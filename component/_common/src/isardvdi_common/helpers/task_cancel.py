#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generic redis pub/sub primitive for cooperative task cancellation.

RQ's ``job.cancel()`` only stops jobs while they are still queued — once a
worker picked them up, the job runs to completion. For long-running tasks
(curl, qemu-img convert, rsync, …) we need an out-of-band signal the
running code can poll without busy-looping rethinkdb.

This module provides:

* :func:`request_task_cancel` — one-shot publish a cancel signal for a
  task id. Safe to call from anywhere with redis access (apiv4, scheduler,
  another task).
* :class:`TaskCancelWatcher` — context manager used inside a long-running
  task. Spawns a daemon thread that subscribes to the task's cancel
  channel and exposes a ``cancelled`` boolean. The thread costs nothing
  while no message is in flight (it blocks on ``pubsub.get_message``).

The channel is ``task:cancel:<task_id>`` and the payload is irrelevant —
the mere arrival of any message on that channel means *cancel requested*.

Note: pub/sub is fire-and-forget. If ``request_task_cancel`` runs before
the watcher subscribes, the signal is lost. Callers should either:

* invoke the watcher early (immediately on task entry, before any
  setup) — this module does that automatically when used as a context
  manager, *and*
* perform a one-time check on entry against a persistent flag if one
  is available (e.g. the row's status field). :class:`TaskCancelWatcher`
  accepts an optional ``initial_check`` callable for this.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from redis import Redis

from .. import connections  # noqa: F401  (ensures package import side effects)
from ..connections.redis_base import RedisBase

log = logging.getLogger(__name__)


def _channel(task_id: str) -> str:
    return f"task:cancel:{task_id}"


def request_task_cancel(task_id: str) -> int:
    """Publish a cancel signal for ``task_id``.

    Returns the number of subscribers that received the message (0 means
    either nobody listening *or* the task hasn't reached the watcher yet
    — this is informational only; callers should not retry based on it).

    Idempotent: extra calls are harmless, the running task will see at
    most one ``cancelled`` transition.
    """
    return RedisBase._redis.publish(_channel(task_id), b"cancel")


class TaskCancelWatcher:
    """Context manager: subscribe to a task's cancel channel.

    Usage::

        from rq import get_current_job
        from isardvdi_common.helpers.task_cancel import TaskCancelWatcher

        def long_task(...):
            job = get_current_job()
            with TaskCancelWatcher(job.id) as watcher:
                while doing_work():
                    if watcher.cancelled:
                        cleanup()
                        raise RuntimeError("cancelled")

    The watcher uses a *fresh* redis connection (pub/sub blocks the
    connection it runs on), spawns a daemon thread, and stops cleanly
    when the ``with`` block exits.

    :param task_id: The RQ job id whose cancel channel to subscribe to.
        Usually ``rq.get_current_job().id``.
    :param initial_check: Optional callable returning ``True`` if the
        task should already be considered cancelled at startup
        (e.g. the row's status was flipped before the worker picked the
        job up). Called once on ``__enter__``. Useful to close the
        narrow race where ``request_task_cancel`` fires *before* the
        worker subscribes.
    :param connection: Optional pre-built ``redis.Redis`` instance to
        use. By default, a new connection is created from
        :class:`RedisBase` — required because pub/sub monopolises a
        connection.
    """

    def __init__(
        self,
        task_id: str,
        initial_check: Optional[Callable[[], bool]] = None,
        connection: Optional[Redis] = None,
    ) -> None:
        self._task_id = task_id
        self._initial_check = initial_check
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        # We can't reuse the shared RedisBase connection: pubsub.listen()
        # holds the socket. Build a new one with the same params.
        if connection is not None:
            self._conn = connection
        else:
            kw = RedisBase._redis.connection_pool.connection_kwargs
            self._conn = Redis(
                host=kw.get("host"),
                port=kw.get("port"),
                password=kw.get("password"),
                db=kw.get("db"),
            )
        self._pubsub = None

    @property
    def cancelled(self) -> bool:
        """True if a cancel signal has arrived (or initial_check fired)."""
        return self._event.is_set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until cancel signal arrives or ``timeout`` expires.

        Returns ``True`` if cancelled, ``False`` if the timeout elapsed.
        """
        return self._event.wait(timeout=timeout)

    def __enter__(self) -> "TaskCancelWatcher":
        if self._initial_check is not None:
            try:
                if self._initial_check():
                    self._event.set()
                    return self
            except Exception:
                log.exception(
                    "TaskCancelWatcher: initial_check failed for %s",
                    self._task_id,
                )

        self._pubsub = self._conn.pubsub(ignore_subscribe_messages=True)
        self._pubsub.subscribe(_channel(self._task_id))
        self._thread = threading.Thread(
            target=self._run,
            name=f"task-cancel-watch-{self._task_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        try:
            if self._pubsub is not None:
                # Closing the pubsub connection breaks get_message()'s
                # blocking call so the thread exits quickly.
                self._pubsub.close()
        except Exception:
            pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        try:
            self._conn.close()
        except Exception:
            pass

    def _run(self) -> None:
        # ``get_message`` with a small timeout lets us notice the stop
        # event quickly without busy-looping.
        try:
            while not self._stop.is_set():
                msg = self._pubsub.get_message(timeout=0.5)
                if msg is None:
                    continue
                # ignore_subscribe_messages=True filters the subscribe
                # ack so any message here is a real cancel.
                self._event.set()
                return
        except Exception:
            # Connection errors here just mean we stop watching — the
            # task continues running. Persistent flags (row status,
            # task.status) remain the safety net.
            log.exception(
                "TaskCancelWatcher: subscriber loop crashed for %s",
                self._task_id,
            )
        finally:
            try:
                if self._pubsub is not None:
                    self._pubsub.unsubscribe()
            except Exception:
                pass
