# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards / decisions in ``move`` (disk relocation).

* a missing origin is rejected (ValueError);
* an unknown method is rejected (ValueError);
* origin and destination are the same file -> remove the SOURCE (or keep it
  when remove_source_file is False), never copy onto itself;
* ``mv`` and ``auto`` both attempt the rename, and both degrade to the rsync
  branch when the kernel refuses it with EXDEV (see
  test_move_across_mounts.py for why the old st_dev probe could not see that).

DB-free: ``progress_domain_id`` is left None (the only Domain() touch), so
only filesystem helpers and ``run_with_progress`` are stubbed.
"""

import errno

import pytest


class _Stat:
    """Only the free-space guard reads a stat now; the branch decision does not."""

    def __init__(self, dev, size=1):
        self.st_dev = dev
        self.st_size = size


def _fs(monkeypatch, task, *, origin=True, dest=False, same=False):
    monkeypatch.setattr(task, "isfile", lambda p: origin if "origin" in p else dest)
    monkeypatch.setattr(task, "isdir", lambda p: True)
    monkeypatch.setattr(task, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(task, "_same_file", lambda a, b: same)


class TestMoveGuards:
    def test_missing_origin_rejected(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=False)
        with pytest.raises(ValueError):
            task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv")

    def test_invalid_method_rejected(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=False)
        with pytest.raises(ValueError) as exc:
            task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "teleport")
        assert "Invalid move method" in str(exc.value)

    def test_same_file_removes_source_only(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=True, same=True)
        removed = []
        monkeypatch.setattr(task, "remove", lambda p: removed.append(p))
        task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv")
        # the source is removed; the destination (the real file) is NEVER touched
        assert removed == ["/isard/origin.qcow2"]

    def test_same_file_keeps_source_when_asked(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=True, same=True)
        removed = []
        monkeypatch.setattr(task, "remove", lambda p: removed.append(p))
        assert (
            task.move(
                "/isard/origin.qcow2",
                "/isard/dest.qcow2",
                "mv",
                remove_source_file=False,
            )
            == 0
        )
        assert removed == []

    def test_mv_renames(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=False)
        renamed = []
        monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))
        assert task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv") == 0
        assert renamed == [("/isard/origin.qcow2", "/isard/dest.qcow2")]

    def test_auto_renames_when_the_kernel_allows_it(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=False)
        renamed = []
        monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))
        task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "auto")
        assert renamed == [("/isard/origin.qcow2", "/isard/dest.qcow2")]

    def test_exdev_falls_back_to_rsync(self, monkeypatch):
        from isardvdi_storage import task

        _fs(monkeypatch, task, origin=True, dest=False)

        def _refuse(a, b):
            raise OSError(errno.EXDEV, "Invalid cross-device link")

        monkeypatch.setattr(task, "rename", _refuse)
        # The fallback is a copy, so the floor now applies to it; the paths here
        # are fictional, so give the guard a filesystem it can read.
        monkeypatch.setattr(task, "os_stat", lambda p: _Stat(1))
        monkeypatch.setattr(task, "_free_space", lambda d: 1 << 40)
        rsync = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda *a, **k: rsync.append(a[0]) or 0
        )
        assert task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "auto") == 0
        assert rsync and rsync[0][0] == "rsync"
