#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Media.delete_file`` must never leave a row it refused to delete in a
state nobody can delete afterwards, and must never mark a file deleted
while the file is still on disk.

Both were real: the method flipped the row to ``maintenance`` *before*
enqueueing, so a refusal from the queue stranded it there; and rows at
``DownloadFailed`` / ``DownloadFailedInvalidFormat`` were short-circuited
to ``deleted`` without ever asking anyone to unlink the file.

``Media`` is built with ``__new__`` and its persisted attributes are held
in a plain dict, so no database is touched.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.media import Media
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task


class _FakeMedia(Media):
    """A media row whose attributes live in memory."""

    def __init__(self, status, path_downloaded="/isard/media/m.iso", task=None):
        object.__setattr__(self, "_values", {})
        self._values.update(
            {
                "id": "m-1",
                "status": status,
                "path_downloaded": path_downloaded,
                "task": task,
            }
        )
        self.created_tasks = []

    def __getattr__(self, name):
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        if name in ("created_tasks", "create_task"):
            object.__setattr__(self, name, value)
        else:
            self._values[name] = value

    def create_task(self, **kwargs):
        self.created_tasks.append(kwargs)
        self._values["task"] = "task-1"


@pytest.fixture(autouse=True)
def _no_pool(monkeypatch):
    pool = StoragePool.__new__(StoragePool)
    object.__setattr__(pool, "id", "pool-a")
    monkeypatch.setattr(
        StoragePool, "get_best_for_action", classmethod(lambda cls, *a, **k: pool)
    )
    monkeypatch.setattr(Task, "exists", staticmethod(lambda task_id: False))


@pytest.mark.parametrize("status", ["Downloading", "DownloadStarting", "Download"])
def test_a_running_download_is_refused_with_the_translated_code(status):
    media = _FakeMedia(status)
    with pytest.raises(Error) as raised:
        media.delete_file()
    assert raised.value.error["description_code"] == "media_should_not_be_downloading"
    assert media.status == status
    assert media.created_tasks == []


def test_deleting_an_already_deleted_row_is_a_no_op():
    media = _FakeMedia("deleted")
    assert media.delete_file() is None
    assert media.created_tasks == []


def test_a_row_without_a_path_never_had_a_file():
    media = _FakeMedia("DownloadFailed", path_downloaded="")
    assert media.delete_file() is None
    assert media.status == "deleted"
    assert media.created_tasks == []


@pytest.mark.parametrize(
    "status", ["Downloaded", "DownloadFailed", "DownloadFailedInvalidFormat"]
)
def test_every_status_that_owns_a_file_enqueues_a_real_delete(status):
    media = _FakeMedia(status)
    media.delete_file()
    assert len(media.created_tasks) == 1
    task = media.created_tasks[0]
    assert task["task"] == "delete"
    assert task["job_kwargs"]["kwargs"]["path"] == "/isard/media/m.iso"
    assert media.status == "maintenance"


def test_keep_status_returns_the_row_to_where_it_was():
    media = _FakeMedia("DownloadFailedInvalidFormat")
    media.delete_file(keep_status=True)
    statuses = media.created_tasks[0]["dependents"][0]["job_kwargs"]["kwargs"][
        "statuses"
    ]
    assert "DownloadFailedInvalidFormat" in statuses["finished"]


def test_without_keep_status_the_row_ends_deleted():
    media = _FakeMedia("Downloaded")
    media.delete_file()
    statuses = media.created_tasks[0]["dependents"][0]["job_kwargs"]["kwargs"][
        "statuses"
    ]
    assert "deleted" in statuses["finished"]


def test_a_failed_delete_does_not_claim_the_row_is_downloaded():
    media = _FakeMedia("DownloadFailed")
    media.delete_file()
    statuses = media.created_tasks[0]["dependents"][0]["job_kwargs"]["kwargs"][
        "statuses"
    ]
    assert "DownloadFailed" in statuses["failed"]


def test_a_refused_enqueue_leaves_the_row_where_it_was(monkeypatch):
    """The bug that made rows undeletable: maintenance with no task."""
    media = _FakeMedia("Downloaded")

    def boom(**kwargs):
        raise Error("precondition_required", "queue is shedding")

    monkeypatch.setattr(media, "create_task", boom)
    with pytest.raises(Error):
        media.delete_file()
    assert media.status == "Downloaded"


def test_a_pending_task_is_refused_before_anything_is_written(monkeypatch):
    media = _FakeMedia("Downloaded", task="task-9")
    monkeypatch.setattr(Task, "exists", staticmethod(lambda task_id: True))
    monkeypatch.setattr(Task, "__init__", lambda self, task_id: None)
    monkeypatch.setattr(Task, "pending", property(lambda self: True))
    with pytest.raises(Error) as raised:
        media.delete_file()
    assert raised.value.error["description_code"] == "media_pending_task"
    assert media.status == "Downloaded"
