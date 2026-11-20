# Copyright 2026 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

"""A new peer is generated once: add_peer adopts the peer init_peers made, never a second one."""
from __future__ import annotations

import ipaddress
import threading
from unittest.mock import MagicMock, patch

from isardvdi_vpn import wgtools


class _Ctx:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


class _FakeDB:
    """A tiny stateful table: init_peers writes here, add_peer reads it back."""

    def __init__(self, rows=()):
        self.rows = {row["id"]: dict(row) for row in rows}
        self.updated = []  # ids written through get().update()


class _Tbl:
    def __init__(self, db, name):
        self.db = db
        self._id = None
        self._pending = None

    def pluck(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def get(self, i):
        self._id = i
        return self

    def update(self, doc):
        self._pending = ("update", doc)
        return self

    def replace(self, fn):
        self._pending = ("replace", fn)
        return self

    def run(self, conn):
        if self._pending:
            kind, arg = self._pending
            if self._id not in self.db.rows:
                return {"skipped": 1, "replaced": 0}
            if kind == "update":
                self.db.rows[self._id].update(arg)
                self.db.updated.append(self._id)
            else:
                self.db.rows[self._id].pop("nets", None)
            return {"replaced": 1}
        if self._id is not None:
            return self.db.rows.get(self._id)
        return list(self.db.rows.values())


class _Expr:
    def __init__(self, seq):
        self.seq = list(seq)

    def for_each(self, fn):
        self._fn = fn
        return self

    def run(self, conn):
        for item in self.seq:
            self._fn(item).run(conn)
        return {"replaced": len(self.seq)}


class _FakeR:
    def __init__(self, db):
        self.db = db
        self.row = MagicMock()

    def table(self, name, *a, **k):
        return _Tbl(self.db, name)

    def expr(self, seq):
        return _Expr(seq)


def _hyper_wg(reserved=None):
    Wg = wgtools.Wg
    wg = Wg.__new__(Wg)
    wg.table = "hypervisors"
    wg.interface = "hypers"
    wg.allowed_client_nets = "10.1.0.1/32"
    wg.server_net = ipaddress.ip_network("10.1.0.0/24")
    wg.server_ip = "10.1.0.1"
    wg.clients_reserved_ips = {"10.1.0.1"} if reserved is None else set(reserved)
    wg.uipt = MagicMock()
    wg.keys = MagicMock()
    wg.keys.update_clients = False
    wg.keys.new_client_keys.side_effect = (
        {"public": f"pub{i}", "private": f"priv{i}"} for i in range(1, 1000)
    )
    return wg


def _counting_gen_ip(wg, counter):
    real = wg.gen_client_ip
    wg.gen_client_ip = lambda: (counter.__setitem__("n", counter["n"] + 1) or real())


def _public(peer):
    return peer["vpn"]["wireguard"]["keys"]["public"]


def _address(peer):
    return peer["vpn"]["wireguard"]["Address"]


def _join_up_threads():
    for t in threading.enumerate():
        if t.name.startswith("init_peers_up_"):
            t.join(timeout=5)


def _row(address, public):
    return {
        "id": "h1",
        "hostname": "h1",
        "vpn": {
            "wireguard": {
                "Address": address,
                "keys": {"public": public, "private": "p"},
                "extra_client_nets": None,
                "AllowedIPs": "10.1.0.1/32",
            }
        },
    }


# --- the fix, end to end: init_peers then add_peer of the same id ---


def test_end_to_end_add_adopts_the_init_peer_without_regenerating():
    wg = _hyper_wg()
    db = _FakeDB([{"id": "h1", "hostname": "h1"}])  # fresh row, no vpn
    up = []
    wg.up_peer = lambda p: up.append(p) or True
    wg._to_model = lambda d: d
    gen = {"n": 0}
    _counting_gen_ip(wg, gen)
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ):
        wg.init_peers(reset=False)
        _join_up_threads()
        updated_after_init = list(db.updated)
        wg.add_peer({"id": "h1", "hostname": "h1"})

    assert gen["n"] == 1  # only init_peers allocated an address
    assert db.updated == updated_after_init  # add_peer wrote nothing to the db
    assert up and all(_address(p) == "10.1.0.2" and _public(p) == "pub1" for p in up)


def test_batched_insert_event_carrying_the_peer_is_adopted():
    wg = _hyper_wg()
    db = _FakeDB([{"id": "h1", "hostname": "h1"}])
    up = []
    wg.up_peer = lambda p: up.append(p) or True
    wg._to_model = lambda d: d
    gen = {"n": 0}
    _counting_gen_ip(wg, gen)
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ):
        wg.init_peers(reset=False)
        _join_up_threads()
        updated_after_init = list(db.updated)
        # the changefeed batched the insert, so the event already carries the peer
        wg.add_peer(dict(db.rows["h1"]))

    assert gen["n"] == 1
    assert db.updated == updated_after_init
    assert up and all(_address(p) == "10.1.0.2" for p in up)


def test_registration_survives_a_second_wg_on_the_same_interface():
    db = _FakeDB([{"id": "h1", "hostname": "h1"}])
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ):
        wg1 = _hyper_wg()
        wg1.up_peer = lambda p: True
        wg1._to_model = lambda d: d
        wg1.init_peers(reset=False)
        _join_up_threads()
        # the consumer crashed; wgadmin.main() rebuilds Wg on the same interface
        wg2 = _hyper_wg()
        up = []
        wg2.up_peer = lambda p: up.append(p) or True
        gen = {"n": 0}
        _counting_gen_ip(wg2, gen)
        wg2.add_peer({"id": "h1", "hostname": "h1"})

    assert gen["n"] == 0  # wg2 adopted via the module-level registry, never generated
    assert up and all(_address(p) == "10.1.0.2" for p in up)


def test_registration_is_single_use_a_second_insert_regenerates():
    wg = _hyper_wg()
    db = _FakeDB([{"id": "h1", "hostname": "h1"}])
    up = []
    wg.up_peer = lambda p: up.append(p) or True
    wg._to_model = lambda d: d
    gen = {"n": 0}
    _counting_gen_ip(wg, gen)
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ):
        wg.init_peers(reset=False)
        _join_up_threads()
        wg.add_peer({"id": "h1", "hostname": "h1"})  # adopts, clears the registry
        gen_after_first = gen["n"]
        updated_after_first = list(db.updated)
        wg.add_peer({"id": "h1", "hostname": "h1"})  # no entry now -> regenerate

    assert gen_after_first == 1
    assert gen["n"] == 2  # the second insert allocated a fresh address
    assert len(db.updated) > len(updated_after_first)  # and wrote it


# --- the geneve port follows the adopted (db) address ---


def test_adopt_sets_the_geneve_remote_ip_to_the_db_address():
    wg = _hyper_wg(reserved={"10.1.0.1", "10.1.0.2"})
    wg._generated_peers["h1"] = "INIT"
    db = _FakeDB([_row("10.1.0.2", "INIT")])
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ), patch.object(wgtools, "check_output", side_effect=["", "42"]), patch.object(
        wgtools.subprocess, "run"
    ) as mock_run:
        wg.add_peer({"id": "h1", "hostname": "h1"})

    cmds = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    assert any("options:remote_ip=10.1.0.2" in c for c in cmds)
    assert any(" INIT " in c + " " for c in cmds if c.startswith("/usr/bin/wg set"))


# --- a peer we did not generate is never adopted ---


def test_add_peer_regenerates_a_foreign_peer_and_ups_the_new_one():
    wg = _hyper_wg(reserved={"10.1.0.1"})  # no registry entry
    db = _FakeDB([_row("10.1.0.9", "OLD")])
    up = []
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ), patch.object(wgtools.Wg, "up_peer", lambda self, p: up.append(p) or True):
        wg.add_peer({"id": "h1", "hostname": "h1"})

    assert _public(up[0]) == "pub1"  # freshly generated
    assert _address(up[0]) == "10.1.0.2"  # not the foreign 10.1.0.9


def test_add_peer_does_not_reuse_a_restored_peer_address():
    wg = _hyper_wg(reserved={"10.1.0.1", "10.1.0.2"})  # .2 belongs to another row
    db = _FakeDB([_row("10.1.0.2", "OLD")])
    up = []
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ), patch.object(wgtools.Wg, "up_peer", lambda self, p: up.append(p) or True):
        wg.add_peer({"id": "h1", "hostname": "h1"})

    assert _address(up[0]) == "10.1.0.3"  # fresh, not the colliding 10.1.0.2


def test_add_peer_adds_nothing_when_the_row_vanished():
    wg = _hyper_wg(reserved={"10.1.0.1"})  # no registry entry
    db = _FakeDB([])  # the row was deleted before we claimed it
    up = []
    with patch.object(wgtools, "r", _FakeR(db)), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ), patch.object(wgtools.Wg, "up_peer", lambda self, p: up.append(p) or True):
        wg.add_peer({"id": "h1", "hostname": "h1"})

    assert up == []
    assert "10.1.0.2" not in wg.clients_reserved_ips  # released


def test_down_peer_clears_the_registry_for_a_deleted_row():
    wg = _hyper_wg()
    wg._generated_peers["h1"] = "INIT"
    with patch.object(wgtools, "r", _FakeR(_FakeDB())), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ), patch.object(wgtools, "check_output", side_effect=["", ""]), patch.object(
        wgtools.subprocess, "run"
    ):
        wg.down_peer({"id": "h1", "hostname": "h1"})
    assert wg._generated_peers == {}


# --- init_peers still regenerates on rotation and on reset ---


def _run_init_peers(wg, rows):
    flushed = []
    wg._flush_peers_batch = lambda table, batch, *a, **k: flushed.append((table, batch))
    wg.up_peer = lambda p: True
    wg._to_model = lambda d: d
    with patch.object(wgtools, "r", _FakeR(_FakeDB(rows))), patch.object(
        wgtools, "vpn_rethink_conn", lambda *a, **k: _Ctx()
    ):
        wg.init_peers(reset=False)
    _join_up_threads()
    return [p for _, batch in flushed for p in batch]


def test_server_key_rotation_still_regenerates():
    wg = _hyper_wg()
    wg.keys.update_clients = True
    written = _run_init_peers(wg, [_row("10.1.0.2", "old")])
    assert any(
        p["id"] == "h1"
        and p["vpn"]["wireguard"]["keys"] == {"public": "pub1", "private": "priv1"}
        for p in written
    )


def test_user_reset_still_regenerates():
    wg = _hyper_wg()
    rows = [{"id": "h1", "vpn": {"wireguard": {"Address": "10.1.0.2", "keys": False}}}]
    written = _run_init_peers(wg, rows)
    assert any(
        p["id"] == "h1"
        and p["vpn"]["wireguard"]["keys"] == {"public": "pub1", "private": "priv1"}
        for p in written
    )
