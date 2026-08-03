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
