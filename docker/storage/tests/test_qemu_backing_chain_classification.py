# SPDX-License-Identifier: AGPL-3.0-or-later

"""Disk-integrity classification in ``qemu_img_info_backing_chain``.

This turns a ``qemu-img info --backing-chain`` outcome into a storage
status, and that status drives whether a disk is treated as usable,
orphaned, or broken. A misclassification here marks a good disk broken or a
broken one ready, so the mapping is pinned:

* qemu-img timeout             -> unknown (raises, RQ retries)
* EIO / ESTALE / EAGAIN / EMFILE -> unknown (raises, RQ retries)
* rc 0                         -> ready (+ backing-filename keys defaulted)
* rc != 0, stderr unrecognized -> unknown (raises, RQ retries)
* "Could not open '<self>'", ENOENT and nothing at the path -> deleted
* "Could not open '<self>'" for any other reason, or with something at the
  path -> a reading without status that carries ``open_error``
* "Could not open '<parent>'" where parent is this disk's backing -> orphan
* "Could not open '<parent>'" where it is NOT the backing -> broken_chain
* unknown in a chain step with no retry left -> a reading without status

DB-free: it runs with no RQ job, and only the qemu-img subprocess (``run``) and the sibling ``qemu_img_info``
lookup are stubbed.
"""

from types import SimpleNamespace

import pytest


class _Proc:
    def __init__(self, returncode, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _backing(task, monkeypatch, path):
    monkeypatch.setattr(
        task,
        "qemu_img_info",
        lambda *a, **k: {"qemu-img-info": {"backing-filename": path}},
    )


def _job(monkeypatch, task, retries_left, dependency_ids):
    job = SimpleNamespace(
        retries_left=retries_left, meta={"dependency_ids": dependency_ids}
    )
    monkeypatch.setattr(task, "get_current_job", lambda: job)


def _hang(*a, **k):
    from isardvdi_storage import task

    raise task.TimeoutExpired(cmd="qemu-img", timeout=1)


def _open_error(path, reason):
    """What qemu-img prints when it cannot open ``path`` itself."""
    text = f"qemu-img: Could not open '{path}': Could not open '{path}': {reason}\n"
    return text.encode()


def _fails(monkeypatch, task, stderr):
    monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))


class TestUnknownInsideAChain:
    def test_last_attempt_of_a_chain_step_returns_no_status(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(task, "run", _hang)
        _job(monkeypatch, task, 0, ["create-step"])
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result == {"id": "st-1"}

    def test_unrecognised_stderr_in_a_chain_step_returns_no_status(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=b"EIO"))
        _job(monkeypatch, task, 0, ["create-step"])
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result == {"id": "st-1"}

    def test_chain_step_with_retries_left_still_raises(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(task, "run", _hang)
        _job(monkeypatch, task, 2, ["create-step"])
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_standalone_check_out_of_retries_still_raises(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(task, "run", _hang)
        _job(monkeypatch, task, 0, [])
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_missing_backing_file_in_a_chain_step_is_still_orphan(self, monkeypatch):
        from isardvdi_storage import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        _backing(task, monkeypatch, "/isard/parent.qcow2")
        _job(monkeypatch, task, 0, ["create-step"])
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "orphan"


class TestBackingChainClassification:
    def test_timeout_is_unknown(self, monkeypatch):
        from isardvdi_storage import task

        def _boom(*a, **k):
            raise task.TimeoutExpired(cmd="qemu-img", timeout=1)

        monkeypatch.setattr(task, "run", _boom)
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    @pytest.mark.parametrize(
        "reason",
        [
            b"Input/output error",
            b"Stale file handle",
            b"Resource temporarily unavailable",
            b"Connection timed out",
        ],
    )
    def test_transient_io_error_on_self_is_unknown(self, monkeypatch, reason):
        from isardvdi_storage import task

        stderr = (
            b"qemu-img: Could not open '/isard/x.qcow2': Could not open "
            b"'/isard/x.qcow2': " + reason + b"\n"
        )
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_transient_io_error_on_backing_is_unknown(self, monkeypatch):
        from isardvdi_storage import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': Stale file handle\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        _backing(task, monkeypatch, "/isard/parent.qcow2")
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_backing_probe_timeout_is_unknown(self, monkeypatch):
        from isardvdi_storage import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))

        def _hang(*a, **k):
            raise task.TimeoutExpired(cmd="qemu-img", timeout=1)

        monkeypatch.setattr(task, "qemu_img_info", _hang)
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_rc0_is_ready_with_defaults(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(
            task, "run", lambda *a, **k: _Proc(0, stdout=b'[{"virtual-size": 10}]')
        )
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "ready"
        assert "backing-filename" in result["qemu-img-info"]  # defaulted to None

    def test_unrecognized_stderr_is_unknown(self, monkeypatch):
        from isardvdi_storage import task

        monkeypatch.setattr(
            task, "run", lambda *a, **k: _Proc(1, stderr=b"some other error")
        )
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")

    def test_could_not_open_self_is_deleted(self, monkeypatch, tmp_path):
        from isardvdi_storage import task

        path = str(tmp_path / "x.qcow2")
        _fails(monkeypatch, task, _open_error(path, "No such file or directory"))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert result["status"] == "deleted"

    def test_could_not_open_missing_backing_is_orphan(self, monkeypatch):
        from isardvdi_storage import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        _backing(task, monkeypatch, "/isard/parent.qcow2")
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "orphan"

    def test_could_not_open_unrelated_path_is_broken_chain(self, monkeypatch):
        from isardvdi_storage import task

        stderr = b"qemu-img: Could not open '/isard/parent.qcow2': No such file\n"
        monkeypatch.setattr(task, "run", lambda *a, **k: _Proc(1, stderr=stderr))
        _backing(task, monkeypatch, "/isard/other.qcow2")
        result = task.qemu_img_info_backing_chain("st-1", "/isard/x.qcow2")
        assert result["status"] == "broken_chain"


def _disk(tmp_path):
    disk = tmp_path / "x.qcow2"
    disk.write_bytes(b"QFI\xfb")
    return str(disk)


class TestDeletedOnlyWhenTheFileIsGone:
    """``deleted`` only when qemu-img says ENOENT and lstat finds nothing there."""

    @pytest.mark.parametrize(
        "reason",
        [
            "Permission denied",
            "Operation not permitted",
            "Image is not in qcow2 format",
            "Is a directory",
        ],
    )
    def test_a_present_file_that_does_not_open_is_not_deleted(
        self, monkeypatch, tmp_path, reason
    ):
        from isardvdi_storage import task

        path = _disk(tmp_path)
        _fails(monkeypatch, task, _open_error(path, reason))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert "status" not in result
        assert result["id"] == "st-1"
        assert reason in result["open_error"]

    def test_enoent_for_a_file_that_is_there_is_not_deleted(
        self, monkeypatch, tmp_path
    ):
        from isardvdi_storage import task

        path = _disk(tmp_path)
        _fails(monkeypatch, task, _open_error(path, "No such file or directory"))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert "status" not in result
        assert "No such file or directory" in result["open_error"]

    def test_a_dangling_link_at_the_path_is_not_deleted(self, monkeypatch, tmp_path):
        from isardvdi_storage import task

        link = tmp_path / "x.qcow2"
        link.symlink_to(tmp_path / "moved.qcow2")
        _fails(monkeypatch, task, _open_error(str(link), "No such file or directory"))
        result = task.qemu_img_info_backing_chain("st-1", str(link))
        assert "status" not in result

    def test_a_missing_file_without_enoent_is_not_deleted(self, monkeypatch, tmp_path):
        from isardvdi_storage import task

        path = str(tmp_path / "x.qcow2")
        _fails(monkeypatch, task, _open_error(path, "Permission denied"))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert "status" not in result

    def test_an_lstat_error_other_than_enoent_is_no_proof(self, monkeypatch, tmp_path):
        """lstat through a regular file fails with ENOTDIR, not ENOENT."""
        from isardvdi_storage import task

        (tmp_path / "not-a-dir").write_bytes(b"")
        path = str(tmp_path / "not-a-dir" / "x.qcow2")
        _fails(monkeypatch, task, _open_error(path, "No such file or directory"))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert "status" not in result

    @pytest.mark.parametrize(
        "retries_left, dependency_ids",
        [(2, []), (0, []), (2, ["create-step"]), (0, ["create-step"])],
    )
    def test_an_open_error_is_returned_in_every_job_context(
        self, monkeypatch, tmp_path, retries_left, dependency_ids
    ):
        """No retry: the reading has to reach storage_update to flag the row."""
        from isardvdi_storage import task

        path = _disk(tmp_path)
        _job(monkeypatch, task, retries_left, dependency_ids)
        _fails(monkeypatch, task, _open_error(path, "Permission denied"))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert set(result) == {"id", "open_error"}

    @pytest.mark.parametrize(
        "reason", ["Too many open files", "No file descriptors available"]
    )
    def test_running_out_of_descriptors_is_transient(
        self, monkeypatch, tmp_path, reason
    ):
        from isardvdi_storage import task

        path = _disk(tmp_path)
        _fails(monkeypatch, task, _open_error(path, reason))
        with pytest.raises(task.BackingChainUnknown):
            task.qemu_img_info_backing_chain("st-1", path)

    def test_the_open_error_is_bounded(self, monkeypatch, tmp_path):
        from isardvdi_storage import task

        path = _disk(tmp_path)
        _fails(monkeypatch, task, _open_error(path, "Permission denied" * 100))
        result = task.qemu_img_info_backing_chain("st-1", path)
        assert len(result["open_error"]) <= task.OPEN_ERROR_MAX_CHARS
