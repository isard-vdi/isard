# SPDX-License-Identifier: AGPL-3.0-or-later

"""The disk-creation entry points hand back the task they just enqueued.

Retiring the row pointer changed ``create_task`` from *stamping* ``self.task``
to *returning* the id. Every caller that used to read the field back had to
start reading the return value, and these two did not: they discarded what
``create_task`` returned and kept reading the scalar, which is now never
written. Both therefore answered ``(storage, None)``.

That is not a cosmetic ``None``. ``POST /item/storage/priority/{priority}``
feeds the tuple straight into ``StorageCreateResponse``, whose ``task_id`` is a
required ``str``; the validation error is caught by the route's blanket
``except Exception`` and served as **500 — for every input** — *after* the row
and the qcow2 have already been created. The caller never learns the id, so
nothing ever reclaims the disk: one orphan per attempt.

Why the existing suite was green through all of it: every other test of these
paths patches ``create_task`` (or the whole chain enqueuer) out at class level,
so the line under test never ran and a mock's return value stood in for the
thing that was broken. These tests patch one seam lower — at ``Task``, the
object that actually mints the job — so the real ``create_task`` and the real
entry-point bodies both execute, and the assertion is on what the caller gets
back rather than on what a mock was told.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.models.storage import Storage

TASK_ID = "the-job-that-was-just-enqueued"


def _new_disk():
    """A bare ``Storage`` carrying only what the bodies under test read.

    Fields go straight into ``__dict__``: ``Storage`` resolves unknown
    attributes through ``__getattr__`` (a query) and writes them through
    ``__setattr__`` (an update), neither of which may touch a database here.
    ``task`` is deliberately left absent-but-readable as ``None``: that is
    exactly the retired scalar's production value, and it is what the bug read.
    """
    disk = Storage.__new__(Storage)
    disk.__dict__.update(
        {
            "id": "disk-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": None,
            "path": "/isard/groups/disk-1.qcow2",
            "directory_path": "/isard/groups",
            "task": None,
        }
    )
    return disk


@pytest.fixture
def minted():
    """Run the real bodies with ``Task`` stubbed, and expose the disk built."""
    disk = _new_disk()
    pool = MagicMock()
    pool.id = "pool-1"

    def _task(*args, **kwargs):
        built = MagicMock()
        built.id = TASK_ID
        return built

    with patch("isardvdi_common.models.storage.Task", side_effect=_task) as Task, patch(
        "isardvdi_common.models.storage.queue_coverage.enforce_shed"
    ), patch.object(Storage, "new_dict", return_value=disk), patch.object(
        Storage, "set_maintenance"
    ), patch.object(
        Storage, "pool", pool
    ), patch.object(
        Storage, "category", "cat-1"
    ), patch.object(
        Storage, "__setattr__", lambda self, name, value: None
    ):
        Task.exists.return_value = False
        Task._redis = MagicMock()
        yield disk


class TestCreateNewStorage:
    def test_returns_the_task_it_enqueued(self, minted):
        """The contract the API response model depends on."""
        storage, task_id = Storage.create_new_storage(
            user_id="u-1",
            pool_usage="desktop",
            parent_id=None,
            size="10",
        )
        assert storage is minted
        assert task_id == TASK_ID

    def test_does_not_answer_none(self, minted):
        """Stated separately and on purpose.

        ``task_id is None`` is the whole defect, and it is what a required
        ``str`` field rejects. A future refactor that returns some other
        falsy placeholder would still break the route, so pin the shape as
        well as the value.
        """
        _, task_id = Storage.create_new_storage(
            user_id="u-1",
            pool_usage="desktop",
            parent_id=None,
            size="10",
        )
        assert task_id is not None
        assert isinstance(task_id, str)

    def test_does_not_read_the_retired_scalar(self, minted):
        """Guard against the fix being written as a re-stamp.

        Making ``create_task`` write ``self.task`` again would turn these
        green while reinstating the pointer this whole MR removes, so assert
        the row's field stays unwritten and the id comes from the return value.
        """
        _, task_id = Storage.create_new_storage(
            user_id="u-1",
            pool_usage="desktop",
            parent_id=None,
            size="10",
        )
        assert minted.__dict__["task"] is None
        assert task_id == TASK_ID


class TestCreateNewStorageForDomain:
    """The sibling entry point, broken the same way for the same reason.

    It discards what ``enqueue_disk_creation_chain_for_domain`` returns — a
    method whose docstring already promises the root task id — and then reads
    the same retired scalar.
    """

    def test_returns_the_root_task_of_the_chain(self, minted):
        with patch.object(
            Storage,
            "enqueue_disk_creation_chain_for_domain",
            return_value=TASK_ID,
        ):
            storage, task_id = Storage.create_new_storage_for_domain(
                domain_id="dom-1",
                user_id="u-1",
                pool_usage="desktop",
            )
        assert storage is minted
        assert task_id == TASK_ID

    def test_does_not_answer_none(self, minted):
        with patch.object(
            Storage,
            "enqueue_disk_creation_chain_for_domain",
            return_value=TASK_ID,
        ):
            _, task_id = Storage.create_new_storage_for_domain(
                domain_id="dom-1",
                user_id="u-1",
                pool_usage="desktop",
            )
        assert task_id is not None
