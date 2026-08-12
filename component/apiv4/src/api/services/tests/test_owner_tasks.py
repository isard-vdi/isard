#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Reading the per-owner task index — the half that makes it not write-only.

The index is a ZSET per row whose members are rq job ids. Turning that into
rows the caller can render must stay a bounded number of round trips: the
liveness sweep and the field read are each ONE pipelined batch, never one call
per member. Measured on a full index, per-member checks cost 12.9 ms against
1.4 ms, so this is a property worth pinning rather than a preference.
"""

from unittest.mock import MagicMock, patch

from api.services.tasks import TaskService


def _job(job_id, **meta):
    job = MagicMock(name=job_id)
    job.id = job_id
    job.func_name = "task.convert"
    job.origin = "storage.pool.default.default"
    job.meta = {"user_id": "u-1", "category_id": "cat-1", **meta}
    job.get_status.return_value = "finished"
    job.enqueued_at = None
    job.started_at = None
    job.ended_at = None
    return job


class TestOwnerTasks:
    def test_returns_a_flat_row_per_live_task(self):
        with patch(
            "api.services.tasks.owner_task_ids", return_value=["j-2", "j-1"]
        ), patch("api.services.tasks.Job") as Job:
            Job.fetch_many.return_value = [
                _job("j-2", storage_id="disk-1"),
                _job("j-1", storage_id="disk-1"),
            ]
            rows = TaskService.owner_tasks("disk-1")
        assert [row["id"] for row in rows] == ["j-2", "j-1"]
        assert rows[0]["storage_id"] == "disk-1"
        assert rows[0]["task"] == "convert"
        assert rows[0]["queue"] == "storage.pool.default.default"
        assert rows[0]["job_status"] == "finished"

    def test_reads_every_member_in_one_batch(self):
        """The property the measurement bought: one ``fetch_many`` for the whole
        index, not one fetch per member."""
        with patch(
            "api.services.tasks.owner_task_ids",
            return_value=[f"j-{n}" for n in range(50)],
        ), patch("api.services.tasks.Job") as Job:
            Job.fetch_many.return_value = [_job(f"j-{n}") for n in range(50)]
            TaskService.owner_tasks("disk-1")
        assert Job.fetch_many.call_count == 1
        assert Job.fetch.call_count == 0
        assert list(Job.fetch_many.call_args.args[0]) == [f"j-{n}" for n in range(50)]

    def test_an_empty_index_asks_redis_nothing_more(self):
        with patch("api.services.tasks.owner_task_ids", return_value=[]), patch(
            "api.services.tasks.Job"
        ) as Job:
            assert TaskService.owner_tasks("disk-1") == []
        assert Job.fetch_many.call_count == 0

    def test_a_member_that_died_between_the_two_batches_is_dropped(self):
        """``fetch_many`` answers ``None`` for a job that went away after the
        liveness sweep proved it. The row is dropped rather than rendered as a
        half-empty one."""
        with patch(
            "api.services.tasks.owner_task_ids", return_value=["j-2", "j-1"]
        ), patch("api.services.tasks.Job") as Job:
            Job.fetch_many.return_value = [None, _job("j-1")]
            rows = TaskService.owner_tasks("disk-1")
        assert [row["id"] for row in rows] == ["j-1"]

    def test_media_reads_its_own_index(self):
        with patch("api.services.tasks.owner_task_ids") as owner_task_ids, patch(
            "api.services.tasks.Job"
        ) as Job:
            owner_task_ids.return_value = []
            TaskService.owner_tasks("media-1", kind="media")
        assert owner_task_ids.call_args.kwargs["kind"] == "media"

    def test_a_redis_failure_is_an_empty_listing_not_a_500(self):
        """Bookkeeping beside the task: the reader degrades to "no rows" the
        same way the writer degrades to "not indexed"."""
        with patch("api.services.tasks.owner_task_ids", return_value=["j-1"]), patch(
            "api.services.tasks.Job"
        ) as Job:
            Job.fetch_many.side_effect = RuntimeError("redis down")
            assert TaskService.owner_tasks("disk-1") == []
