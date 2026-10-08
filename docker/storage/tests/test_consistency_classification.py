# SPDX-License-Identifier: AGPL-3.0-or-later
"""The pure table-vs-pool classifier and the qcow2 header reader, on synthetic data."""

import struct
import sys
from pathlib import Path

_UTILS = Path(__file__).resolve().parents[1] / "utils"
if str(_UTILS) not in sys.path:
    sys.path.insert(0, str(_UTILS))

from storage_lib.consistency import (  # noqa: E402
    best_file_by_uuid,
    classify_storage_consistency,
    uuids_sustaining_live,
)
from storage_lib.qcow import build_backing_index, read_qcow2_backing  # noqa: E402

POOL = "/isard/storage_pools/default"


def df(path, uuid, backing_uuid=None, backing_raw=None, size=100, readable=True):
    return {
        "path": path,
        "uuid": uuid,
        "backing_uuid": backing_uuid,
        "backing_raw": backing_raw,
        "size": size,
        "readable": readable,
    }


def row(rid, status, path, live=False, parent=None):
    return {"id": rid, "status": status, "path": path, "parent": parent, "live": live}


def _estate():
    """A rows+files estate with exactly one instance of each casuistic + a clean chain."""
    rows = [
        row("u_tg", "ready", f"{POOL}/templates/u_tg.qcow2", live=True),
        row("u_dg", "ready", f"{POOL}/desktops/u_dg.qcow2", live=True, parent="u_tg"),
        row("u_r2", "ready", f"{POOL}/desktops/u_r2.qcow2", live=True),
        row("u_r3", "ready", f"{POOL}/desktops/u_r3.qcow2", live=True),
        row("u_t4a", "deleted", f"{POOL}/templates/u_t4a.qcow2"),
        row(
            "u_d4a", "ready", f"{POOL}/desktops/u_d4a.qcow2", live=True, parent="u_t4a"
        ),
        row("u_t4b", "deleted", f"{POOL}/templates/u_t4b.qcow2"),
        row("u_d5", "ready", f"{POOL}/desktops/u_d5.qcow2", live=True, parent="u_gone"),
        row(
            "u_d5b", "ready", f"{POOL}/desktops/u_d5b.qcow2", live=True, parent="u_p5b"
        ),
        row("u_p5b", "ready", f"{POOL}/templates/moved/u_p5b.qcow2"),
        row("u_r7", "non_existing", f"{POOL}/desktops/u_r7.qcow2"),
    ]
    files = [
        df(f"{POOL}/templates/u_tg.qcow2", "u_tg"),
        df(
            f"{POOL}/desktops/u_dg.qcow2",
            "u_dg",
            "u_tg",
            f"{POOL}/templates/u_tg.qcow2",
        ),
        df(f"{POOL}/desktops/u_orph.qcow2", "u_orph"),  # c1: no row
        df(
            f"{POOL}/templates/u_r3.qcow2", "u_r3"
        ),  # c3: file under templates, row says desktops
        df(f"{POOL}/templates/u_t4a.qcow2", "u_t4a"),
        df(
            f"{POOL}/desktops/u_d4a.qcow2",
            "u_d4a",
            "u_t4a",
            f"{POOL}/templates/u_t4a.qcow2",
        ),
        df(f"{POOL}/templates/u_t4b.qcow2", "u_t4b"),
        df(
            f"{POOL}/desktops/u_d5.qcow2",
            "u_d5",
            "u_gone",
            f"{POOL}/templates/u_gone.qcow2",
        ),
        df(
            f"{POOL}/desktops/u_d5b.qcow2",
            "u_d5b",
            "u_p5b",
            f"{POOL}/templates/u_p5b.qcow2",
        ),
        df(
            f"{POOL}/templates/moved/u_p5b.qcow2", "u_p5b"
        ),  # displaced parent, present here
    ]
    return rows, files


def _ids(items):
    return {i.get("id") or i.get("uuid") for i in items}


def test_each_casuistic_in_its_own_bucket():
    rows, files = _estate()
    res = classify_storage_consistency(rows, files)
    assert _ids(res["c1_file_no_row"]) == {"u_orph"}
    assert _ids(res["c2_ready_no_file"]) == {"u_r2"}
    assert _ids(res["c3_ready_wrong_pool"]) == {"u_r3"}
    assert _ids(res["c4a_deleted_sustains_live"]) == {"u_t4a"}
    assert _ids(res["c4bc_deleted_dead"]) == {"u_t4b"}
    assert _ids(res["c5_parent_missing"]) == {"u_d5"}
    assert _ids(res["c5b_parent_displaced"]) == {"u_d5b"}
    assert _ids(res["c7_non_existing"]) == {"u_r7"}


def test_clean_chain_is_not_flagged_anywhere():
    rows, files = _estate()
    res = classify_storage_consistency(rows, files)
    everything = set()
    for items in res.values():
        everything |= _ids(items)
    # the good template, its live desktop and the (correctly relocated) parent
    assert {"u_tg", "u_dg", "u_p5b"}.isdisjoint(everything)


def test_c4a_reports_which_live_disks_it_sustains():
    rows, files = _estate()
    res = classify_storage_consistency(rows, files)
    (item,) = res["c4a_deleted_sustains_live"]
    assert item["id"] == "u_t4a"
    assert item["sustains"] == ["u_d4a"]
    assert item["sustains_count"] == 1


def test_deleted_template_without_live_child_is_c4bc_not_c4a():
    rows = [row("t", "deleted", f"{POOL}/templates/t.qcow2")]
    files = [df(f"{POOL}/templates/t.qcow2", "t")]
    res = classify_storage_consistency(rows, files)
    assert _ids(res["c4a_deleted_sustains_live"]) == set()
    assert _ids(res["c4bc_deleted_dead"]) == {"t"}


def test_sustained_deep_in_the_chain_still_counts():
    # live desktop -> mid template -> root template; both templates deleted.
    rows = [
        row("root", "deleted", f"{POOL}/templates/root.qcow2"),
        row("mid", "deleted", f"{POOL}/templates/mid.qcow2"),
        row("live", "ready", f"{POOL}/desktops/live.qcow2", live=True, parent="mid"),
    ]
    files = [
        df(f"{POOL}/templates/root.qcow2", "root"),
        df(
            f"{POOL}/templates/mid.qcow2", "mid", "root", f"{POOL}/templates/root.qcow2"
        ),
        df(f"{POOL}/desktops/live.qcow2", "live", "mid", f"{POOL}/templates/mid.qcow2"),
    ]
    res = classify_storage_consistency(rows, files)
    assert _ids(res["c4a_deleted_sustains_live"]) == {"root", "mid"}


def test_parent_missing_vs_displaced():
    rows = [
        row("child_missing", "ready", f"{POOL}/desktops/cm.qcow2", live=True),
        row("child_displaced", "ready", f"{POOL}/desktops/cd.qcow2", live=True),
        row("parent", "ready", f"{POOL}/templates/moved/p.qcow2"),
    ]
    files = [
        df(
            f"{POOL}/desktops/cm.qcow2",
            "child_missing",
            "gone",
            f"{POOL}/templates/gone.qcow2",
        ),
        df(
            f"{POOL}/desktops/cd.qcow2",
            "child_displaced",
            "parent",
            f"{POOL}/templates/p.qcow2",
        ),
        df(f"{POOL}/templates/moved/p.qcow2", "parent"),
    ]
    res = classify_storage_consistency(rows, files)
    assert _ids(res["c5_parent_missing"]) == {"child_missing"}
    assert _ids(res["c5b_parent_displaced"]) == {"child_displaced"}
    (disp,) = res["c5b_parent_displaced"]
    assert disp["found_at"] == f"{POOL}/templates/moved/p.qcow2"


def test_c5c_parent_link_broken_while_file_chain_is_fine():
    # migration-201 reduced a path-shaped parent to its last segment; the file
    # chain still points at the live parent, only the row link is broken.
    rows = [
        row("parent", "ready", f"{POOL}/templates/parent.qcow2", live=True),
        row(
            "child",
            "ready",
            f"{POOL}/desktops/child.qcow2",
            live=True,
            parent="parent.qcow2",
        ),
    ]
    files = [
        df(f"{POOL}/templates/parent.qcow2", "parent"),
        df(
            f"{POOL}/desktops/child.qcow2",
            "child",
            "parent",
            f"{POOL}/templates/parent.qcow2",
        ),
    ]
    res = classify_storage_consistency(rows, files)
    (item,) = res["c5c_parent_mislinked"]
    assert item["id"] == "child"
    assert item["registered_parent"] == "parent.qcow2"
    assert item["real_backing_uuid"] == "parent"
    assert item["real_backing_path"] == f"{POOL}/templates/parent.qcow2"
    assert item["backing_row_status"] == "ready"
    # the file chain is intact, so it must NOT be read as missing/displaced
    assert res["c5_parent_missing"] == []
    assert res["c5b_parent_displaced"] == []


def test_c5c_not_flagged_when_row_parent_matches_header():
    rows = [
        row("parent", "ready", f"{POOL}/templates/parent.qcow2", live=True),
        row(
            "child", "ready", f"{POOL}/desktops/child.qcow2", live=True, parent="parent"
        ),
    ]
    files = [
        df(f"{POOL}/templates/parent.qcow2", "parent"),
        df(
            f"{POOL}/desktops/child.qcow2",
            "child",
            "parent",
            f"{POOL}/templates/parent.qcow2",
        ),
    ]
    res = classify_storage_consistency(rows, files)
    assert res["c5c_parent_mislinked"] == []


def test_binned_copy_of_a_deleted_row_is_not_a_rowless_file():
    # a soft-deleted disk keeps a copy under deleted/, but its uuid has a row.
    rows = [row("x", "deleted", f"{POOL}/desktops/x.qcow2")]
    files = [
        df(f"{POOL}/desktops/x.qcow2", "x"),
        df(f"{POOL}/desktops/deleted/x.qcow2", "x"),
        df(f"{POOL}/desktops/truly_orphan.qcow2", "y"),
    ]
    res = classify_storage_consistency(rows, files)
    assert _ids(res["c1_file_no_row"]) == {"y"}


def test_check_errors_become_c6_and_deferred_jobs_become_c8():
    res = classify_storage_consistency(
        [],
        [],
        check_errors={f"{POOL}/desktops/bad.qcow2": {"corruptions": 3}},
        deferred_jobs=[
            {"id": "no_expiry", "ttl": -1},
            {"id": "has_expiry", "expires": 1789},
        ],
    )
    assert [i["path"] for i in res["c6_qcow2_errors"]] == [f"{POOL}/desktops/bad.qcow2"]
    assert res["c6_qcow2_errors"][0]["corruptions"] == 3
    assert [j["id"] for j in res["c8_deferred_no_expiry"]] == ["no_expiry"]


def test_best_file_by_uuid_prefers_live_over_binned():
    files = [
        df(f"{POOL}/desktops/deleted/u.qcow2", "u"),
        df(f"{POOL}/desktops/u.qcow2", "u"),
    ]
    assert best_file_by_uuid(files)["u"]["path"] == f"{POOL}/desktops/u.qcow2"


def test_uuids_sustaining_live_finds_the_backing_by_uuid_not_path():
    # the live child's stored backing path is stale; only a uuid map links them.
    files = [
        df(f"{POOL}/templates/moved/parent.qcow2", "parent"),
        df(
            f"{POOL}/desktops/child.qcow2",
            "child",
            "parent",
            f"{POOL}/templates/parent.qcow2",
        ),
    ]
    assert uuids_sustaining_live(files, {"child"}) == {"parent"}
    assert uuids_sustaining_live(files, set()) == set()


# ── qcow2 header reader ───────────────────────────────────────────────────────


def _write_qcow2(path, backing=None, backing_off=512, total=1024):
    buf = bytearray(total)
    buf[0:4] = b"QFI\xfb"
    struct.pack_into(">I", buf, 4, 3)
    if backing is not None:
        b = backing.encode()
        struct.pack_into(">Q", buf, 8, backing_off)
        struct.pack_into(">I", buf, 16, len(b))
        buf[backing_off : backing_off + len(b)] = b
    Path(path).write_bytes(bytes(buf))


def test_read_backing_from_header(tmp_path):
    p = tmp_path / "d.qcow2"
    _write_qcow2(p, backing="/isard/templates/base.qcow2")
    assert read_qcow2_backing(str(p)) == ("/isard/templates/base.qcow2", True)


def test_read_backing_none_when_root(tmp_path):
    p = tmp_path / "root.qcow2"
    _write_qcow2(p, backing=None)
    assert read_qcow2_backing(str(p)) == (None, True)


def test_read_backing_non_qcow2_is_unreadable(tmp_path):
    p = tmp_path / "notq.qcow2"
    p.write_bytes(b"NOTQCOW2" + b"\x00" * 100)
    assert read_qcow2_backing(str(p)) == (None, False)


def test_read_backing_seek_fallback_beyond_first_read(tmp_path):
    # backing string past the 64 KiB up-front read forces the seek path.
    p = tmp_path / "far.qcow2"
    _write_qcow2(
        p, backing="/isard/templates/far.qcow2", backing_off=70000, total=71000
    )
    assert read_qcow2_backing(str(p)) == ("/isard/templates/far.qcow2", True)


def test_build_backing_index_reads_uuid_and_backing(tmp_path):
    parent = tmp_path / "11111111-1111-1111-1111-111111111111.qcow2"
    child = tmp_path / "22222222-2222-2222-2222-222222222222.qcow2"
    _write_qcow2(parent, backing=None)
    _write_qcow2(child, backing=str(parent))
    idx = build_backing_index([str(parent), str(child)])
    assert idx[str(child)]["backing_uuid"] == "11111111-1111-1111-1111-111111111111"
    assert idx[str(parent)]["backing_uuid"] is None
