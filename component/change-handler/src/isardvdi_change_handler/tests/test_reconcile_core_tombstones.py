# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the reconcile's side of the cancelled-chain contract.

Two things are pinned here:

* the reconcile must cancel a doomed orphan through ``Task.cancel`` — the
  chain-settling primitive — instead of RQ's raw ``job.cancel(
  enqueue_dependents=True)``, which promoted the chain's finalize dependents
  onto the consumerless ``core`` queue where they stayed QUEUED forever and
  wedged the storage behind a permanent ``storage_pending_task``;
* the debt already sitting on that queue (from before the fix, or from a
  dead-lettered entry) is swept, safely: only members whose chain is settled
  and that are old enough not to be somebody's live replay state.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rq.exceptions import InvalidJobOperation
from rq.job import JobStatus


def _dep(status=JobStatus.FINISHED, ended_secs_ago=600, created_secs_ago=None):
    ended = None
    if ended_secs_ago is not None:
        ended = datetime.now(timezone.utc) - timedelta(seconds=ended_secs_ago)
    created = None
    if created_secs_ago is not None:
        created = datetime.now(timezone.utc) - timedelta(seconds=created_secs_ago)
    return SimpleNamespace(
        job_status=status, job=SimpleNamespace(ended_at=ended, created_at=created)
    )


def _task(
    task_id="t1",
    *,
    task_name="storage_update",
    queue="core",
    dependencies=None,
    dependents=None,
    user_id="u1",
):
    job = MagicMock(name=f"job-{task_id}")
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        user_id=user_id,
        dependencies=dependencies if dependencies is not None else [_dep()],
        dependents=dependents or [],
        job=job,
        cancel=MagicMock(name=f"cancel-{task_id}"),
    )


class TestReconcileCancelsThroughTheChainPrimitive:
    @pytest.mark.asyncio
    async def test_doomed_orphan_is_canceled_via_task_cancel(self):
        """``Task.cancel`` settles the whole chain and promotes nothing.
        Calling rq's ``job.cancel(enqueue_dependents=True)`` here is what
        produced the permanent core-queue tombstones."""
        from isardvdi_change_handler.streams import reconcile

        orphan = _task(
            "stg1",
            queue="storage.default.maintenance",
            dependencies=[_dep(JobStatus.FAILED, 600)],
        )
        with (
            patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
            patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
        ):
            healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

        assert healed == 1
        orphan.cancel.assert_called_once_with()
        orphan.job.cancel.assert_not_called()
        rel.assert_not_awaited()


class TestCanceledDependenciesCanSettle:
    def test_canceled_dep_without_ended_at_ages_from_created_at(self):
        """rq never writes ``ended_at`` on a cancel, so a chain cancelled by
        the old code could never age out and its orphans were invisible to
        this pass forever."""
        from isardvdi_change_handler.streams import reconcile

        now = datetime.now(timezone.utc)
        task = _task(
            dependencies=[
                _dep(JobStatus.CANCELED, ended_secs_ago=None, created_secs_ago=600)
            ]
        )

        assert reconcile._deps_terminal_and_aged(task, now, 120) is True

    def test_recently_canceled_dep_is_still_within_grace(self):
        from isardvdi_change_handler.streams import reconcile

        now = datetime.now(timezone.utc)
        task = _task(
            dependencies=[
                _dep(JobStatus.CANCELED, ended_secs_ago=None, created_secs_ago=10)
            ]
        )

        assert reconcile._deps_terminal_and_aged(task, now, 120) is False

    def test_finished_dep_without_ended_at_is_still_invisible(self):
        """Deliberately unchanged: a FINISHED dep with no ``ended_at`` is one
        the consumer marked mid-flight, and it may still be the replay state
        of an entry being redelivered. Ageing it here would let the heal
        delete that state."""
        from isardvdi_change_handler.streams import reconcile

        now = datetime.now(timezone.utc)
        task = _task(
            dependencies=[
                _dep(JobStatus.FINISHED, ended_secs_ago=None, created_secs_ago=6000)
            ]
        )

        assert reconcile._deps_terminal_and_aged(task, now, 120) is False


class TestCoreOrphanHealIsGated:
    @pytest.mark.asyncio
    async def test_failed_dependency_blocks_the_storage_release(self):
        """Releasing the deferred storage children of a chain whose parent
        failed or was cancelled would run work for a dead operation."""
        from isardvdi_change_handler.streams import reconcile

        orphan = _task("core1", dependencies=[_dep(JobStatus.CANCELED, 600)])
        with (
            patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=True)),
            patch.object(reconcile, "_set_job_status", new=AsyncMock()),
            patch.object(
                reconcile, "_release_storage_dependents", new=AsyncMock()
            ) as rel,
        ):
            await reconcile._heal_core_orphan(AsyncMock(), orphan)

        rel.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_handler_keeps_the_replay_state(self):
        """The consumer keeps a chain's jobs when a handler fails so a
        redelivery can re-run it. The heal must honour the same rule instead
        of deleting the evidence."""
        from isardvdi_change_handler.streams import reconcile

        orphan = _task("core1", dependencies=[_dep(JobStatus.FINISHED, 600)])
        with (
            patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=False)),
            patch.object(reconcile, "_set_job_status", new=AsyncMock()),
            patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()),
        ):
            await reconcile._heal_core_orphan(AsyncMock(), orphan)

        orphan.job.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_successful_handler_still_deletes(self):
        from isardvdi_change_handler.streams import reconcile

        orphan = _task("core1", dependencies=[_dep(JobStatus.FINISHED, 600)])
        with (
            patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=True)),
            patch.object(reconcile, "_set_job_status", new=AsyncMock()),
            patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()),
        ):
            await reconcile._heal_core_orphan(AsyncMock(), orphan)

        orphan.job.delete.assert_called_once()


class TestCoreTombstoneReap:
    """Pass 1c: sweep the debt left on ``rq:queue:core``."""

    def _redis(self, ids):
        conn = MagicMock()
        conn.lrange.return_value = list(ids)
        return conn

    @pytest.mark.asyncio
    async def test_settled_and_aged_tombstone_is_healed(self):
        from isardvdi_change_handler.streams import reconcile

        conn = self._redis([b"ghost"])
        ghost = _task("ghost", dependencies=[_dep(JobStatus.CANCELED, 6000)])
        ghost.job.get_status.return_value = JobStatus.QUEUED
        ghost.job.enqueued_at = datetime.now(timezone.utc) - timedelta(seconds=6000)

        with (
            patch.object(reconcile, "_reap_connection", return_value=conn),
            patch.object(reconcile.Task, "exists", return_value=True),
            patch.object(reconcile, "Task", side_effect=lambda _id: ghost),
            patch.object(
                reconcile, "_heal_core_orphan", new=AsyncMock(return_value=1)
            ) as heal,
        ):
            reaped = await reconcile._reap_core_tombstones(AsyncMock())

        assert reaped == 1
        heal.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_young_tombstone_is_left_alone(self):
        """Inside the redelivery envelope a QUEUED core job may still be the
        replay state of an entry the consumer is retrying."""
        from isardvdi_change_handler.streams import reconcile

        conn = self._redis([b"fresh"])
        fresh = _task("fresh", dependencies=[_dep(JobStatus.CANCELED, 30)])
        fresh.job.get_status.return_value = JobStatus.QUEUED
        fresh.job.enqueued_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        with (
            patch.object(reconcile, "_reap_connection", return_value=conn),
            patch.object(reconcile.Task, "exists", return_value=True),
            patch.object(reconcile, "Task", side_effect=lambda _id: fresh),
            patch.object(
                reconcile, "_heal_core_orphan", new=AsyncMock(return_value=1)
            ) as heal,
        ):
            reaped = await reconcile._reap_core_tombstones(AsyncMock())

        assert reaped == 0
        heal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tombstone_with_a_live_dependency_is_left_alone(self):
        from isardvdi_change_handler.streams import reconcile

        conn = self._redis([b"busy"])
        busy = _task("busy", dependencies=[_dep(JobStatus.STARTED, None)])
        busy.job.get_status.return_value = JobStatus.QUEUED
        busy.job.enqueued_at = datetime.now(timezone.utc) - timedelta(seconds=6000)

        with (
            patch.object(reconcile, "_reap_connection", return_value=conn),
            patch.object(reconcile.Task, "exists", return_value=True),
            patch.object(reconcile, "Task", side_effect=lambda _id: busy),
            patch.object(
                reconcile, "_heal_core_orphan", new=AsyncMock(return_value=1)
            ) as heal,
        ):
            reaped = await reconcile._reap_core_tombstones(AsyncMock())

        assert reaped == 0
        heal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_id_without_a_job_hash_is_dropped_from_the_list(self):
        """A dangling id keeps the queue non-empty for ever and poisons every
        chain walk that meets it; there is no job left to heal."""
        from isardvdi_change_handler.streams import reconcile

        conn = self._redis([b"dangling"])

        with (
            patch.object(reconcile, "_reap_connection", return_value=conn),
            patch.object(reconcile.Task, "exists", return_value=False),
            patch.object(
                reconcile, "_heal_core_orphan", new=AsyncMock(return_value=1)
            ) as heal,
        ):
            reaped = await reconcile._reap_core_tombstones(AsyncMock())

        conn.lrem.assert_called_once()
        heal.assert_not_awaited()
        assert reaped == 1


class TestReleaseNeedsProvenSuccess:
    """Unknown is not success: only a provably FINISHED parent may release."""

    @pytest.mark.asyncio
    async def test_vanished_parent_is_settled_not_released(self):
        """A parent whose job data is gone may well have FAILED — releasing on
        it runs the next stage of a dead operation. Settling the chain instead
        finalises the row through the cancelled branch."""
        from isardvdi_change_handler.streams import reconcile

        class _GoneDep:
            """A dependency whose RQ job data was evicted: reading its status
            raises, exactly as rq does for a job whose hash is gone."""

            job = SimpleNamespace(ended_at=None, created_at=None)

            @property
            def job_status(self):
                raise InvalidJobOperation("Failed to retrieve status for job")

        orphan = _task(
            "stg1", queue="storage.default.maintenance", dependencies=[_GoneDep()]
        )

        with patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel:
            await reconcile._heal_storage_orphan(orphan)

        orphan.cancel.assert_called_once_with()
        rel.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_all_finished_parents_still_release(self):
        from isardvdi_change_handler.streams import reconcile

        orphan = _task(
            "stg1",
            queue="storage.default.maintenance",
            dependencies=[_dep(JobStatus.FINISHED, 600)],
        )

        with patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel:
            await reconcile._heal_storage_orphan(orphan)

        rel.assert_awaited_once_with(orphan)
        orphan.cancel.assert_not_called()
