# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards / decisions in ``move`` (disk relocation).

* a missing origin is rejected (ValueError);
* an unknown method is rejected (ValueError);
* origin and destination are the same file -> remove the SOURCE (or keep it
  when remove_source_file is False), never copy onto itself;
* ``mv`` does a shutil.move; ``auto`` picks mv/rsync by filesystem and falls
  back to rsync when the st_dev probe raises.

DB-free: ``progress_domain_id`` is left None (the only Domain() touch), so
only filesystem helpers and ``run_with_progress`` are stubbed.
"""

import pytest


class _Stat:
    def __init__(self, dev):
        self.st_dev = dev


def _fs(monkeypatch, task, *, origin=True, dest=False, same=False):
    monkeypatch.setattr(task, "isfile", lambda p: origin if "origin" in p else dest)
    monkeypatch.setattr(task, "isdir", lambda p: True)
    monkeypatch.setattr(task, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(task, "_same_file", lambda a, b: same)


class TestMoveGuards:
    def test_missing_origin_rejected(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=False)
        with pytest.raises(ValueError):
            task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv")

    def test_invalid_method_rejected(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=True, dest=False)
        with pytest.raises(ValueError) as exc:
            task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "teleport")
        assert "Invalid move method" in str(exc.value)

    def test_same_file_removes_source_only(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=True, dest=True, same=True)
        removed = []
        monkeypatch.setattr(task, "remove", lambda p: removed.append(p))
        task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv")
        # the source is removed; the destination (the real file) is NEVER touched
        assert removed == ["/isard/origin.qcow2"]

    def test_same_file_keeps_source_when_asked(self, monkeypatch):
        import task

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

    def test_mv_uses_shutil_move(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=True, dest=False)
        moved = []
        monkeypatch.setattr(task.shutil, "move", lambda a, b: moved.append((a, b)))
        assert task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "mv") == 0
        assert moved == [("/isard/origin.qcow2", "/isard/dest.qcow2")]

    def test_auto_same_fs_picks_mv(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=True, dest=False)
        monkeypatch.setattr(task, "os_stat", lambda p: _Stat(1))  # same device
        moved = []
        monkeypatch.setattr(task.shutil, "move", lambda a, b: moved.append((a, b)))
        task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "auto")
        assert moved == [("/isard/origin.qcow2", "/isard/dest.qcow2")]

    def test_auto_probe_error_falls_back_to_rsync(self, monkeypatch):
        import task

        _fs(monkeypatch, task, origin=True, dest=False)

        def _boom(p):
            raise OSError("cross-fs")

        monkeypatch.setattr(task, "os_stat", _boom)
        rsync = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda *a, **k: rsync.append(a[0]) or 0
        )
        assert task.move("/isard/origin.qcow2", "/isard/dest.qcow2", "auto") == 0
        assert rsync and rsync[0][0] == "rsync"
