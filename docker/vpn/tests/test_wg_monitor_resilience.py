# SPDX-License-Identifier: AGPL-3.0-or-later
"""Regression test: a poison WireGuard peer must not block other peers.

A single unresolvable ("poison") WireGuard peer must not stop ``wg_monitor``
from updating the connected status of every *other* peer.

Pre-migration the monitor talked to apiv3 through ``ApiClient``, whose
``post``/``delete``/``update`` methods *logged and returned ``False``* on an
HTTP error response instead of raising, so one peer that the API rejected
(``404 No active VPN client``) was silently skipped and the poll pass
continued. The apiv4 migration replaced those calls with
``raise_for_status``, which raises ``ApiV4Error`` on any non-2xx. Because the
per-peer API calls sit inside a shared ``for peer in peers`` loop with only an
*outer* ``except``, one poison peer now aborts the whole iteration and every
peer after it never gets its status updated -> the admin Users VPN indicator
stops updating.
"""
from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def _load_real_wg_monitor():
    """Load ``docker/vpn/src/wg_monitor.py`` under a private module name.

    The session-scoped conftest installs ``sys.modules['wg_monitor']`` as a
    stub (to stop ``wgadmin`` spawning the monitor thread), so importing the
    name would hand back that stub. Loading straight from the file under a
    different name gives us the real ``log_wireguard_peers``.
    """
    spec = importlib.util.spec_from_file_location(
        "wg_monitor_real_2070", str(SRC_DIR / "wg_monitor.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeResp:
    """Minimal stand-in for the generated client's ``Response``."""

    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content


class _StopLoop(BaseException):
    """Escape ``log_wireguard_peers``' ``while True`` after one pass.

    ``BaseException`` so the loop's bare ``except`` (which sleeps and retries)
    cannot swallow it on the way out.
    """


def _make_peer(mod, *, public_key: str, client_ip: str):
    return mod.RemotePeer(
        device="users",
        public_key=public_key,
        remote_addr="8.8.8.8:2222",
        allowed_ips=[f"{client_ip}/32"],
        latest_handshake=datetime.now(),
        transfer_rx=1,
        transfer_tx=1,
    )


@pytest.fixture
def wg_monitor_real():
    return _load_real_wg_monitor()


def test_poison_peer_does_not_block_other_peers(wg_monitor_real, monkeypatch):
    mod = wg_monitor_real

    poison = _make_peer(mod, public_key="POISON_KEY", client_ip="10.0.0.250")
    healthy = _make_peer(mod, public_key="HEALTHY_KEY", client_ip="10.0.0.2")

    # First get_peer_states() builds the initial (empty) peer_state, so both
    # peers look brand-new *with* a handshake -> both take the
    # "new peer -> connect" branch on the single poll iteration.
    states = [[], [poison, healthy]]
    monkeypatch.setattr(
        mod, "get_peer_states", lambda: states.pop(0) if states else [poison, healthy]
    )

    # Dummy build_client context manager: no JWT minting, no network.
    @contextmanager
    def fake_build_client(*args, **kwargs):
        yield object()

    monkeypatch.setattr(mod, "build_client", fake_build_client)

    connect_calls: list[str] = []

    def fake_connect(*, kind, client_ip, client, body):
        connect_calls.append(client_ip)
        # apiv4 rejects the poison IP (resolves to no users/remotevpn row).
        if client_ip == "10.0.0.250":
            return _FakeResp(404, b'{"error":"not_found"}')
        return _FakeResp(204, b"")

    monkeypatch.setattr(mod.vpn_connection_connect, "sync_detailed", fake_connect)

    # Break out of the while True loop after exactly one pass.
    def fake_sleep(_):
        raise _StopLoop

    monkeypatch.setattr(mod.time, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        mod.log_wireguard_peers(poll_delay=5, handshake_timeout=150)

    assert "10.0.0.250" in connect_calls, "poison peer should be attempted"
    assert "10.0.0.2" in connect_calls, (
        "healthy peer must still be processed even though the poison peer's "
        "connect returned 404"
    )


def test_only_404_is_skipped(wg_monitor_real):
    """Only the benign 404 is swallowed; systemic errors still propagate.

    Swallowing *every* non-2xx would silently mask a 500 (server bug) or 401
    (auth) peer-by-peer. Those must reach the outer retry loop, so
    ``_skip_unresolved_peer`` re-raises anything that is not a 404.
    """
    from isardvdi_apiv4_client_auth import ApiV4Error

    mod = wg_monitor_real

    # 404 -> skipped (no active client for this peer); returns True so the
    # caller leaves peer_state unchanged and retries on a later poll.
    assert mod._skip_unresolved_peer(_FakeResp(404, b'{"error":"not_found"}')) is True

    # 2xx -> applied; returns False so the caller advances peer_state.
    assert mod._skip_unresolved_peer(_FakeResp(204, b"")) is False

    # 5xx / 401 -> systemic, must propagate.
    with pytest.raises(ApiV4Error):
        mod._skip_unresolved_peer(_FakeResp(500, b'{"error":"internal_server"}'))
    with pytest.raises(ApiV4Error):
        mod._skip_unresolved_peer(_FakeResp(401, b'{"error":"unauthorized"}'))
