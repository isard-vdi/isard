# SPDX-License-Identifier: AGPL-3.0-or-later

"""The recycle-bin purge must not unlink a base qcow2 that still backs a live
disk on disk -- including a child whose DB row carries no ``parent`` and is
therefore invisible to the storage graph. The only place that knows the on-disk
truth is the worker, which reads the backing link from the qcow2 header, so the
guard lives next to the ``remove()``.

The guard asks the one dependents primitive (``dependents_of`` over a
``build_backing_index`` of the pool) "who reads through this file?";
``delete``/``move_delete`` grow a ``covered_paths`` opt-in the purge passes so a
child that is ITSELF part of the deletion never false-blocks.

Red without this change: ``delete`` takes no ``covered_paths`` and unlinks the
base regardless of what reads through it."""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))

from isardvdi_common.lib.storage.dependents import (  # noqa: E402
    build_backing_index,
    dependents_of,
)
from isardvdi_storage import task  # noqa: E402


def _mk(path, backing=None, unsafe=False):
    cmd = ["qemu-img", "create", "-f", "qcow2"]
    if backing is not None:
        if unsafe:
            cmd.append("-u")  # don't open the backing: lets it be absent/stale
        cmd += ["-b", str(backing), "-F", "qcow2"]
    cmd += [str(path), "64M"]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


class TestDependentsOverRealQcow2:
    def test_detects_a_header_only_child(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        deps, unreadable = dependents_of(
            base, build_backing_index([base, child]), covered_paths=[]
        )
        assert deps == [child]
        assert unreadable == []

    def test_a_covered_child_is_not_a_blocker(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        deps, _ = dependents_of(
            base, build_backing_index([base, child]), covered_paths=[child]
        )
        assert deps == []

    def test_an_unrelated_disk_is_not_a_dependent(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        other = _mk(tmp_path / "other.qcow2")
        deps, _ = dependents_of(
            base, build_backing_index([base, other]), covered_paths=[]
        )
        assert deps == []

    def test_matches_by_uuid_when_the_backing_path_is_stale(self, tmp_path):
        # move_disks-style: the child still records the OLD absolute backing
        # path (another directory), but the uuid in the filename resolves it.
        uuid = "a0a0a0a0-1111-2222-3333-a0a0a0a0a0a0"
        base = _mk(tmp_path / f"{uuid}.qcow2")
        stale = f"/isard/templates/old/{uuid}.qcow2"
        child = _mk(tmp_path / "child.qcow2", backing=stale, unsafe=True)
        deps, _ = dependents_of(
            base, build_backing_index([base, child]), covered_paths=[]
        )
        assert deps == [child]

    def test_an_unreadable_candidate_is_reported_not_treated_as_safe(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        junk = tmp_path / "junk.qcow2"
        junk.write_bytes(b"not a qcow2 at all")
        deps, unreadable = dependents_of(
            base, build_backing_index([base, str(junk)]), covered_paths=[]
        )
        assert deps == []
        assert str(junk) in unreadable


def test_dependent_candidates_excludes_deleted_and_to_delete(monkeypatch):
    """C3 at the source: the guard's candidate list drops ``deleted/`` (move_
    delete's target) and ``to_delete/`` (cleanup's), and non-qcow2 files. Red on
    main: only ``*.qcow2`` was filtered, so a ``deleted/`` child was a candidate."""
    import storage_lib.scanning as scanning

    paths = [
        "/isard/templates/a.qcow2",
        "/isard/groups/x/deleted/b.qcow2",
        "/isard/groups/y/to_delete/c.qcow2",
        "/isard/volatile/d.qcow2",
        "/isard/groups/z/e.txt",
    ]
    monkeypatch.setattr(scanning, "scan_isard_dirs", lambda *a, **k: list(paths))
    got = task._dependent_candidates()
    assert "/isard/templates/a.qcow2" in got
    assert "/isard/volatile/d.qcow2" in got
    assert all("/deleted/" not in p for p in got)
    assert all("/to_delete/" not in p for p in got)
    assert "/isard/groups/z/e.txt" not in got


class _FakeHashRedis:
    """A dict-backed stand-in for the hash ops the shared index uses."""

    def __init__(self):
        self.h = {}

    def hgetall(self, key):
        return dict(self.h.get(key, {}))

    def hmget(self, key, fields):
        d = self.h.get(key, {})
        return [d.get(f) for f in fields]

    def hset(self, key, mapping=None, **kw):
        d = self.h.setdefault(key, {})
        if mapping:
            d.update(
                {
                    k: (v.encode() if isinstance(v, str) else v)
                    for k, v in mapping.items()
                }
            )
        return len(mapping or {})

    def expire(self, key, ttl):
        return True

    def hdel(self, key, *fields):
        d = self.h.get(key, {})
        return sum(1 for f in fields if d.pop(f, None) is not None)


class TestDeleteRefusesLiveBacking:
    @pytest.fixture(autouse=True)
    def _force_direct_scan(self, monkeypatch):
        # No Redis in these cases: exercise the direct-scan fallback so the
        # guard decision is hermetic. The cache path has its own test below.
        monkeypatch.setattr(task, "_redis_connection", lambda: None)

    def test_delete_refuses_a_base_that_still_backs_a_live_disk(
        self, tmp_path, monkeypatch
    ):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child])
        with pytest.raises(task.BackingInUseError):
            task.delete(base, covered_paths=[])
        # The red line: the base file is still there.
        assert Path(base).exists()

    def test_move_delete_refuses_too(self, tmp_path, monkeypatch):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child])
        with pytest.raises(task.BackingInUseError):
            task.move_delete(base, covered_paths=[])
        assert Path(base).exists()

    def test_delete_proceeds_when_the_only_child_is_covered(
        self, tmp_path, monkeypatch
    ):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child])
        task.delete(base, covered_paths=[child])
        assert not Path(base).exists()

    def test_delete_proceeds_for_a_leaf(self, tmp_path, monkeypatch):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, child])
        # Deleting the leaf child is fine: nothing reads through it.
        task.delete(child, covered_paths=[])
        assert not Path(child).exists()

    def test_an_unreadable_candidate_does_not_block_the_purge(
        self, tmp_path, monkeypatch
    ):
        # A live child is always a readable qcow2, so an unreadable candidate
        # cannot be one. Blocking on it (a disk mid-creation, a placeholder)
        # would strand every purge, so it is logged, not blocked.
        base = _mk(tmp_path / "base.qcow2")
        junk = tmp_path / "corrupt.qcow2"
        junk.write_bytes(b"not a qcow2 at all")
        monkeypatch.setattr(task, "_dependent_candidates", lambda: [base, str(junk)])
        task.delete(base, covered_paths=[])
        assert not Path(base).exists()

    def test_a_readable_child_still_blocks_despite_an_unreadable_sibling(
        self, tmp_path, monkeypatch
    ):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        junk = tmp_path / "corrupt.qcow2"
        junk.write_bytes(b"not a qcow2 at all")
        monkeypatch.setattr(
            task, "_dependent_candidates", lambda: [base, child, str(junk)]
        )
        with pytest.raises(task.BackingInUseError):
            task.delete(base, covered_paths=[])
        assert Path(base).exists()

    def test_delete_without_covered_paths_is_unguarded(self, tmp_path):
        """Control + backward-compat: the direct delete path (already DB-guarded
        by ``set_maintenance``) passes no ``covered_paths`` and is unchanged."""
        base = _mk(tmp_path / "base.qcow2")
        _mk(tmp_path / "child.qcow2", backing=base)
        task.delete(base)
        assert not Path(base).exists()

    def test_a_move_deleted_child_does_not_block_its_base(self, tmp_path, monkeypatch):
        """a child parked under a sibling ``deleted/`` dir by ``move_delete``
        is itself deleted and must not pin its base's purge. Red on main: the
        scan did not exclude ``deleted/``, so the moved child was counted as a
        live dependent and the base could never be purged. Here
        ``_dependent_candidates`` runs for real over a faked scan."""
        import storage_lib.scanning as scanning

        base = _mk(tmp_path / "base.qcow2")
        deleted = tmp_path / "deleted"
        deleted.mkdir()
        moved_child = _mk(deleted / "child.qcow2", backing=base)
        monkeypatch.setattr(
            scanning, "scan_isard_dirs", lambda *a, **k: [base, moved_child]
        )
        task.delete(base, covered_paths=[])  # must NOT raise
        assert not Path(base).exists()


class TestSharedIndexScales:
    def test_headers_are_read_once_and_shared_across_deletes(
        self, tmp_path, monkeypatch
    ):
        """The pool's headers are read once and SHARED through Redis, not re-read
        per delete: a second delete in the warmed window re-reads no header. (The
        partial-build-survives-a-timeout property, which is what actually fixes
        the 45k-file incident, is covered by the _common primitive's unit tests.)

        Red before the incremental index: the old whole-index cache only wrote
        after the full build completed, so on a large estate it never cached and
        every delete re-read every header."""
        from isardvdi_common.lib.storage import dependents as dep

        uid = "a0a0a0a0-0000-0000-0000-{:012d}"
        base = _mk(tmp_path / f"{uid.format(1)}.qcow2")
        _mk(tmp_path / f"{uid.format(2)}.qcow2", backing=base)  # child
        _mk(tmp_path / f"{uid.format(3)}.qcow2")  # an unrelated leaf
        candidates = [
            str(tmp_path / f"{uid.format(1)}.qcow2"),
            str(tmp_path / f"{uid.format(2)}.qcow2"),
            str(tmp_path / f"{uid.format(3)}.qcow2"),
        ]
        reads = {"n": 0}
        real_read = dep.read_backing

        def counting_read(path, *a, **k):
            reads["n"] += 1
            return real_read(path, *a, **k)

        monkeypatch.setattr(dep, "read_backing", counting_read)
        monkeypatch.setattr(task, "_dependent_candidates", lambda: list(candidates))
        monkeypatch.setattr(task, "_redis_connection", lambda: _FakeHashRedis())
        # one shared fake across both deletes
        shared = _FakeHashRedis()
        monkeypatch.setattr(task, "_redis_connection", lambda: shared)

        with pytest.raises(task.BackingInUseError):
            task.delete(base, covered_paths=[])  # builds the index (reads 3 headers)
        after_first = reads["n"]
        assert after_first == 3
        with pytest.raises(task.BackingInUseError):
            task.delete(base, covered_paths=[])  # cache warm: no header re-read
        assert reads["n"] == after_first  # zero additional header reads
        assert Path(base).exists()
