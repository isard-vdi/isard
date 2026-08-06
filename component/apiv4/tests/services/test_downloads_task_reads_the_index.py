# SPDX-License-Identifier: AGPL-3.0-or-later

"""The downloads abort/delete gate resolves its task through the index.

``_domain_storage_task`` read ``Storage(storage_id).task``. That was right when
it was written — on its own branch ``create_task`` still stamped the scalar —
and it only becomes a defect once the pointer retirement is underneath it, at
which point the field is never written and the helper answers ``None`` for
every download. ``_domain_action`` then computes ``pending = False`` always,
and both of its guards invert:

* **abort** stops cancelling. It takes the "no chain will ever finalize this
  row" branch, writes ``Failed``, and leaves the real task running.
* **delete** stops refusing. The ``download_task_pending`` precondition never
  fires, so a row is deleted out from under a live chain.

Both were reproduced against a live stack before this was written: with a
genuinely queued task, the abort endpoint answered 200, moved the domain to
``Failed``, and the task stayed ``JobStatus.QUEUED``.

The existing tests could not catch it because their double declares liveness
with the retired field (``SimpleNamespace(task="t-1")``), which nothing reads
any more — the same shape that hid the reconcile namespace defect. These
declare it where production looks: the per-owner index.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.services.admin.downloads import AdminDownloadsService
from isardvdi_common.helpers.error_factory import Error

LIVE_TASK = "task-in-flight"


def _domain(status="Downloading", storage_id="s-1"):
    return SimpleNamespace(
        id="d-1",
        status=status,
        kind="desktop",
        create_dict={"hardware": {"disks": [{"storage_id": storage_id}]}},
    )


class _Index:
    """Stand-in for the per-owner index: the one place that knows the task."""

    def __init__(self, task_id):
        self.task_id = task_id
        self.asked_for = []

    def __call__(self, _connection, owner_id, **kwargs):
        self.asked_for.append(owner_id)
        return self.task_id


def _harness(domain, index, task_pending=True):
    """Patch the models where the service looks them up, never ``__new__``.

    ``__new__`` does not round-trip under ``unittest.mock`` and poisons the
    class for the rest of the worker process; the neighbouring suite already
    carries that scar. Patch the plain module attributes instead.
    """
    cancelled = []

    domain_cls = MagicMock(name="DomainClass", return_value=domain)
    domain_cls.exists = lambda _id: True

    storage_cls = MagicMock(name="StorageClass")
    storage_cls.exists = lambda _id: True

    task_cls = MagicMock(
        name="TaskClass",
        return_value=SimpleNamespace(
            pending=task_pending, cancel=lambda: cancelled.append(True)
        ),
    )
    task_cls.exists = lambda _id: True
    task_cls._redis = MagicMock(name="redis")

    return (
        cancelled,
        (
            patch("api.services.admin.downloads.RethinkDomain", domain_cls),
            patch("api.services.admin.downloads.Task", task_cls),
            patch("api.services.admin.downloads.current_task_id", index),
            patch("isardvdi_common.models.storage.Storage", storage_cls),
        ),
    )


class TestTheHelperAsksTheIndex:
    def test_it_returns_the_task_the_index_holds(self):
        index = _Index(LIVE_TASK)
        _, patches = _harness(_domain(), index)
        with patches[0], patches[1], patches[2], patches[3]:
            assert AdminDownloadsService._domain_storage_task(_domain()) == LIVE_TASK

    def test_it_asks_about_the_disk_the_download_writes_into(self):
        index = _Index(LIVE_TASK)
        _, patches = _harness(_domain(storage_id="s-42"), index)
        with patches[0], patches[1], patches[2], patches[3]:
            AdminDownloadsService._domain_storage_task(_domain(storage_id="s-42"))
        assert index.asked_for == ["s-42"]

    def test_no_live_task_still_answers_none(self):
        """The empty answer has to stay reachable, or the guards jam shut."""
        index = _Index(None)
        _, patches = _harness(_domain(), index)
        with patches[0], patches[1], patches[2], patches[3]:
            assert AdminDownloadsService._domain_storage_task(_domain()) is None


class TestAbortCancelsTheLiveTask:
    def test_a_live_download_is_cancelled_not_buried(self):
        """The defect wrote ``Failed`` and left the task running."""
        domain = _domain("Downloading")
        index = _Index(LIVE_TASK)
        cancelled, patches = _harness(domain, index, task_pending=True)
        with patches[0], patches[1], patches[2], patches[3]:
            AdminDownloadsService._domain_action("abort", "d-1", "u1")
        assert cancelled == [True]
        assert domain.status == "DownloadAborting"

    def test_without_a_live_task_the_row_is_still_settled(self):
        """The other arm stays intact: nothing will finalize it, so it fails."""
        domain = _domain("Downloading")
        index = _Index(None)
        cancelled, patches = _harness(domain, index, task_pending=False)
        with patches[0], patches[1], patches[2], patches[3]:
            AdminDownloadsService._domain_action("abort", "d-1", "u1")
        assert cancelled == []
        assert domain.status == "Failed"


class TestDeleteRefusesWhileTheChainRuns:
    def test_a_pending_task_blocks_the_delete(self):
        domain = _domain("Failed")
        index = _Index(LIVE_TASK)
        _, patches = _harness(domain, index, task_pending=True)
        with patches[0], patches[1], patches[2], patches[3]:
            with pytest.raises(Error) as raised:
                AdminDownloadsService._domain_action("delete", "d-1", "u1")
        assert raised.value.error["description_code"] == "download_task_pending"
