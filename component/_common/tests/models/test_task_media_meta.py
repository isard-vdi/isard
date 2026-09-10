# SPDX-License-Identifier: AGPL-3.0-or-later

"""The owning media, stamped into the rq job meta at creation.

The twin of the storage stamping: ``media.task`` has the same shape and the
same defect as ``storage.task``, so the media surface needs the same reverse
mapping — which disk or which media a task belongs to, answered from the job
rather than from a RethinkDB secondary index.

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
        Task(task="download_url", queue="storage.pool.default", **extra)
    return created


def _meta(created, index=0):
    return created[index][1]["meta"]


class TestMediaIdInMeta:
    def test_the_owning_media_is_stamped(self):
        created = _build(media_id="med-1")
        assert _meta(created)["media_id"] == "med-1"

    def test_a_task_that_owns_no_media_stamps_none(self):
        created = _build()
        assert _meta(created)["media_id"] is None

    def test_an_explicit_meta_is_not_overwritten(self):
        created = _build(
            media_id="med-1", job_kwargs={"meta": {"media_id": "med-override"}}
        )
        assert _meta(created)["media_id"] == "med-override"

    def test_dependents_inherit_the_owner(self):
        """A STORAGE dependent, deliberately: a ``core`` dependent is serialised
        into ``meta["core_finalize"]`` and builds no rq job at all, so it has no
        job meta to inherit into. The owner still descends to its knot children,
        which is what ``test_task_knot_owner`` covers."""
        created = _build(
            media_id="med-1",
            dependents=[{"queue": "storage.pool.default", "task": "qemu_img_info"}],
        )
        assert len(created) == 2
        assert all(kwargs["meta"]["media_id"] == "med-1" for _, kwargs in created)

    def test_a_dependent_may_name_its_own_owner(self):
        created = _build(
            media_id="med-1",
            dependents=[
                {
                    "queue": "storage.pool.default",
                    "task": "qemu_img_info",
                    "media_id": "med-2",
                }
            ],
        )
        assert [kwargs["meta"]["media_id"] for _, kwargs in created] == [
            "med-1",
            "med-2",
        ]

    def test_the_two_owner_kinds_are_independent(self):
        """A task belongs to a disk or to a media, never implicitly to both."""
        created = _build(storage_id="disk-1")
        assert _meta(created)["storage_id"] == "disk-1"
        assert _meta(created)["media_id"] is None
