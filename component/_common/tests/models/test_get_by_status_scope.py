# SPDX-License-Identifier: AGPL-3.0-or-later

"""``get_by_status`` must return only the statuses it was asked for.

QUEUED jobs live on the queue list rather than in a registry, and the list was
read on every call whatever the caller asked for. A scan for a handful of
DEFERRED orphans therefore hydrated the entire queued backlog of every queue -
one fetch per id - which on a busy install is tens of thousands of round trips
every pass, and delays the healing that scan exists to drive.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task
from rq.job import JobStatus


def _queue(name="storage.pool.standard", queued_ids=(), registry_ids=()):
    q = MagicMock(name=name)
    q.name = name
    q.job_ids = list(queued_ids)
    for status in (
        "deferred",
        "finished",
        "failed",
        "started",
        "canceled",
        "scheduled",
    ):
        reg = MagicMock()
        reg.get_job_ids.return_value = (
            list(registry_ids) if status == "deferred" else []
        )
        setattr(q, f"{status}_job_registry", reg)
    return q


def _run(statuses, queue):
    seen = {"ids": []}

    def _from_ids(ids, _source):
        seen["ids"].extend(list(ids))
        return []

    with (
        patch("isardvdi_common.models.task.Queue.all", return_value=[queue]),
        patch.object(Task, "_tasks_from_source_ids", side_effect=_from_ids),
        patch.object(Task, "_redis", MagicMock()),
    ):
        Task.get_by_status(*statuses)
    return seen["ids"]


class TestScope:
    def test_deferred_scan_does_not_read_the_queued_backlog(self):
        q = _queue(queued_ids=["q1", "q2", "q3"], registry_ids=["d1"])

        assert _run([JobStatus.DEFERRED.value], q) == ["d1"]

    def test_queued_is_still_available_when_asked_for(self):
        q = _queue(queued_ids=["q1", "q2"])

        assert _run([JobStatus.QUEUED.value], q) == ["q1", "q2"]

    def test_mixed_request_returns_both(self):
        q = _queue(queued_ids=["q1"], registry_ids=["d1"])

        got = _run([JobStatus.QUEUED.value, JobStatus.DEFERRED.value], q)

        assert sorted(got) == ["d1", "q1"]
