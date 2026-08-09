# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on the disk lifecycle ops: create / move_delete / convert / media check.

* create: an existing destination is idempotent success and qemu-img is NEVER
  run again (so a re-enqueued chain can't clobber a live disk); an
  extended_l2 cluster size below 16k is rejected.
* move_delete: an existing disk is moved into the sibling ``deleted/`` dir; a
  missing path is rejected.
* convert: an unknown output format is rejected before any qemu-img runs.
* check_media_existence: file present -> Downloaded/100, absent -> deleted.

DB-free: only filesystem helpers and the ``run`` subprocess are stubbed.
"""

import pytest


class _Proc:
    returncode = 0


class TestCreate:
    def test_existing_dest_is_idempotent_and_never_runs_qemu(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: True)  # already exists
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a) or _Proc())
        assert task.create("/isard/g/d.qcow2", "qcow2") == 0
        assert ran == []  # qemu-img create must NOT run over an existing disk

    def test_extended_l2_cluster_too_small_rejected(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        monkeypatch.setenv("QCOW2_EXTENDED_L2", "on")
        monkeypatch.setenv("QCOW2_CLUSTER_SIZE", "4k")  # < 16k
        with pytest.raises(ValueError):
            task.create("/isard/g/d.qcow2", "qcow2")

    def test_valid_create_runs_qemu(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        monkeypatch.setenv("QCOW2_EXTENDED_L2", "off")
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a[0]) or _Proc())
        assert task.create("/isard/g/d.qcow2", "qcow2") == 0
        assert ran and ran[0][:2] == ["qemu-img", "create"]


class TestMoveDelete:
    def test_moves_existing_disk_to_deleted_dir(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isfile", lambda p: True)
        monkeypatch.setattr(task, "isdir", lambda p: True)
        renamed = []
        monkeypatch.setattr(task, "rename", lambda a, b: renamed.append((a, b)))
        assert task.move_delete("/isard/g/d.qcow2") == 0
        assert renamed == [("/isard/g/d.qcow2", "/isard/g/deleted/d.qcow2")]

    def test_missing_path_rejected(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isfile", lambda p: False)
        with pytest.raises(ValueError):
            task.move_delete("/isard/g/d.qcow2")


class TestConvertFormatGuard:
    def test_invalid_format_rejected_before_running(self, monkeypatch):
        import task

        ran = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda *a, **k: ran.append(a) or 0
        )
        with pytest.raises(ValueError):
            task.convert("/isard/s.qcow2", "/isard/d.raw", "raw", False)
        assert ran == []  # rejected before any qemu-img convert


class TestCheckMediaExistence:
    def test_present_file_is_downloaded(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isfile", lambda p: True)
        media = task.check_media_existence("m-1", "/isard/media/x.iso")
        assert media["status"] == "Downloaded"
        assert media["total_percent"] == 100

    def test_absent_file_is_deleted(self, monkeypatch):
        import task

        monkeypatch.setattr(task, "isfile", lambda p: False)
        media = task.check_media_existence("m-1", "/isard/media/x.iso")
        assert media["status"] == "deleted"
