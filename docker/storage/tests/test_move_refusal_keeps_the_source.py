# SPDX-License-Identifier: AGPL-3.0-or-later

"""``move`` reserves what the sparse copy writes, and a refusal leaves the source untouched."""

from types import SimpleNamespace

import pytest

GIB = 1024**3


class _Job:
    def __init__(self):
        self.meta = {}
        self.saved = 0

    def save_meta(self):
        self.saved += 1


def _fs(monkeypatch, task, *, size, blocks, free):
    monkeypatch.setattr(task, "isfile", lambda p: "origin" in p)
    monkeypatch.setattr(task, "isdir", lambda p: True)
    monkeypatch.setattr(task, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(task, "_same_file", lambda a, b: False)
    monkeypatch.setattr(
        task, "os_stat", lambda p: SimpleNamespace(st_size=size, st_blocks=blocks)
    )
    monkeypatch.setattr(task, "_physical_free_space", lambda d: None)
    monkeypatch.setattr(task, "_free_space", lambda d: free)
    job = _Job()
    monkeypatch.setattr(task, "get_current_job", lambda: job)
    rsync = []
    monkeypatch.setattr(
        task, "run_with_progress", lambda *a, **k: rsync.append(a[0]) or 0
    )
    return job, rsync


def test_a_sparse_disk_that_fits_by_its_blocks_is_copied(monkeypatch):
    """10 GB apparent, 8 MiB real, 5 GiB free: the copy fits many times over."""
    from isardvdi_storage import task

    job, rsync = _fs(
        monkeypatch,
        task,
        size=10_747_904_000,
        blocks=(8 * 1024**2) // 512,
        free=5 * GIB,
    )
    assert (
        task.move(
            "/isard/groups/origin.qcow2",
            "/isard/templates/dest.qcow2",
            "rsync",
            min_free_bytes=1 * GIB,
        )
        == 0
    )
    assert rsync and rsync[0][0] == "rsync" and "--sparse" in rsync[0]
    assert task.SOURCE_UNTOUCHED_META_KEY not in job.meta


def test_a_refusal_states_the_source_untouched_and_copies_nothing(monkeypatch):
    """Really too big: refused, nothing run, and the job says the source is intact."""
    from isardvdi_storage import task

    job, rsync = _fs(
        monkeypatch, task, size=20 * GIB, blocks=(8 * GIB) // 512, free=5 * GIB
    )
    with pytest.raises(RuntimeError, match="move: refusing to copy"):
        task.move(
            "/isard/groups/origin.qcow2",
            "/isard/templates/dest.qcow2",
            "rsync",
            min_free_bytes=1 * GIB,
        )
    assert rsync == []
    assert job.meta[task.SOURCE_UNTOUCHED_META_KEY] is True
    assert job.saved == 1


def test_a_failed_copy_does_not_claim_the_source_untouched(monkeypatch):
    """Only the refusal before copying is stated; a copy that ran and failed is not."""
    from subprocess import CalledProcessError

    from isardvdi_storage import task

    job, _ = _fs(
        monkeypatch, task, size=1 * GIB, blocks=(1 * GIB) // 512, free=100 * GIB
    )

    def _rsync_fails(*a, **k):
        raise CalledProcessError(returncode=23, cmd=a[0])

    monkeypatch.setattr(task, "run_with_progress", _rsync_fails)
    with pytest.raises(CalledProcessError):
        task.move(
            "/isard/groups/origin.qcow2",
            "/isard/templates/dest.qcow2",
            "rsync",
            min_free_bytes=1 * GIB,
        )
    assert task.SOURCE_UNTOUCHED_META_KEY not in job.meta


def test_a_missing_source_does_not_claim_it_untouched(monkeypatch):
    from isardvdi_storage import task

    job, _ = _fs(monkeypatch, task, size=1, blocks=1, free=100 * GIB)
    with pytest.raises(ValueError):
        task.move("/isard/groups/gone.qcow2", "/isard/templates/dest.qcow2", "rsync")
    assert task.SOURCE_UNTOUCHED_META_KEY not in job.meta


def test_the_floor_without_sparse_copy_still_reserves_the_apparent_size(monkeypatch):
    """``convert`` and ``disconnect`` keep the conservative figure."""
    from isardvdi_storage import task

    _fs(monkeypatch, task, size=10 * GIB, blocks=(8 * 1024**2) // 512, free=5 * GIB)
    with pytest.raises(RuntimeError, match="refusing to convert"):
        task._require_free_space(
            "/isard/templates", "/x.qcow2", GIB, "convert", "convert"
        )


def test_blocks_above_the_apparent_size_are_capped_by_it(monkeypatch):
    """A fully allocated file can report a few more blocks than its size."""
    from isardvdi_storage import task

    _fs(
        monkeypatch,
        task,
        size=4 * GIB,
        blocks=(4 * GIB + 64 * 1024**2) // 512,
        free=5 * GIB,
    )
    # 5 GiB free - 4 GiB apparent = 1 GiB, exactly the floor: allowed
    task._require_free_space(
        "/isard/templates", "/x.qcow2", GIB, "move", "copy", sparse_copy=True
    )
