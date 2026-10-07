# SPDX-License-Identifier: AGPL-3.0-or-later

"""The reconciliation must sort a pool's files/rows into the right classes, and
offer for auto-correction ONLY the size drift of ready storage rows."""

from storage_lib import reconcile

POOL = ("/isard/groups", "/isard/templates")
THRESHOLD = 64 << 20  # 64 MiB


def _scan(path, allocated, dirty=False, corrupt=False, virtual=10 << 30):
    return {
        path: {
            "path": path,
            "allocated": allocated,
            "apparent": allocated,
            "dev": 1,
            "ino": hash(path) & 0xFFFFFF,
            "virtual_size": virtual,
            "dirty": dirty,
            "corrupt": corrupt,
            "backing_file": None,
            "header_error": None,
        }
    }


class TestClassify:
    def test_ready_row_matching_size_is_clean(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/isard/groups/s1.qcow2",
                "status": "ready",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/isard/groups/s1.qcow2", 1_000_000)
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert all(out[k] == [] for k in out)

    def test_ready_row_size_drift_is_flagged_and_correctable(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/isard/groups/s1.qcow2",
                "status": "ready",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/isard/groups/s1.qcow2", 1_000_000 + (200 << 20))
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert [d["id"] for d in out["size_drift"]] == ["s1"]
        assert out["size_drift"][0]["drift"] == 200 << 20
        assert reconcile.correctable_ids(out) == ["s1"]

    def test_drift_within_threshold_is_not_flagged(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/isard/groups/s1.qcow2",
                "status": "ready",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/isard/groups/s1.qcow2", 1_000_000 + (10 << 20))  # < 64 MiB
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert out["size_drift"] == []

    def test_non_ready_drift_is_not_auto_corrected(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/isard/groups/s1.qcow2",
                "status": "recycled",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/isard/groups/s1.qcow2", 1_000_000 + (500 << 20))
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert out["size_drift"] == []
        assert reconcile.correctable_ids(out) == []

    def test_ready_row_without_file(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/isard/groups/gone.qcow2",
                "status": "ready",
                "db_size": 1_000_000,
            }
        ]
        out = reconcile.classify(rows, {}, POOL, THRESHOLD)
        assert [d["id"] for d in out["row_without_file"]] == ["s1"]

    def test_row_pointing_outside_the_pool(self):
        rows = [
            {
                "id": "s1",
                "kind": "storage",
                "path": "/other/pool/s1.qcow2",
                "status": "ready",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/other/pool/s1.qcow2", 1_000_000)
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert [d["id"] for d in out["row_on_other_pool"]] == ["s1"]
        assert out["size_drift"] == []  # not judged as drift: wrong pool

    def test_file_without_a_row(self):
        scan = _scan("/isard/groups/orphan.qcow2", 5 << 20)
        out = reconcile.classify([], scan, POOL, THRESHOLD)
        assert [d["path"] for d in out["file_without_row"]] == [
            "/isard/groups/orphan.qcow2"
        ]

    def test_recycle_bin_copy_is_not_a_rowless_file(self):
        scan = _scan("/isard/groups/deleted/old.qcow2", 5 << 20)
        out = reconcile.classify([], scan, POOL, THRESHOLD)
        assert out["file_without_row"] == []

    def test_dirty_or_corrupt_is_reported(self):
        scan = {}
        scan.update(_scan("/isard/groups/d.qcow2", 10, dirty=True))
        scan.update(_scan("/isard/groups/c.qcow2", 10, corrupt=True))
        out = reconcile.classify([], scan, POOL, THRESHOLD)
        flags = {d["path"]: (d["dirty"], d["corrupt"]) for d in out["dirty_or_corrupt"]}
        assert flags == {
            "/isard/groups/d.qcow2": (True, False),
            "/isard/groups/c.qcow2": (False, True),
        }

    def test_media_drift_is_classified_but_not_auto_corrected(self):
        rows = [
            {
                "id": "m1",
                "kind": "media",
                "path": "/isard/groups/m1.iso",
                "status": "Downloaded",
                "db_size": 1_000_000,
            }
        ]
        scan = _scan("/isard/groups/m1.iso", 1_000_000 + (200 << 20))
        out = reconcile.classify(rows, scan, POOL, THRESHOLD)
        assert [d["id"] for d in out["size_drift"]] == ["m1"]
        # media rows are reported, never re-measured through the storage path
        assert reconcile.correctable_ids(out) == []


class TestDriftMetrics:
    def test_aggregates_bytes_and_counts(self):
        out = {
            "size_drift": [
                {"id": "s1", "kind": "storage", "drift": 100},
                {"id": "s2", "kind": "storage", "drift": -50},
            ],
            "row_without_file": [{"id": "s3"}],
            "row_on_other_pool": [],
            "file_without_row": [{"path": "/x", "allocated": 7}],
            "dirty_or_corrupt": [{"path": "/y"}],
        }
        m = reconcile.drift_metrics("pool-a", out)
        assert m["size_drift_files"] == 2
        assert m["size_drift_bytes"] == 150
        assert m["row_without_file"] == 1
        assert m["file_without_row_bytes"] == 7
        assert m["dirty_or_corrupt"] == 1


class TestScan:
    def test_scan_file_on_a_non_qcow2_sets_header_error(self, tmp_path):
        p = tmp_path / "x.iso"
        p.write_bytes(b"\0" * 8192)
        info = reconcile.scan_file(str(p))
        assert info["header_error"] is not None
        assert info["virtual_size"] is None
        assert isinstance(info["allocated"], int)

    def test_scan_pool_respects_the_file_budget(self, tmp_path):
        for i in range(5):
            (tmp_path / f"f{i}.bin").write_bytes(b"\0" * 1024)
        scanned = reconcile.scan_pool([str(tmp_path)], max_files=3)
        assert scanned["_budget_hit"] is True
        assert len([k for k in scanned if k != "_budget_hit"]) == 3
