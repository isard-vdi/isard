#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Retire ``core`` as an execution surface: ``core`` finalize as metadata.

A chain's ``core`` finalize steps are stored as ``meta["core_finalize"]`` and
never become rq jobs, so rq cannot promote a tombstone onto the consumerless
``core`` queue. These tests exercise the producer + the :class:`CoreStep` shim
with Job/Queue mocked (no redis).
"""

import itertools
from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import CoreStep, Task
from rq.job import JobStatus

# A ``find``-shaped chain: storage root -> core storage_update_pool -> core
# storage_update_parent. The canonical two-deep core finalize tree.
FIND_DEPENDENTS = [
    {
        "queue": "core",
        "task": "storage_update_pool",
        "job_kwargs": {"kwargs": {"storage_id": "sid-1"}},
        "dependents": [
            {
                "queue": "core",
                "task": "storage_update_parent",
                "job_kwargs": {"kwargs": {"storage_id": "sid-1"}},
            }
        ],
    }
]

# A "knot": a storage task nested UNDER a core step (storage-under-core), like
# enqueue_template_creation_chain_from_desktop. The core step must carry the
# storage child as a ``storage_dependents`` entry, not build it at chain time.
KNOT_DEPENDENTS = [
    {
        "queue": "core",
        "task": "storage_update",
        "job_kwargs": {"kwargs": {"storage_id": "sid-1"}},
        "dependents": [
            {
                "queue": "core",
                "task": "storage_update_parent",
                "job_kwargs": {"kwargs": {"storage_id": "sid-1"}},
            },
            {
                "queue": "storage.pool.default",
                "task": "qemu_img_info_backing_chain",
                "job_kwargs": {"kwargs": {"storage_id": "sid-2"}},
            },
        ],
    }
]


def _build(dependents, **extra):
    """Real ``Task.__init__`` (new-task path) with Job/Queue mocked. Each
    ``Job.create`` returns a fresh mock with its own id/meta so nested tasks get
    distinct ids. Returns (root_task, jobs_created)."""
    jobs = []
    ids = itertools.count(1)

    def make_job(*a, **k):
        job = MagicMock(name="job")
        job.id = f"job-{next(ids)}"
        job.meta = {}
        job.args = []
        job.get_position.return_value = None
        jobs.append(job)
        return job

    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        Job.create.side_effect = make_job
        queue_obj = MagicMock(name="queue")
        # enqueue_job returns the job it was given (identity), like rq does.
        queue_obj.enqueue_job.side_effect = lambda job: job
        Queue.return_value = queue_obj
        task = Task(
            task="find",
            queue="storage.pool.default",
            user_id="u-1",
            dependents=dependents,
            **extra,
        )
    return task, jobs


# --------------------------------------------------------------------------- #
# Producer: core finalize is always metadata
# --------------------------------------------------------------------------- #


def test_metadata_mode_stores_core_finalize_and_creates_no_core_jobs():
    """Only the root job is created; the core finalize tree lives in
    ``meta["core_finalize"]`` and nothing is enqueued on ``core``."""
    task, jobs = _build(FIND_DEPENDENTS)
    assert len(jobs) == 1  # ONLY the root storage job
    assert not task.job.meta.get("dependent_ids")
    finalize = task.job.meta["core_finalize"]
    assert len(finalize) == 1
    pool = finalize[0]
    assert pool["task"] == "storage_update_pool"
    assert pool["queue"] == "core"
    assert pool["id"] == f"{task.id}:cf:0"
    assert pool["status"] is None
    assert pool["kwargs"] == {"storage_id": "sid-1"}
    assert pool["user_id"] == "u-1"
    # nested core step
    assert len(pool["core_finalize"]) == 1
    parent = pool["core_finalize"][0]
    assert parent["task"] == "storage_update_parent"
    assert parent["id"] == f"{task.id}:cf:0:cf:0"


def test_metadata_knot_carries_storage_child_as_storage_dependent():
    """A storage task nested under a core step is a ``storage_dependents`` entry
    (enqueued later by the consumer), not built at chain time."""
    task, jobs = _build(KNOT_DEPENDENTS)
    assert len(jobs) == 1  # no storage child built yet
    step = task.job.meta["core_finalize"][0]
    assert step["task"] == "storage_update"
    # its two dependents split: one core (metadata), one storage (deferred build)
    assert len(step["core_finalize"]) == 1
    assert step["core_finalize"][0]["task"] == "storage_update_parent"
    assert len(step["storage_dependents"]) == 1
    knot = step["storage_dependents"][0]
    assert knot["task"] == "qemu_img_info_backing_chain"
    assert knot["queue"] == "storage.pool.default"


# --------------------------------------------------------------------------- #
# CoreStep shim: dependents / to_dict / status
# --------------------------------------------------------------------------- #


def test_dependents_yields_core_step_shims_in_metadata_mode():
    task, _ = _build(FIND_DEPENDENTS)
    deps = task.dependents
    assert len(deps) == 1
    step = deps[0]
    assert isinstance(step, CoreStep)
    assert step.task == "storage_update_pool"
    assert step.queue == "core"
    assert step.user_id == "u-1"
    assert step.kwargs == {"storage_id": "sid-1"}
    # nested
    nested = step.dependents
    assert len(nested) == 1
    assert nested[0].task == "storage_update_parent"


def test_core_step_to_dict_shape_matches_task_dependent():
    task, _ = _build(FIND_DEPENDENTS)
    data = task.to_dict()
    assert len(data["dependents"]) == 1
    step = data["dependents"][0]
    # same key set a real rq dependent would render
    for key in (
        "id",
        "task",
        "queue",
        "status",
        "depending_status",
        "job_status",
        "pending",
        "progress",
        "kwargs",
        "user_id",
        "dependents",
    ):
        assert key in step, f"missing {key}"
    assert step["task"] == "storage_update_pool"
    assert len(step["dependents"]) == 1
    assert step["dependents"][0]["task"] == "storage_update_parent"


# --------------------------------------------------------------------------- #
# CoreStep status derivation + pending gate
# --------------------------------------------------------------------------- #


def _root_with_status(status):
    root = MagicMock(name="root")
    root.job_status = status
    return root


def test_core_step_deferred_while_parent_running():
    node = {"id": "x:cf:0", "task": "storage_update_pool", "status": None}
    step = CoreStep(node, _root_with_status(JobStatus.STARTED), redis=None)
    assert step.job_status == JobStatus.DEFERRED
    assert step.pending is True


def test_core_step_queued_when_parent_settled_but_not_run():
    node = {"id": "x:cf:0", "task": "storage_update_pool", "status": None}
    step = CoreStep(node, _root_with_status(JobStatus.FINISHED), redis=None)
    # ready to run, mirrors rq's DEFERRED->QUEUED promotion: still pending, the
    # storage stays gated until finalize actually applies (no tombstone leak).
    assert step.job_status == JobStatus.QUEUED
    assert step.pending is True
    assert step.depending_status == JobStatus.FINISHED


def test_core_step_finished_after_mark_stops_pending():
    node = {"id": "x:cf:0", "task": "storage_update_pool", "status": None}
    step = CoreStep(node, _root_with_status(JobStatus.FINISHED), redis=None)
    step.mark(ok=True)
    assert node["status"] == "finished"
    assert step.job_status == JobStatus.FINISHED
    assert step.pending is False


def test_metadata_pending_releases_when_finalize_marked():
    """End-to-end on the real Task: a finished storage root with an unstamped
    finalize is still pending; marking the finalize done releases it."""
    task, _ = _build(FIND_DEPENDENTS)
    # make the root read FINISHED
    task.job.get_status.return_value = JobStatus.FINISHED
    assert task.pending is True  # finalize not applied yet -> gated
    # the change-handler runs + marks the finalize step
    task.dependents[0].mark(ok=True)
    assert task.pending is False


def test_root_only_chain_has_no_finalize():
    """A chain with no dependents has no finalize steps."""
    task, jobs = _build([])
    assert len(jobs) == 1
    assert task.dependents == []
