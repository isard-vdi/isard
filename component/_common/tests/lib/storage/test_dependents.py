# SPDX-License-Identifier: AGPL-3.0-or-later

"""The one dependents primitive: header read, index build, and the single
"what depends on this disk" query in its direct / transitive / covered / live
modes."""

import struct

from isardvdi_common.lib.storage import dependents

BASE = "11111111-1111-1111-1111-111111111111"
MID = "22222222-2222-2222-2222-222222222222"
LEAF = "33333333-3333-3333-3333-333333333333"
POOL = "/isard/storage_pools/default/templates"


def _qcow2(path, backing=None):
    """Write a minimal qcow2 header (magic + backing offset/size) — enough for
    the header-only reader, no qemu-img needed."""
    head = bytearray(72)
    head[0:4] = dependents.QCOW2_MAGIC
    if backing:
        raw = backing.encode()
        head[8:16] = struct.pack(">Q", 72)
        head[16:20] = struct.pack(">I", len(raw))
        head += raw
    path.write_bytes(bytes(head))
    return str(path)


def test_read_backing_reads_the_header(tmp_path):
    with_b = _qcow2(tmp_path / "a.qcow2", backing="/isard/x/base.qcow2")
    assert dependents.read_backing(with_b) == ("/isard/x/base.qcow2", True)
    no_b = _qcow2(tmp_path / "b.qcow2")
    assert dependents.read_backing(no_b) == (None, True)
    (tmp_path / "c.qcow2").write_bytes(b"not a qcow2 at all")
    assert dependents.read_backing(str(tmp_path / "c.qcow2")) == (None, False)


def test_build_backing_index_shape(tmp_path):
    p = _qcow2(tmp_path / f"{LEAF}.qcow2", backing=f"{POOL}/{BASE}.qcow2")
    idx = dependents.build_backing_index([p])
    e = idx[p]
    assert e["uuid"] == LEAF
    assert e["backing_raw"] == f"{POOL}/{BASE}.qcow2"
    assert e["backing_uuid"] == BASE
    assert e["readable"] is True


def _index():
    # mid reads through base; leaf reads through mid; a stray reads through nobody
    return {
        f"{POOL}/{MID}.qcow2": {
            "uuid": MID,
            "size": 1,
            "backing_raw": f"{POOL}/{BASE}.qcow2",
            "backing_uuid": BASE,
            "readable": True,
        },
        f"{POOL}/{LEAF}.qcow2": {
            "uuid": LEAF,
            "size": 1,
            "backing_raw": f"{POOL}/{MID}.qcow2",
            "backing_uuid": MID,
            "readable": True,
        },
        f"{POOL}/stray.qcow2": {
            "uuid": None,
            "size": 1,
            "backing_raw": None,
            "backing_uuid": None,
            "readable": True,
        },
    }


def test_direct_dependents_are_immediate_children_only():
    deps, unreadable = dependents.dependents_of(f"{POOL}/{BASE}.qcow2", _index())
    assert deps == [f"{POOL}/{MID}.qcow2"]  # not the leaf
    assert unreadable == []


def test_transitive_dependents_follow_the_chain():
    deps, _ = dependents.dependents_of(
        f"{POOL}/{BASE}.qcow2", _index(), transitive=True
    )
    assert deps == [f"{POOL}/{MID}.qcow2", f"{POOL}/{LEAF}.qcow2"]


def test_a_match_by_uuid_survives_a_moved_backing_pointer():
    # mid's stored pointer is a stale path, but its backing_uuid still names base
    idx = _index()
    idx[f"{POOL}/{MID}.qcow2"]["backing_raw"] = "/old/location/" + BASE + ".qcow2"
    deps, _ = dependents.dependents_of(f"{POOL}/{BASE}.qcow2", idx)
    assert deps == [f"{POOL}/{MID}.qcow2"]


def test_covered_paths_are_not_counted():
    deps, _ = dependents.dependents_of(
        f"{POOL}/{BASE}.qcow2", _index(), covered_paths=[f"{POOL}/{MID}.qcow2"]
    )
    assert deps == []


def test_live_uuids_filter_keeps_only_live_candidates():
    deps, _ = dependents.dependents_of(
        f"{POOL}/{BASE}.qcow2", _index(), live_uuids={LEAF}
    )
    assert deps == []  # mid is the only direct child and it is not live
    deps, _ = dependents.dependents_of(
        f"{POOL}/{BASE}.qcow2", _index(), transitive=True, live_uuids={LEAF}
    )
    assert deps == [f"{POOL}/{LEAF}.qcow2"]  # leaf reached transitively and is live


def test_an_unreadable_candidate_is_reported_never_assumed_safe():
    idx = _index()
    idx[f"{POOL}/bad.qcow2"] = {
        "uuid": None,
        "size": 1,
        "backing_raw": None,
        "backing_uuid": None,
        "readable": False,
    }
    _, unreadable = dependents.dependents_of(f"{POOL}/{BASE}.qcow2", idx)
    assert unreadable == [f"{POOL}/bad.qcow2"]
