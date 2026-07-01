"""Per-hypervisor tunnel liveness monitor.

Publishes ``hypervisors[id].vpn.tunnel_status`` (``"connected"`` /
``"disconnected"``) so the webapp datatable can render a live VPN
indicator without polling the API. The signal is mode-specific:

  * **geneve-only** (``GENEVE_ONLY_INFRA=true``)
        The OVS geneve port for each hypervisor carries BFD (200 ms
        intervals, see wgadmin.py / wgtools.py). ``bfd_status:state ==
        "up"`` is treated as connected. BFD is the only liveness signal
        available in this mode — there is no wireguard layer.

  * **wireguard+geneve** (default)
        The OVS BFD session is intentionally disabled in this mode (see
        the BFD optimisation commit) because wireguard's own 25 s
        persistent-keepalive is the actual tunnel liveness check. The
        peer is connected iff ``latest_handshake`` is within
        ``HANDSHAKE_TIMEOUT`` (75 s = 3× keepalive).

We update RethinkDB directly (the changefeed → change-handler →
socketio chain delivers ``hyper_data`` to the webapp). The monitor
debounces by writing only when a hypervisor's status actually flips —
the changefeed otherwise gets a no-op write per tick and the webapp
re-renders the row needlessly.
"""

from __future__ import annotations

import logging as log
import os
import subprocess
import threading
import time
import traceback
from subprocess import check_output

from rethinkdb import RethinkDB

POLL_INTERVAL_S = 5
HANDSHAKE_TIMEOUT_S = 75  # 3 x persistent-keepalive (25 s)


def _rdb_connect():
    r = RethinkDB()
    return r, r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(os.environ.get("RETHINKDB_PORT", "28015")),
        password=os.environ.get("RETHINKDB_AUTH", ""),
        db=os.environ.get("RETHINKDB_DB", "isard"),
        timeout=10,
    )


def _bfd_state(port_name: str) -> str | None:
    """Return the OVS BFD ``state`` for ``port_name`` (``"up"`` /
    ``"down"`` / ``"init"``) or None if the port is gone."""
    try:
        out = check_output(
            ["ovs-vsctl", "get", "Interface", port_name, "bfd_status:state"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return out.strip('"') or None


def _wg_handshakes(interface: str) -> dict[str, int]:
    """Return ``{public_key: latest_handshake_epoch}`` for ``interface``.
    ``0`` means no handshake has happened yet."""
    try:
        out = check_output(
            ["wg", "show", interface, "latest-handshakes"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        return {}
    result: dict[str, int] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            try:
                result[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return result


def _connected_geneve(hyper_id: str) -> bool:
    return _bfd_state(hyper_id) == "up"


def _connected_wireguard(public_key: str, handshakes: dict[str, int]) -> bool:
    ts = handshakes.get(public_key, 0)
    if ts == 0:
        return False
    return (time.time() - ts) < HANDSHAKE_TIMEOUT_S


def _set_status(r, conn, hyper_id: str, connected: bool):
    """Write tunnel_status if it changed. Returns the new bool or None
    if it was already at the target value."""
    target = "connected" if connected else "disconnected"
    current = (
        r.table("hypervisors")
        .get(hyper_id)
        .get_field("vpn")
        .default({})
        .get_field("tunnel_status")
        .default(None)
        .run(conn)
    )
    if current == target:
        return None
    r.table("hypervisors").get(hyper_id).update({"vpn": {"tunnel_status": target}}).run(
        conn
    )
    log.info(
        "tunnel_monitor: %s %s -> %s",
        hyper_id,
        current or "(unset)",
        target,
    )
    return connected


def _poll_once(r, conn, geneve_only: bool):
    """One pass over the hypervisors table."""
    hypers = list(
        r.table("hypervisors")
        .pluck("id", {"vpn": ["tunneling_mode", "wireguard"]})
        .run(conn)
    )
    handshakes = {} if geneve_only else _wg_handshakes("hypers")
    for h in hypers:
        hyper_id = h["id"]
        vpn = h.get("vpn") or {}
        mode = vpn.get("tunneling_mode", "wireguard+geneve")
        try:
            if geneve_only or mode == "geneve":
                connected = _connected_geneve(hyper_id)
            else:
                pub = (vpn.get("wireguard") or {}).get("keys", {}).get("public")
                connected = _connected_wireguard(pub, handshakes) if pub else False
            _set_status(r, conn, hyper_id, connected)
        except Exception:
            log.debug("tunnel_monitor %s failed:\n%s", hyper_id, traceback.format_exc())


def _run(geneve_only: bool):
    """Long-running poller. Reconnects to rdb on driver errors."""
    while True:
        try:
            r, conn = _rdb_connect()
            log.info(
                "tunnel_monitor started (interval=%ss, mode=%s)",
                POLL_INTERVAL_S,
                "geneve-only" if geneve_only else "wireguard+geneve",
            )
            while True:
                _poll_once(r, conn, geneve_only)
                time.sleep(POLL_INTERVAL_S)
        except Exception:
            log.warning(
                "tunnel_monitor reconnecting after error:\n%s", traceback.format_exc()
            )
            time.sleep(5)


def start():
    """Spawn the poller as a daemon thread."""
    geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
    t = threading.Thread(target=_run, args=(geneve_only,), daemon=True)
    t.start()
    return t
