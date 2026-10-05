# SPDX-License-Identifier: AGPL-3.0-or-later

"""``storage space``: recorded size against allocated size, never against apparent size."""

from collections import namedtuple

from storage_lib import space

St = namedtuple("St", "st_size st_blocks st_dev st_ino")
GIB = 1 << 30


def _st(apparent, allocated, ino, dev=1):
    return St(apparent, allocated // 512, dev, ino)


def _row(sid, path, actual, status="ready"):
    return {
        "id": sid,
        "path": path,
        "status": status,
        "qemu-img-info": {"actual-size": actual},
    }


class TestDrift:
    def test_a_healthy_sparse_disk_does_not_drift(self):
        """100 GiB apparent, 4 GiB allocated, DB says 4 GiB: nothing to report."""
        rows = [_row("a", "/isard/t/a.qcow2", 4 * GIB)]
        fs = {"/isard/t/a.qcow2": _st(100 * GIB, 4 * GIB, 1)}
        assert space.size_drift(rows, fs, 64 << 20) == []

    def test_an_inflated_disk_drifts(self):
        rows = [_row("a", "/isard/t/a.qcow2", 2 * GIB)]
        fs = {"/isard/t/a.qcow2": _st(100 * GIB, 100 * GIB, 1)}
        [m] = space.size_drift(rows, fs, 64 << 20)
        assert (m["db_size"], m["real_size"], m["drift"]) == (
            2 * GIB,
            100 * GIB,
            98 * GIB,
        )

    def test_only_ready_rows_with_a_file(self):
        rows = [
            _row("a", "/x/a.qcow2", 0, status="recycled"),
            _row("b", "/x/b.qcow2", 0),
        ]
        fs = {"/x/a.qcow2": _st(GIB, GIB, 1)}
        assert space.size_drift(rows, fs, 1) == []


class TestReport:
    def test_counts_each_inode_once_and_splits_what_the_db_cannot_see(self):
        rows = [
            _row("a", "/isard/templates/a.qcow2", 1 * GIB),
            _row("r", "/isard/templates/r.qcow2", 0, status="recycled"),
        ]
        same = _st(10 * GIB, 3 * GIB, ino=7)
        fs = {
            "/isard/templates/a.qcow2": same,
            "/isard/storage_pools/fast/templates/a.qcow2": same,  # bind mount, same inode
            "/isard/templates/deleted/a.qcow2": _st(10 * GIB, 5 * GIB, ino=8),
            "/isard/templates/orphan.qcow2": _st(GIB, 2 * GIB, ino=9),
            "/isard/templates/r.qcow2": _st(GIB, 1 * GIB, ino=10),
        }
        acc = space.space_report(rows, fs, 64 << 20)["filesystems"][1]
        assert (acc["db_ready"], acc["ready_allocated"], acc["ready_files"]) == (
            1 * GIB,
            3 * GIB,
            1,
        )
        assert (acc["deleted_dir"], acc["deleted_dir_files"]) == (5 * GIB, 1)
        assert (acc["no_row"], acc["no_row_files"]) == (2 * GIB, 1)
        assert (acc["other_status"], acc["other_status_files"]) == (1 * GIB, 1)

    def test_filesystems_are_reported_apart(self):
        rows = [_row("a", "/f/a.qcow2", GIB), _row("b", "/s/b.qcow2", GIB)]
        fs = {
            "/f/a.qcow2": _st(GIB, GIB, 1, dev=1),
            "/s/b.qcow2": _st(GIB, GIB, 2, dev=2),
        }
        assert set(space.space_report(rows, fs)["filesystems"]) == {1, 2}
