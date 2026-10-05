# SPDX-License-Identifier: AGPL-3.0-or-later

"""A copying ``move`` keeps holes, and turns runs of zeros into holes, through the real rsync."""

import filecmp
import os
import shutil

import pytest

MIB = 1 << 20

pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")


def _allocated(path):
    return os.stat(path).st_blocks * 512


def _sparse_source(path, apparent=64 * MIB, data=2 * MIB):
    """A file the way qemu leaves a metadata-preallocated qcow2: data, then holes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(data))
        f.truncate(apparent)
    return path


def _inflated_source(path, apparent=64 * MIB, data=2 * MIB):
    """The same content with every hole written as zeros, the way the old copy left it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(os.urandom(data))
        f.write(b"\0" * (apparent - data))
    return path


class _Job:
    id = "job-1"
    func_name = "task.move"
    origin = "default"
    connection = object()

    def __init__(self):
        self.meta = {}

    def save_meta(self):
        pass


class _NeverCancelled:
    cancelled = False

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def task(monkeypatch):
    """The real rsync through ``run_with_progress``; only the rq job around it is faked."""
    from isardvdi_storage import task as task_module

    monkeypatch.setattr(task_module, "_state_progress", lambda payload: None)
    monkeypatch.setattr(task_module, "get_current_job", lambda: _Job())
    monkeypatch.setattr(task_module, "TaskCancelWatcher", _NeverCancelled)
    monkeypatch.setattr(task_module, "_publish_task_event", lambda *a, **k: None)
    return task_module


class TestCopyKeepsHoles:
    def test_a_sparse_disk_stays_sparse(self, task, tmp_path):
        src = _sparse_source(tmp_path / "groups" / "d.qcow2")
        dst = tmp_path / "templates" / "d.qcow2"
        reference = tmp_path / "reference"
        shutil.copyfile(src, reference)

        assert task.move(str(src), str(dst), "rsync", min_free_bytes=0) == 0

        assert filecmp.cmp(dst, reference, shallow=False)
        assert os.stat(dst).st_size == 64 * MIB
        assert _allocated(dst) < 8 * MIB, "the holes came back as written zeros"

    def test_an_inflated_disk_is_made_sparse_by_the_copy(self, task, tmp_path):
        """Disks already inflated by an earlier copy get their space back on the next move."""
        src = _inflated_source(tmp_path / "groups" / "d.qcow2")
        assert _allocated(src) >= 60 * MIB
        dst = tmp_path / "templates" / "d.qcow2"
        reference = tmp_path / "reference"
        shutil.copyfile(src, reference)

        assert task.move(str(src), str(dst), "rsync", min_free_bytes=0) == 0

        assert filecmp.cmp(dst, reference, shallow=False)
        assert (
            _allocated(dst) < 8 * MIB
        ), "runs of zeros were written instead of skipped"
