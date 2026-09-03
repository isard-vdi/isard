# SPDX-License-Identifier: AGPL-3.0-or-later

"""The owning row reaches the knot child, which is a real disk operation.

A ``core`` dependent is metadata, but its storage children are not: the result
consumer builds each one with ``Task(**child)`` when the finalize step runs, so
they become rq jobs that do disk work. Before the metadata path, they inherited
the owning row by recursion through ``Task.__init__``. Serialising the subtree
instead skips that recursion, and a closed key list plus a two-field child
hand-off is easy to leave the owner out of.

Nothing here is about the task index: a knot child is a member of its root's
chain and is reached through the root, so indexing it would put two rows in a
listing for one operation the user asked for. This is the ``meta`` trace field
only.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task


def _knot(**child_extra):
    """A fresh finalize step with one storage child.

    Built per call, never shared: ``Task.__init__`` and ``_serialize_finalize``
    fill their defaults INTO the dicts they are handed, so a module-level
    literal would carry one test's owner into the next.
    """
    return {
        "queue": "core",
        "task": "storage_update",
        "dependents": [
            {"queue": "storage.pool.default", "task": "qemu_img_info", **child_extra}
        ],
    }


def _build(**extra):
    """The real new-task path with ``Job``/``Queue`` mocked, returning the root
    Task so its ``meta["core_finalize"]`` can be read back."""
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
        # A generic storage root: "move" exercises the finalize-knot path
        # without the qcow2 geometry a create/convert/disconnect now requires.
        task = Task(task="move", queue="storage.pool.default", **extra)
    return task, created


def _knot_children(task):
    return task.job.meta["core_finalize"][0]["storage_dependents"]


class TestKnotChildOwner:
    def test_the_knot_child_carries_the_owning_disk(self):
        """Parity with the pre-metadata chain, where the child got there by
        recursion. Without it the consumer stamps ``storage_id = None`` on a job
        that is doing that disk's work."""
        task, _ = _build(storage_id="disk-1", dependents=[_knot()])
        assert _knot_children(task)[0]["storage_id"] == "disk-1"

    def test_the_knot_child_carries_the_owning_media(self):
        task, _ = _build(media_id="media-1", dependents=[_knot()])
        assert _knot_children(task)[0]["media_id"] == "media-1"

    def test_a_knot_child_may_name_its_own_owner(self):
        """Same ``setdefault`` semantics the rq path has: an explicit owner on
        the child wins over the one it would inherit."""
        task, _ = _build(storage_id="disk-1", dependents=[_knot(storage_id="disk-2")])
        assert _knot_children(task)[0]["storage_id"] == "disk-2"

    def test_the_owner_reaches_a_knot_under_a_nested_finalize_step(self):
        """A finalize tree is recursive, so the owner has to descend with it."""
        nested = {
            "queue": "core",
            "task": "storage_update",
            "dependents": [
                {
                    "queue": "core",
                    "task": "domain_update",
                    "dependents": [
                        {"queue": "storage.pool.default", "task": "qemu_img_info"}
                    ],
                }
            ],
        }
        task, _ = _build(storage_id="disk-1", dependents=[nested])
        inner = task.job.meta["core_finalize"][0]["core_finalize"][0]
        assert inner["storage_dependents"][0]["storage_id"] == "disk-1"

    def test_the_consumer_stamps_the_owner_it_was_handed(self):
        """End of the path: what the change-handler builds from that dict is an
        rq job whose meta names the disk."""
        task, created = _build(storage_id="disk-1", dependents=[_knot()])
        child = dict(_knot_children(task)[0])
        created.clear()
        with patch("isardvdi_common.models.task.Job") as Job, patch(
            "isardvdi_common.models.task.Queue"
        ) as Queue:
            Job.create.side_effect = lambda func_name, *a, **kw: created.append(
                (func_name, kw)
            ) or MagicMock(id="child", meta=kw.get("meta", {}))
            Queue.return_value.enqueue_job.side_effect = lambda job: job
            Task(**child)
        assert created[0][1]["meta"]["storage_id"] == "disk-1"


class TestKnotChildIsNotIndexed:
    def test_the_knot_child_names_no_index_owner(self):
        """A knot child is a member of its root's chain and is reached through
        the root. Indexing it too would spend the per-owner cap several times on
        one operation and show the user two rows for one thing they asked for."""
        task, _ = _build(
            storage_id="disk-1", index_owners=["disk-1"], dependents=[_knot()]
        )
        assert "index_owners" not in _knot_children(task)[0]
