# Copyright 2026 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

"""The peer write must never bring back a row that was deleted meanwhile.

Generating a peer's config shells out to wireguard, so a user can be removed
between the moment their peer is built and the moment it is stored. An upsert
would recreate them as an ``{id, vpn}`` stub that holds a client IP and breaks
every query expecting a real user; an update leaves the deletion alone.
"""

from __future__ import annotations

from unittest.mock import patch


def test_add_peer_updates_and_never_inserts(wgtools_module):
    """``add_peer`` writes through ``get(id).update(...)``, not an upsert."""
    wg = wgtools_module.Wg.__new__(wgtools_module.Wg)
    wg.table = "users"
    wg.allowed_client_nets = "10.2.0.0/16"

    calls = {"update": 0, "insert": 0, "got": []}

    class _Row:
        def update(self, doc):
            calls["update"] += 1
            return self

        def run(self, *args, **kwargs):
            return {"replaced": 1}

    class _Table:
        def get(self, item_id):
            calls["got"].append(item_id)
            return _Row()

        def insert(self, *args, **kwargs):
            calls["insert"] += 1
            raise AssertionError(
                "add_peer must not insert: it can resurrect a deleted row"
            )

    class _Conn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    with patch.object(
        wgtools_module, "vpn_rethink_conn", lambda *a, **k: _Conn()
    ), patch.object(wgtools_module.r, "table", lambda *_: _Table()), patch.object(
        wgtools_module.Wg,
        "gen_new_peer",
        lambda self, peer, **kw: {"id": peer["id"], "vpn": {}},
    ), patch.object(
        wgtools_module.Wg, "up_peer", lambda self, peer: True
    ):
        wg.add_peer({"id": "gone-user"}, table="users")

    assert calls["insert"] == 0
    assert calls["update"] == 1
    assert calls["got"] == ["gone-user"]


def test_add_peer_takes_the_peer_back_off_when_the_row_is_gone(wgtools_module):
    """update alone is not enough: the peer is already on the interface.

    up_peer() runs before the write, so a write that skips a missing row leaves
    a peer with nothing in the database pointing at it -- the orphan that
    answers 404 on every reconnect until the container restarts. Trading the
    stub row for an orphan peer is not a fix, so the peer must come back off.
    """
    from unittest.mock import MagicMock, patch

    Wg = wgtools_module.Wg
    wg = Wg.__new__(Wg)
    wg.table = "users"
    wg.interface = "users"
    wg.uipt = MagicMock()
    removed = []

    class _Table:
        def get(self, key):
            return self

        def update(self, doc):
            return self

        def replace(self, *a, **kw):  # pragma: no cover - must not be reached
            raise AssertionError("a vanished row must not be touched further")

        def run(self, conn):
            return {"skipped": 1, "replaced": 0}

    class _Conn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    with patch.object(
        wgtools_module, "vpn_rethink_conn", lambda *a, **k: _Conn()
    ), patch.object(wgtools_module.r, "table", lambda *_: _Table()), patch.object(
        wgtools_module.Wg,
        "gen_new_peer",
        lambda self, peer, **kw: {"id": peer["id"], "vpn": {}},
    ), patch.object(
        wgtools_module.Wg, "up_peer", lambda self, peer: True
    ), patch.object(
        wgtools_module.Wg,
        "down_peer",
        lambda self, peer, table=False: removed.append(peer["id"]),
    ):
        wg.add_peer({"id": "gone-user"}, table="users")

    assert removed == ["gone-user"]
