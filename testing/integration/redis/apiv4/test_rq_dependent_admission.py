#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The premise ``TaskService``'s CANCELED-dependent refusal rests on.

``api.services.tasks`` refuses to retry a task whose direct dependent is
CANCELED, because rq would re-run the root's disk operation while the
dependents that would have finalised it never re-run: the operation happens and
nothing closes it out. That refusal is only as good as its premise about rq's
own admission rule, so the premise is proved against the rq we actually ship
rather than taken on trust.

Proving it means running rq, which is why this lives here and not beside the
rest of ``TaskService``'s unit tests: what it asserts on is rq's behaviour, not
our use of it. Work happens in an unused db (15) under a per-run queue name,
and every key created is deleted again.
"""

import os
import uuid

import pytest
from rq.job import JobStatus


class TestRqDependentAdmission:
    @staticmethod
    def _queue():
        import redis
        from rq import Queue

        host = os.environ.get("REDIS_HOST", "isard-redis")
        connection = redis.Redis(
            host=host,
            port=int(os.environ.get("REDIS_PORT", 6379)),
            password=os.environ.get("REDIS_PASSWORD") or None,
            db=int(os.environ.get("RQ_PROOF_REDIS_DB", 15)),
        )
        try:
            connection.ping()
        except Exception as exc:
            pytest.fail(
                f"this proof requires a reachable redis (REDIS_HOST={host}); "
                f"it must not be skipped into silence: {exc}"
            )
        return Queue(f"rq-proof-{uuid.uuid4().hex[:8]}", connection=connection)

    def test_rq_skips_a_canceled_dependent_and_enqueues_a_deferred_one(self):
        """``Queue.enqueue_dependents`` admits a dependent only when its status
        is not CANCELED. So a root whose chain was cancelled re-runs its disk
        operation while the dependents that would have finalised it never
        re-run: the operation happens and nothing closes it out."""
        queue = self._queue()
        root = queue.enqueue(print, "root")
        canceled = queue.enqueue(print, "canceled", depends_on=root)
        deferred = queue.enqueue(print, "deferred", depends_on=root)
        try:
            canceled.cancel()
            assert canceled.get_status(refresh=True) == JobStatus.CANCELED
            assert deferred.get_status(refresh=True) == JobStatus.DEFERRED
            root.set_status(JobStatus.FINISHED)

            queue.enqueue_dependents(root)

            queued = queue.job_ids
            assert deferred.id in queued, "a DEFERRED dependent must be promoted"
            assert canceled.id not in queued, "rq must not promote a CANCELED one"
            assert canceled.get_status(refresh=True) == JobStatus.CANCELED
        finally:
            for job in (root, canceled, deferred):
                job.delete()
            queue.delete(delete_jobs=True)
