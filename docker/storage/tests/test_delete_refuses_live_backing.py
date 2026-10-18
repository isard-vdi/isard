# SPDX-License-Identifier: AGPL-3.0-or-later

"""The recycle-bin purge must not unlink a base qcow2 that still backs a live
disk on disk -- including a child whose DB row carries no
``parent`` and is therefore invisible to the storage graph. The only place that
knows the on-disk truth is the worker, which reads the backing link from the
qcow2 header (72 bytes), so the guard lives next to the ``remove()``.

``on_disk_dependents`` is the pure, header-only answer to "who reads through
this file?"; ``delete``/``move_delete`` grow a ``covered_paths`` opt-in that the
purge passes so a child that is ITSELF part of the deletion never false-blocks.

Red on ``main``: ``on_disk_dependents`` does not exist and ``delete`` takes no
``covered_paths``; ``main`` unlinks the base regardless of what reads through it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "utils"))

from isardvdi_storage import task  # noqa: E402
from storage_lib.consistency import on_disk_dependents  # noqa: E402
from storage_lib.qcow import build_backing_index  # noqa: E402


def _mk(path, backing=None, unsafe=False):
    cmd = ["qemu-img", "create", "-f", "qcow2"]
    if backing is not None:
        if unsafe:
            cmd.append("-u")  # don't open the backing: lets it be absent/stale
        cmd += ["-b", str(backing), "-F", "qcow2"]
    cmd += [str(path), "64M"]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path)


class TestOnDiskDependents:
    def test_detects_a_header_only_child(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        deps, unreadable = on_disk_dependents(
            base, build_backing_index([base, child]), covered_paths=[]
        )
        assert deps == [child]
        assert unreadable == []

    def test_a_covered_child_is_not_a_blocker(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        child = _mk(tmp_path / "child.qcow2", backing=base)
        deps, _ = on_disk_dependents(
            base, build_backing_index([base, child]), covered_paths=[child]
        )
        assert deps == []

    def test_an_unrelated_disk_is_not_a_dependent(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        other = _mk(tmp_path / "other.qcow2")
        deps, _ = on_disk_dependents(
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
        deps, _ = on_disk_dependents(
            base, build_backing_index([base, child]), covered_paths=[]
        )
        assert deps == [child]

    def test_an_unreadable_candidate_is_reported_not_treated_as_safe(self, tmp_path):
        base = _mk(tmp_path / "base.qcow2")
        junk = tmp_path / "junk.qcow2"
        junk.write_bytes(b"not a qcow2 at all")
        deps, unreadable = on_disk_dependents(
            base, build_backing_index([base, str(junk)]), covered_paths=[]
        )
        assert deps == []
        assert str(junk) in unreadable


class TestDeleteRefusesLiveBacking:
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

    def test_delete_without_covered_paths_is_unguarded(self, tmp_path):
        """Control + backward-compat: the direct delete path (already DB-guarded
        by ``set_maintenance``) passes no ``covered_paths`` and is unchanged."""
        base = _mk(tmp_path / "base.qcow2")
        _mk(tmp_path / "child.qcow2", backing=base)
        task.delete(base)
        assert not Path(base).exists()
