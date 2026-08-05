# SPDX-License-Identifier: AGPL-3.0-or-later

"""The real storage-under-core knot (template creation from desktop).

The template chain is the only one that nests a storage task under a ``core``
step: ``... qemu_img_info -> storage_update (core) -> [storage_update_parent,
qemu_img_info (storage) -> storage_update (core) -> [parent, update_status]]``.

The knot serializes in two levels: the top ``storage_update`` keeps the inner
``qemu_img_info`` as a raw ``storage_dependents`` entry (with its own subtree
intact); only when the consumer enqueues that storage Task do its ``core`` steps
become metadata on it. This mirrors the real structure in
``Storage.enqueue_template_creation_chain_from_desktop``.
"""

import itertools
from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import CoreStep, Task, _serialize_finalize

# The ``storage_update`` core step + everything below it, exactly as the template
# chain builds it (the core-bearing subtree that hangs off the middle
# qemu_img_info storage task).
STORAGE_UPDATE_WITH_KNOT = {
    "queue": "core",
    "task": "storage_update",
    "dependents": [
        {
            "queue": "core",
            "task": "storage_update_parent",
            "job_kwargs": {"kwargs": {"storage_id": "tpl-sid"}},
        },
        {
            # THE KNOT: a storage task nested under the core storage_update.
            "queue": "storage.src.template",
            "task": "qemu_img_info_backing_chain",
            "job_kwargs": {"kwargs": {"storage_id": "dom-sid", "storage_path": "/x"}},
            "dependents": [
                {
                    "queue": "core",
                    "task": "storage_update",
                    "dependents": [
                        {
                            "queue": "core",
                            "task": "storage_update_parent",
                            "job_kwargs": {"kwargs": {"storage_id": "dom-sid"}},
                        },
                        {
                            "queue": "core",
                            "task": "update_status",
                            "job_kwargs": {"kwargs": {"statuses": {}}},
                        },
                    ],
                }
            ],
        },
    ],
}


def test_knot_top_level_serialization_keeps_storage_child_raw():
    node = _serialize_finalize(STORAGE_UPDATE_WITH_KNOT, "root", 0, "u", "c")

    assert node["task"] == "storage_update"
    assert node["id"] == "root:cf:0"
    # the one core child is a nested finalize node...
    assert [c["task"] for c in node["core_finalize"]] == ["storage_update_parent"]
    # ...and the storage child is carried raw, NOT serialized into finalize.
    assert len(node["storage_dependents"]) == 1
    knot = node["storage_dependents"][0]
    assert knot["task"] == "qemu_img_info_backing_chain"
    assert knot["queue"] == "storage.src.template"
    # the knot's OWN core subtree is still intact (serialized only when built)
    assert knot["dependents"][0]["task"] == "storage_update"
    inner = knot["dependents"][0]["dependents"]
    assert [c["task"] for c in inner] == ["storage_update_parent", "update_status"]


def test_knot_second_level_serializes_when_built_as_task():
    """Building the knot storage task in metadata mode turns ITS core steps into
    metadata — with no core rq job at either level."""
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

    knot = _serialize_finalize(STORAGE_UPDATE_WITH_KNOT, "root", 0, "u", "c")[
        "storage_dependents"
    ][0]

    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        Job.create.side_effect = make_job
        q = MagicMock()
        q.enqueue_job.side_effect = lambda job: job
        Queue.return_value = q
        knot_task = Task(**knot)

    # only the knot storage job itself is created — no core rq jobs
    assert len(jobs) == 1
    finalize = knot_task.job.meta["core_finalize"]
    assert [n["task"] for n in finalize] == ["storage_update"]
    assert [c["task"] for c in finalize[0]["core_finalize"]] == [
        "storage_update_parent",
        "update_status",
    ]
    assert knot_task.job.meta.get("dependent_ids", []) == []


# ---------------------------------------------------------------------------
# The dead-chain view of a knot child that will never be built
# ---------------------------------------------------------------------------


def _knot_step():
    """The finalize step that carries the knot, as a CoreStep."""
    return CoreStep(
        _serialize_finalize(STORAGE_UPDATE_WITH_KNOT, "root", 0, "u", "c"),
        None,
        MagicMock(),
    )


def test_an_unbuilt_knot_child_exposes_its_core_subtree():
    """On a chain that failed or was cancelled the child is never created, so
    everything the chain declared below it — including the terminal
    update_status — is reachable only as the metadata it already is."""
    step = _knot_step()

    with patch("isardvdi_common.models.task.Job") as Job:
        Job.exists.return_value = False
        steps = step.unbuilt_knot_steps()

    assert [s.task for s in steps] == ["storage_update"]
    assert [c.task for c in steps[0].dependents] == [
        "storage_update_parent",
        "update_status",
    ]


def test_an_unbuilt_knot_step_uses_the_id_the_real_child_would_have_produced():
    """One member, one identity — whether it is reached as metadata here or as
    the job the consumer creates. Any drift would let the same step be
    dispatched twice under two names."""
    step = _knot_step()

    with patch("isardvdi_common.models.task.Job") as Job:
        Job.exists.return_value = False
        steps = step.unbuilt_knot_steps()

    child_id = step.knot_child_ids[0]
    assert steps[0].id == f"{child_id}:cf:0"
    assert [c.id for c in steps[0].dependents] == [
        f"{child_id}:cf:0:cf:0",
        f"{child_id}:cf:0:cf:1",
    ]


def test_a_knot_child_that_exists_is_not_exposed_as_metadata():
    """It is a real member with its own finalize tree, and the walk reaches it
    as the job it is. Returning it here too would give one member two
    representations, whose status marks can then disagree."""
    step = _knot_step()

    with patch("isardvdi_common.models.task.Job") as Job:
        Job.exists.return_value = True
        assert step.unbuilt_knot_steps() == []
