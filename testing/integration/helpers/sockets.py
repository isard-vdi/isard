# SPDX-License-Identifier: AGPL-3.0-or-later

"""Minimal SocketIO listener for the integration suite.

Subscribes to the ``/administrators`` and ``/userspace`` namespaces the
apiv4 webapp/vue frontends use, buffers every incoming event, and
exposes helpers to poll for arrival of a specific event (optionally
matching a predicate).

The listener is intentionally thin — it doesn't try to mirror the full
behaviour of the frontend clients; tests call ``wait_for(event=...)``
or inspect ``events`` directly.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Callable, Optional

import socketio

log = logging.getLogger("integration.sockets")


class SocketIOListener:
    def __init__(
        self,
        token: str,
        url: Optional[str] = None,
        namespaces: tuple = ("/administrators", "/userspace"),
    ) -> None:
        self.url = (
            url or os.environ.get("SOCKETIO_URL") or "http://isard-socketio:5000"
        ).rstrip("/")
        self.token = token
        self.namespaces = namespaces
        self.events: list[tuple[str, str, Any]] = []
        self._lock = threading.Lock()
        self._sio = socketio.Client(
            reconnection=False, logger=False, engineio_logger=False
        )
        self._installed = False

    # --- lifecycle -------------------------------------------------------

    def connect(self, connect_timeout: float = 10.0) -> None:
        if not self._installed:
            for ns in self.namespaces:
                self._install_catchall(ns)
            self._installed = True
        self._sio.connect(
            self.url,
            auth={"jwt": self.token},
            namespaces=list(self.namespaces),
            transports=["websocket"],
            wait_timeout=connect_timeout,
        )

    def disconnect(self) -> None:
        try:
            self._sio.disconnect()
        except Exception:
            pass

    # --- recording -------------------------------------------------------

    def _install_catchall(self, namespace: str) -> None:
        # python-socketio exposes a star handler via on("*") per-namespace
        # (https://python-socketio.readthedocs.io/en/stable/client.html#catch-all-handlers).
        def handler(event: str, data: Any, _ns: str = namespace) -> None:
            payload = data
            if isinstance(data, str):
                try:
                    payload = json.loads(data)
                except ValueError:
                    pass
            with self._lock:
                self.events.append((_ns, event, payload))

        self._sio.on("*", handler=handler, namespace=namespace)

    def clear(self) -> None:
        with self._lock:
            self.events.clear()

    def snapshot(self) -> list[tuple[str, str, Any]]:
        with self._lock:
            return list(self.events)

    # --- polling ---------------------------------------------------------

    def wait_for(
        self,
        event: str,
        namespace: Optional[str] = None,
        predicate: Optional[Callable[[Any], bool]] = None,
        timeout: float = 30.0,
        poll_interval: float = 0.2,
    ) -> tuple[str, str, Any]:
        deadline = time.monotonic() + timeout
        start_from = len(self.events)
        while time.monotonic() < deadline:
            with self._lock:
                for i in range(start_from, len(self.events)):
                    ns, ev, payload = self.events[i]
                    if ev != event:
                        continue
                    if namespace is not None and ns != namespace:
                        continue
                    if predicate is not None and not predicate(payload):
                        continue
                    return ns, ev, payload
            time.sleep(poll_interval)
        raise TimeoutError(
            f"timed out after {timeout}s waiting for event={event!r} namespace={namespace!r}; "
            f"seen since start: {[ (n,e) for n,e,_ in self.events[start_from:] ]}"
        )

    def collect_events(
        self,
        event: str,
        namespace: Optional[str] = None,
        duration: float = 30.0,
    ) -> list[tuple[str, str, Any]]:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            time.sleep(0.5)
        return [
            (ns, ev, payload)
            for ns, ev, payload in self.snapshot()
            if ev == event and (namespace is None or ns == namespace)
        ]
