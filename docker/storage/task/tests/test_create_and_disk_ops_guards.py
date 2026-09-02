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
    def test_existing_dest_is_idempotent_and_never_runs_qemu(self, monkeypatch, geo):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: True)  # already exists
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a) or _Proc())
        assert task.create("/isard/g/d.qcow2", "qcow2", **geo) == 0
        assert ran == []  # qemu-img create must NOT run over an existing disk

    def test_extended_l2_cluster_too_small_rejected(self, monkeypatch, geo):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        # The worker no longer reads the environment: the bad policy arrives in
        # the payload and is rejected by the shared validate().
        geo["extended_l2"] = "on"
        geo["cluster_size"] = "4k"  # < 16k
        with pytest.raises(ValueError):
            task.create("/isard/g/d.qcow2", "qcow2", **geo)

    def test_valid_create_runs_qemu(self, monkeypatch, geo):
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a[0]) or _Proc())
        assert task.create("/isard/g/d.qcow2", "qcow2", **geo) == 0
        assert ran and ran[0][:2] == ["qemu-img", "create"]


class TestGeometryIsRequired:
    @pytest.mark.parametrize(
        "missing", ["cluster_size", "extended_l2", "lazy_refcounts", "preallocation"]
    )
    def test_create_without_the_geometry_is_a_typeerror(
        self, monkeypatch, geo, missing
    ):
        """No environ.get, no defaults: a task enqueued by an older producer
        must die naming the argument, not silently write qemu-img defaults."""
        import task

        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a) or _Proc())
        geo.pop(missing)
        with pytest.raises(TypeError, match=missing):
            task.create("/isard/g/d.qcow2", "qcow2", **geo)
        assert ran == []  # nothing was written

    @pytest.mark.parametrize(
        "missing", ["cluster_size", "extended_l2", "lazy_refcounts", "preallocation"]
    )
    def test_convert_without_the_geometry_is_a_typeerror(
        self, monkeypatch, geo, missing
    ):
        import task

        monkeypatch.setattr(task, "_require_free_space", lambda *a, **k: None)
        ran = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda *a, **k: ran.append(a) or 0
        )
        geo.pop(missing)
        with pytest.raises(TypeError, match=missing):
            task.convert("/isard/s.qcow2", "/isard/d.qcow2", "qcow2", False, **geo)
        assert ran == []

    @pytest.mark.parametrize(
        "missing", ["cluster_size", "extended_l2", "lazy_refcounts", "preallocation"]
    )
    def test_disconnect_without_the_geometry_is_a_typeerror(
        self, monkeypatch, geo, missing
    ):
        import task

        monkeypatch.setattr(task, "_safe_unlink", lambda p: None)
        monkeypatch.setattr(task, "_require_free_space", lambda *a, **k: None)
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a) or _Proc())
        monkeypatch.setattr(task, "rename", lambda a, b: None)
        geo.pop(missing)
        with pytest.raises(TypeError, match=missing):
            task.disconnect("/isard/g/d.qcow2", **geo)
        assert ran == []

    def test_the_environment_is_never_consulted(self, monkeypatch, geo):
        """Deleting every QCOW2_* var must not change the argv."""
        import task

        for var in (
            "QCOW2_CLUSTER_SIZE",
            "QCOW2_EXTENDED_L2",
            "QCOW2_LAZY_REFCOUNTS",
            "QCOW2_PREALLOCATION",
        ):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(task, "isdir", lambda p: True)
        monkeypatch.setattr(task, "isfile", lambda p: False)
        ran = []
        monkeypatch.setattr(task, "run", lambda *a, **k: ran.append(a[0]) or _Proc())
        geo["cluster_size"] = "128k"
        task.create("/isard/g/d.qcow2", "qcow2", **geo)
        cmd = ran[0]
        assert "cluster_size=128k" in cmd[cmd.index("-o") + 1]


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
    def test_invalid_format_rejected_before_running(self, monkeypatch, geo):
        import task

        ran = []
        monkeypatch.setattr(
            task, "run_with_progress", lambda *a, **k: ran.append(a) or 0
        )
        with pytest.raises(ValueError):
            task.convert("/isard/s.qcow2", "/isard/d.raw", "raw", False, **geo)
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
