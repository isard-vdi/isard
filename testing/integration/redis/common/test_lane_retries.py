# SPDX-License-Identifier: AGPL-3.0-or-later

"""A retry scheduled on a per-category lane runs again once it is due."""

from isardvdi_common.lib.governed_worker import GovernedWorker
from isardvdi_common.lib.result_job import ResultJob
from rq import Queue, Retry, SimpleWorker
from rq.job import JobStatus
from rq.registry import ScheduledJobRegistry

BASE = "storage.p1.background"
LANE = "storage.p1.cat1.background"


def _lane_job_scheduled_for_retry(connection):
    lane = Queue(LANE, connection=connection, job_class=ResultJob)
    job = lane.enqueue("builtins.int", "not a number", retry=Retry(max=1, interval=60))
    SimpleWorker([lane], connection=connection, job_class=ResultJob).work(burst=True)
    registry = ScheduledJobRegistry(queue=lane)
    assert job.get_status(refresh=True) == JobStatus.SCHEDULED
    return lane, registry, job


def _governed_worker(connection):
    return GovernedWorker(
        [Queue(BASE, connection=connection, job_class=ResultJob)],
        connection=connection,
        job_class=ResultJob,
    )


def test_a_due_retry_on_a_category_lane_is_enqueued(scratch_redis):
    lane, registry, job = _lane_job_scheduled_for_retry(scratch_redis)
    scratch_redis.zadd(registry.key, {job.id: 0})

    _governed_worker(scratch_redis)._enqueue_due_lane_retries()

    assert job.id in lane.get_job_ids()
    assert job.id not in registry.get_job_ids()


def test_a_retry_not_yet_due_stays_scheduled(scratch_redis):
    lane, registry, job = _lane_job_scheduled_for_retry(scratch_redis)

    _governed_worker(scratch_redis)._enqueue_due_lane_retries()

    assert job.id in registry.get_job_ids()
    assert job.id not in lane.get_job_ids()
