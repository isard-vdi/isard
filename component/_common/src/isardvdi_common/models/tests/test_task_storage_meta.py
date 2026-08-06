# SPDX-License-Identifier: AGPL-3.0-or-later

"""The owning disk, stamped into the rq job ``meta`` at creation.

Answering "which disk does this task belong to" is done today with a RethinkDB
secondary index (``Storage.get_from_task_id``), read on every cancel, every
queue-position computation and every SocketIO task event. Carrying the owner in
the job itself answers the same question from the store the task already lives
in, and is what lets a cancel repair the right disk without touching that
index.

Mechanics tests — redis is mocked out; they pin the stamping contract.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task


def _build(**extra):
    """Run the real ``Task.__init__`` new-task path with ``Job``/``Queue``
    mocked so no redis is touched. Returns the kwargs handed to ``Job.create``."""
    created = []

    def _create(func_name, *args, **kwargs):
        job = MagicMock(name=f"job-{len(created)}")
        job.id = f"job-{len(created)}"
        job.meta = kwargs.get("meta", {})
        created.append((func_name, kwargs))
        return job

    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        Job.create.side_effect = _create
        Queue.return_value.enqueue_job.side_effect = lambda job: job
        Task(task="convert", queue="storage.pool.default", **extra)
    return created


def _meta(created, index=0):
    return created[index][1]["meta"]


class TestStorageIdInMeta:
    def test_the_owning_disk_is_stamped(self):
        created = _build(storage_id="disk-1")
        assert _meta(created)["storage_id"] == "disk-1"

    def test_a_task_that_owns_no_disk_stamps_none(self):
        """Same treatment as ``category_id``: the key is always present so a
        reader never has to distinguish "absent" from "no owner"."""
        created = _build()
        assert _meta(created)["storage_id"] is None

    def test_an_explicit_meta_is_not_overwritten(self):
        created = _build(
            storage_id="disk-1", job_kwargs={"meta": {"storage_id": "disk-override"}}
        )
        assert _meta(created)["storage_id"] == "disk-override"

    def test_dependents_inherit_the_owner(self):
        """A dependent belongs to the same row as the chain it hangs off, and
        the cancel path resolves the owner from whichever member it is handed.

        A STORAGE dependent, deliberately: a ``core`` dependent is serialised
        into ``meta["core_finalize"]`` and builds no rq job at all, so it has no
        job meta to inherit into. The owner still descends to its knot children,
        which is what ``test_task_knot_owner`` covers."""
        created = _build(
            storage_id="disk-1",
            dependents=[{"queue": "storage.pool.default", "task": "qemu_img_info"}],
        )
        assert len(created) == 2
        assert all(kwargs["meta"]["storage_id"] == "disk-1" for _, kwargs in created)

    def test_a_dependent_may_name_its_own_owner(self):
        created = _build(
            storage_id="disk-1",
            dependents=[
                {
                    "queue": "storage.pool.default",
                    "task": "qemu_img_info",
                    "storage_id": "disk-2",
                }
            ],
        )
        owners = [kwargs["meta"]["storage_id"] for _, kwargs in created]
        assert owners == ["disk-1", "disk-2"]

    def test_the_existing_owner_fields_still_land(self):
        created = _build(storage_id="disk-1", user_id="u-1", category_id="cat-1")
        meta = _meta(created)
        assert meta["user_id"] == "u-1"
        assert meta["category_id"] == "cat-1"
