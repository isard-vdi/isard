# SPDX-License-Identifier: AGPL-3.0-or-later

"""A finished copy says so before ``move`` unlinks its source, which may fail or hang."""

import errno
import shutil

import pytest
from rq.timeouts import JobTimeoutException


class _Job:
    def __init__(self):
        self.meta = {}
        self.saved = []

    def save_meta(self):
        self.saved.append(dict(self.meta))


@pytest.fixture
def worker(monkeypatch, tmp_path):
    from isardvdi_storage import task

    job = _Job()
    monkeypatch.setattr(task, "get_current_job", lambda: job)
    monkeypatch.setattr(task, "_require_free_space", lambda *a, **k: None)
    rsync = []

    def _copy(argv, *a, **k):
        rsync.append(argv)
        shutil.copyfile(argv[-2], argv[-1])
        return 0

    monkeypatch.setattr(task, "run_with_progress", _copy)
    src = tmp_path / "groups" / "d.qcow2"
    src.parent.mkdir()
    src.write_bytes(b"disk-bytes")
    dst = tmp_path / "templates" / "t.qcow2"
    return task, job, rsync, src, dst


def _unlink_raises(monkeypatch, task, exc):
    seen = []

    def _remove(path):
        seen.append(path)
        raise exc

    monkeypatch.setattr(task, "remove", _remove)
    return seen


@pytest.mark.parametrize(
    "exc",
    [
        OSError(errno.EIO, "Input/output error"),
        OSError(errno.ESTALE, "Stale file handle"),
        JobTimeoutException("Task exceeded maximum timeout value (43200 seconds)"),
    ],
    ids=["EIO", "ESTALE", "timeout"],
)
def test_an_unlink_that_fails_after_the_copy_leaves_both_files_and_says_so(
    worker, monkeypatch, exc
):
    task, job, _rsync, src, dst = worker
    seen = _unlink_raises(monkeypatch, task, exc)

    with pytest.raises(type(exc)):
        task.move(str(src), str(dst), "rsync")

    assert seen == [str(src)]
    # saved before the unlink, so it is in Redis whatever the unlink did
    assert job.saved and job.saved[-1][task.COPY_COMPLETE_META_KEY] is True
    assert task.SOURCE_UNTOUCHED_META_KEY not in job.meta
    # nothing is deleted on the way out: the source and the whole copy remain
    assert src.read_bytes() == b"disk-bytes"
    assert dst.read_bytes() == b"disk-bytes"


def test_the_flag_is_saved_before_the_unlink_runs(worker, monkeypatch):
    """An unlink that never returns runs no code after it: the order is the fix."""
    task, job, _rsync, src, dst = worker
    order = []
    monkeypatch.setattr(
        job, "save_meta", lambda: order.append(("save", dict(job.meta)))
    )
    monkeypatch.setattr(task, "remove", lambda p: order.append(("unlink", p)))

    assert task.move(str(src), str(dst), "rsync") == 0

    assert [step for step, _ in order] == ["save", "unlink"]
    assert order[0][1][task.COPY_COMPLETE_META_KEY] is True


def test_rsync_does_not_remove_the_source_itself(worker):
    task, _job, rsync, src, dst = worker

    assert task.move(str(src), str(dst), "rsync") == 0

    assert "--remove-source-files" not in rsync[0]
    assert not src.exists() and dst.read_bytes() == b"disk-bytes"


def test_a_source_already_gone_is_the_unlink_done(worker, monkeypatch):
    """An NFS client replaying an unlink the server already did gets ENOENT."""
    task, job, _rsync, src, dst = worker
    _unlink_raises(monkeypatch, task, FileNotFoundError(errno.ENOENT, "gone"))

    assert task.move(str(src), str(dst), "rsync") == 0
    assert job.meta[task.COPY_COMPLETE_META_KEY] is True


def test_a_copy_that_did_not_end_never_claims_it_is_complete(worker, monkeypatch):
    task, job, _rsync, src, dst = worker
    monkeypatch.setattr(task, "run_with_progress", lambda *a, **k: 23)
    removed = []
    monkeypatch.setattr(task, "remove", removed.append)

    assert task.move(str(src), str(dst), "rsync") == 23

    assert removed == []
    assert task.COPY_COMPLETE_META_KEY not in job.meta
    assert src.exists()


def test_keeping_the_source_neither_unlinks_nor_flags(worker, monkeypatch):
    task, job, _rsync, src, dst = worker
    removed = []
    monkeypatch.setattr(task, "remove", removed.append)

    assert task.move(str(src), str(dst), "rsync", remove_source_file=False) == 0

    assert removed == []
    assert task.COPY_COMPLETE_META_KEY not in job.meta
