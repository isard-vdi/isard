# SPDX-License-Identifier: AGPL-3.0-or-later

"""A knot child must not be created onto a lane nothing can drain.

The storage child nested under a ``core`` finalize step is the one chain member
that is NOT admitted when the chain is. Its parent passed the enqueue-time
consumer gate hours or minutes earlier, on a different lane; this child is built
here, later, on a lane of its own — and by then the pool it names may have no
live worker left. Building it anyway writes a QUEUED rq job nobody will ever
take: no worker picks it up, nothing raises, no timeout fires, and the owning
storage row sits behind a task that reports running while not one byte moves.

The right posture here is to DECLINE, not to refuse: returning ``False`` leaves
the stream entry unACKed, so the reclaim redelivers it and the existence guard
dedups — the work stays where something already re-drives it. Raising would be
caught by the ``except`` below, logged as a traceback for a routine shed, and
the entry dropped as though it had been handled.

These tests never name the gate. They present the consumer with a governor redis
that describes a dead fleet and assert what the product does with it, so the
file collects and runs against a build that has no gate at all.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.models.task import CoreStep
from rq.job import JobStatus

# A real storage lane name: ``storage.<pool>.<tier>``, which is what the
# coverage read parses into (pool, category, tier).
POOL = "00000000-0000-0000-0000-000000000000"
STORAGE_LANE = f"storage.{POOL}.standard"


class _NullPipe:
    """Records the pipelined writes the shed counter makes and executes none of
    them — the counter is fail-open, and these tests are about the decision."""

    def __init__(self):
        self.ops = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self.ops.append(name)
            return self

        return _queue

    def execute(self):
        return []


class _FleetRedis:
    """The governor redis as the coverage read sees it, with a live worker fleet
    or none.

    Only the handful of commands that read answers: the live per-(pool, tier)
    coverage zset, the ``rq:workers`` fallback scan, and the fleet-last-seen
    stamp that dates an empty index. Every one of them ANSWERS — a read that
    failed would be ignorance, which is a different situation with a different
    verdict.
    """

    def __init__(self, live_workers=0):
        self._live = live_workers
        self.written = {}

    # -- live coverage index -------------------------------------------------
    def zremrangebyscore(self, key, min_score, max_score):
        return 0

    def zcount(self, key, min_score, max_score):
        return self._live

    # -- the slower governor-hash scan: no worker is registered at all --------
    def smembers(self, key):
        return set()

    # -- fleet last seen: never, so an empty index is not a restart gap -------
    def get(self, key):
        return None

    def set(self, key, value):
        self.written[key] = value
        return True

    # -- lane backlog --------------------------------------------------------
    def llen(self, key):
        return 0

    def pipeline(self):
        return _NullPipe()


def _step_with_one_knot_child(queue=STORAGE_LANE):
    """A real metadata finalize step carrying exactly one storage child.

    Built as the chain builder builds it: the child's rq job id is declared on
    the node, so the step names the child it would create rather than deriving
    it. The parent stands in for the ANCHOR — the real job whose meta carries
    this node — and is terminal, so the step is dispatchable.
    """
    child = {
        "task": "qemu_img_info_backing_chain",
        "queue": queue,
        "job_kwargs": {},
        "dependents": [],
    }
    node = {
        "id": "finalize-step",
        "task": "storage_update",
        "queue": "core",
        "kwargs": {},
        "args": [],
        "core_finalize": [],
        "storage_dependents": [child],
        "storage_dependent_ids": ["finalize-step-sd-0"],
        "status": None,
    }
    anchor = SimpleNamespace(
        job_status=JobStatus.FINISHED,
        id="anchor-of-finalize-step",
        job=MagicMock(),
    )
    return CoreStep(node, anchor, MagicMock())


def _task_double(conn):
    """Stand in for ``models.task.Task``: it is both the constructor the
    consumer calls to create the child and the holder of the redis handle the
    consumer reads the fleet through. ``exists`` is False so the idempotence
    guard never short-circuits the path under test."""
    task = MagicMock(name="Task")
    task.exists.return_value = False
    task._redis = conn
    return task


async def _enqueue_against(conn):
    from isardvdi_change_handler.streams import task_results_consumer

    step = _step_with_one_knot_child()
    task = _task_double(conn)
    with patch.object(task_results_consumer, "Task", task):
        ok = await task_results_consumer._enqueue_metadata_storage_dependents(step)
    return ok, task


@pytest.mark.asyncio
async def test_a_knot_child_is_not_created_when_its_lane_has_no_consumer():
    """Creating it strands a storage job forever: nothing dequeues it, nothing
    fails it, and the row it belongs to reports work in flight for good."""
    ok, task = await _enqueue_against(_FleetRedis(live_workers=0))

    assert task.call_args_list == [], (
        "a storage knot child was created on a lane with no live consumer: "
        f"{task.call_args_list}"
    )
    assert ok is False, (
        "the consumer reported success for a child it could not place, so the "
        "stream entry is ACKed and nothing ever retries it"
    )


@pytest.mark.asyncio
async def test_a_knot_child_is_still_created_when_its_lane_is_served():
    """The other half: a fleet that is alive must keep building knot children,
    or every template creation stops at its finalize step."""
    ok, task = await _enqueue_against(_FleetRedis(live_workers=1))

    assert (
        len(task.call_args_list) == 1
    ), f"the knot child was not created on a served lane: {task.call_args_list}"
    created = task.call_args_list[0].kwargs
    assert created.get("queue") == STORAGE_LANE
    assert created.get("job_kwargs", {}).get("id") == "finalize-step-sd-0", (
        "the child was created under an id the chain never declared, so nothing "
        f"can find it: {created.get('job_kwargs')}"
    )
    assert ok is True
