# SPDX-License-Identifier: AGPL-3.0-or-later

"""``move`` must ask the kernel whether it can rename, not predict it.

Every data directory the worker sees is its own bind mount, very often of the
same underlying device. ``st_dev`` is then equal on both sides while ``rename``
across them still raises ``EXDEV``, so the old probe chose the rename branch for
precisely the case that cannot rename -- and ``shutil.move`` turned the refused
rename into a whole-file copy with no free-space floor and no progress.

DB-free: ``_state_progress`` no-ops outside an rq job and is stubbed only to
observe it; the copy is stubbed too (it runs the floor the way a copy that
cannot clone does), so nothing is copied for real.
"""

import errno

import pytest


def _write(path, content=b"disk-bytes"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


@pytest.fixture
def worker(monkeypatch):
    """The module with the copy branch observable and never actually run."""
    from isardvdi_storage import task

    calls = {"guard": [], "copy": [], "progress": []}
    monkeypatch.setattr(
        task,
        "_require_free_space",
        lambda *a, **k: calls["guard"].append(a),
    )

    def _copy(origin, destination, **kwargs):
        if kwargs.get("before_copy") is not None:
            kwargs["before_copy"]()
        calls["copy"].append(((origin, destination), kwargs))
        return {"method": "sparse"}

    monkeypatch.setattr(task, "copy_disk_file", _copy)
    monkeypatch.setattr(
        task, "_state_progress", lambda payload: calls["progress"].append(payload)
    )
    return task, calls


def _exdev(monkeypatch, task):
    """Two bind mounts of one device: st_dev matches, rename is still refused."""

    def _refuse(origin, destination):
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(task, "rename", _refuse)


class TestExdevDegradesToAGuardedCopy:
    def test_the_copy_runs_the_free_space_guard(self, worker, monkeypatch, tmp_path):
        """The one case where a whole disk is copied without anyone asking for a
        copy, and the one case the floor did not cover."""
        task, calls = worker
        _exdev(monkeypatch, task)
        src = _write(tmp_path / "groups" / "d.qcow2")
        dst = tmp_path / "templates" / "d.qcow2"

        assert task.move(str(src), str(dst), "auto") == 0

        assert len(calls["guard"]) == 1
        target_dir, source_path, _floor, action, verb = calls["guard"][0]
        assert target_dir == str(dst.parent)
        assert source_path == str(src)
        assert (action, verb) == ("move", "copy")

    def test_the_copy_is_a_disk_copy_that_drops_the_source(
        self, worker, monkeypatch, tmp_path
    ):
        task, calls = worker
        _exdev(monkeypatch, task)
        src = _write(tmp_path / "groups" / "d.qcow2")
        dst = tmp_path / "templates" / "d.qcow2"

        task.move(str(src), str(dst), "auto")

        ((origin, destination), _kwargs) = calls["copy"][0]
        assert (origin, destination) == (str(src), str(dst))
        # move drops the source itself once the copy is whole and verified
        assert not src.exists()

    def test_the_copy_reports_progress(self, worker, monkeypatch, tmp_path):
        """Only the rename branch was wired to the row, and it reports nothing
        until it is done, so a degraded copy left the bar frozen."""
        task, calls = worker
        _exdev(monkeypatch, task)
        src = _write(tmp_path / "groups" / "d.qcow2")
        dst = tmp_path / "templates" / "d.qcow2"

        task.move(str(src), str(dst), "auto", progress_domain_id="dom-1")

        (_paths, kwargs) = calls["copy"][0]
        assert kwargs["on_progress"] is not None
        kwargs["on_progress"](0.42)
        assert calls["progress"] == [{"total_percent": 42, "received_percent": 42}]

    def test_an_explicit_mv_degrades_the_same_way(self, worker, monkeypatch, tmp_path):
        """``method="mv"`` is a request, not a promise that a rename is possible:
        the recycle-bin and directory moves pass it across mounts that cannot."""
        task, calls = worker
        _exdev(monkeypatch, task)
        src = _write(tmp_path / "groups" / "d.qcow2")
        dst = tmp_path / "templates" / "d.qcow2"

        assert task.move(str(src), str(dst), "mv") == 0

        assert len(calls["guard"]) == 1 and len(calls["copy"]) == 1


class TestWhatMustNotChange:
    def test_a_real_rename_is_used_and_never_guarded(self, worker, tmp_path):
        """A rename consumes no space, so the floor must never refuse one."""
        task, calls = worker
        src = _write(tmp_path / "a" / "d.qcow2")
        dst = tmp_path / "b" / "d.qcow2"

        assert task.move(str(src), str(dst), "auto") == 0

        assert dst.read_bytes() == b"disk-bytes" and not src.exists()
        assert calls["guard"] == [] and calls["copy"] == []

    def test_a_rename_still_reports_its_final_progress(self, worker, tmp_path):
        task, calls = worker
        src = _write(tmp_path / "a" / "d.qcow2")
        dst = tmp_path / "b" / "d.qcow2"

        task.move(str(src), str(dst), "auto", progress_domain_id="dom-1")

        assert calls["progress"] == [{"total_percent": 100, "received_percent": 100}]

    def test_a_non_exdev_error_is_not_swallowed(self, worker, monkeypatch, tmp_path):
        """EXDEV has a correct fallback; an unwritable destination does not, and
        reporting it as a copy failure buries the cause."""
        task, calls = worker
        src = _write(tmp_path / "a" / "d.qcow2")

        def _denied(origin, destination):
            raise OSError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(task, "rename", _denied)

        with pytest.raises(OSError) as excinfo:
            task.move(str(src), str(tmp_path / "b" / "d.qcow2"), "auto")

        assert excinfo.value.errno == errno.EACCES
        assert calls["copy"] == []

    def test_keeping_the_source_is_never_a_rename(self, worker, tmp_path):
        """A rename IS the removal of the source, so it cannot serve a caller
        that asked to keep it -- and ``shutil.move`` ran regardless."""
        task, calls = worker
        src = _write(tmp_path / "a" / "d.qcow2")
        dst = tmp_path / "b" / "d.qcow2"

        task.move(str(src), str(dst), "mv", remove_source_file=False)

        assert src.exists()
        assert len(calls["copy"]) == 1
