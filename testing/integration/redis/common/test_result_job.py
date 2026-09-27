# SPDX-License-Identifier: AGPL-3.0-or-later

"""A job's result event is committed with its outcome, whoever writes the outcome."""

from isardvdi_common.helpers.task_streams import RESULT_STREAM
from isardvdi_common.lib.result_job import ResultJob
from rq import Queue, Retry, SimpleWorker, Worker
from rq.job import JobStatus
from rq.registry import StartedJobRegistry
from rq.utils import current_timestamp

LANE = "storage.p1.default"


def _queue(connection):
    return Queue(LANE, connection=connection, job_class=ResultJob)


def _events(connection, job_id):
    events = []
    for _entry_id, fields in connection.xrange(RESULT_STREAM):
        fields = {k.decode(): v.decode() for k, v in fields.items()}
        if fields.get("task_id") == job_id:
            events.append(fields)
    return events


def _work(connection, worker_class=SimpleWorker):
    worker = worker_class(
        [_queue(connection)], connection=connection, job_class=ResultJob
    )
    worker.work(burst=True)


def test_a_finished_job_publishes_once_with_its_result_saved(scratch_redis):
    job = _queue(scratch_redis).enqueue(
        "builtins.len", [1, 2, 3], meta={"migration_id": "m1"}
    )

    _work(scratch_redis)

    (event,) = _events(scratch_redis, job.id)
    assert event["job_status"] == "finished"
    assert event["kind"] == "result"
    assert event["queue"] == LANE
    assert event["migration_id"] == "m1"
    job = ResultJob.fetch(job.id, connection=scratch_redis)
    assert job.get_status() == JobStatus.FINISHED
    assert job.return_value() == 3


def test_a_failed_job_publishes_once(scratch_redis):
    job = _queue(scratch_redis).enqueue("builtins.int", "not a number")

    _work(scratch_redis)

    assert [e["job_status"] for e in _events(scratch_redis, job.id)] == ["failed"]


def test_an_attempt_rq_will_retry_publishes_nothing(scratch_redis):
    job = _queue(scratch_redis).enqueue(
        "builtins.int", "not a number", retry=Retry(max=1)
    )

    _work(scratch_redis)

    job = ResultJob.fetch(job.id, connection=scratch_redis)
    assert job.get_status() == JobStatus.FAILED
    assert [e["job_status"] for e in _events(scratch_redis, job.id)] == ["failed"]


def test_a_work_horse_that_dies_is_published_as_failed(scratch_redis):
    job = _queue(scratch_redis).enqueue("os._exit", 1)

    _work(scratch_redis, worker_class=Worker)

    assert [e["job_status"] for e in _events(scratch_redis, job.id)] == ["failed"]


def test_a_job_found_abandoned_is_published_as_failed(scratch_redis):
    job = _queue(scratch_redis).enqueue("builtins.len", [1])
    job.set_status(JobStatus.STARTED)
    scratch_redis.zadd(
        StartedJobRegistry(LANE, connection=scratch_redis).key,
        {f"{job.id}:gone-execution": current_timestamp() - 10},
    )

    StartedJobRegistry(LANE, connection=scratch_redis, job_class=ResultJob).cleanup()

    assert [e["job_status"] for e in _events(scratch_redis, job.id)] == ["failed"]
