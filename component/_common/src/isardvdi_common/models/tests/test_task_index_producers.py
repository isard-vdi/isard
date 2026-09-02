# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every producer of a task writes it into its owners' index.

The index is written from ``Task.__init__`` rather than from each
``create_task``, because not every producer goes through one:
``RecycleBin.delete_storage`` builds ``Task(...)`` directly so it can register
the task before enqueuing it. One write site means a new producer cannot
silently bypass the index — it only has to name its owners.

Roots only. A chain's finalize steps are not operations the disk had, and
indexing them would spend the cap three times over on one operation.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.storage import Storage
from isardvdi_common.models.task import Task


def _build(**extra):
    """Run the real ``Task.__init__`` with ``Job``/``Queue`` mocked, and return
    every ``index_task`` call it made as ``(job_id, owners, kind)``."""
    made = []

    def _create(func_name, *args, **kwargs):
        job = MagicMock(name=f"job-{len(made)}")
        job.id = f"job-{len(made)}"
        job.meta = kwargs.get("meta", {})
        made.append(job)
        return job

    calls = []

    def _index(connection, job, owners, kind="storage"):
        calls.append((job.id, list(owners), kind))

    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue, patch("isardvdi_common.models.task.index_task", side_effect=_index):
        Job.create.side_effect = _create
        Queue.return_value.enqueue_job.side_effect = lambda job: job
        # A generic storage task: "move" exercises the same index path without
        # the qcow2 geometry a create/convert/disconnect now requires.
        Task(task="move", queue="storage.pool.default", **extra)
    return calls


class TestTheRootIsIndexed:
    def test_a_task_lands_under_the_row_that_created_it(self):
        assert _build(storage_id="disk-1", index_owners=["disk-1"]) == [
            ("job-0", ["disk-1"], "storage")
        ]

    def test_a_task_may_name_several_owners(self):
        """The locked row goes here — never in the meta. A template creation is
        built from the desktop and locks the template, so both rows must be
        able to answer "what happened to me"."""
        calls = _build(storage_id="desktop-1", index_owners=["desktop-1", "template-1"])
        assert calls == [("job-0", ["desktop-1", "template-1"], "storage")]

    def test_media_is_indexed_in_its_own_namespace(self):
        calls = _build(media_id="med-1", index_owners=["med-1"], index_kind="media")
        assert calls == [("job-0", ["med-1"], "media")]

    def test_a_task_with_no_owner_writes_nothing(self):
        assert _build() == []

    def test_a_task_built_for_deferred_enqueue_is_still_indexed(self):
        """``RecycleBin.delete_storage`` creates, registers, then enqueues. The
        task must be findable from the moment it exists."""
        assert _build(index_owners=["disk-1"], enqueue=False) == [
            ("job-0", ["disk-1"], "storage")
        ]

    def test_dependents_are_not_indexed(self):
        """One operation is one row in the list, not one row per chain step."""
        calls = _build(
            index_owners=["disk-1"],
            dependents=[{"queue": "core", "task": "storage_update"}],
        )
        assert [job_id for job_id, _, _ in calls] == ["job-0"]

    def test_a_dependent_may_still_be_indexed_deliberately(self):
        """Explicit beats implicit: a chain step that IS a disk's own operation
        can name its owners, and then it is indexed like any other root."""
        calls = _build(
            index_owners=["disk-1"],
            dependents=[
                {
                    "queue": "storage.pool.default",
                    "task": "qemu_img_info",
                    "index_owners": ["disk-2"],
                }
            ],
        )
        assert sorted(calls) == [
            ("job-0", ["disk-1"], "storage"),
            ("job-1", ["disk-2"], "storage"),
        ]


class TestCreateTaskDefaultsTheOwner:
    """``create_task`` takes a list of owner ids, defaulting to its own row."""

    def _run(self, **extra):
        disk = Storage.__new__(Storage)
        disk.__dict__.update({"id": "disk-1", "task": None})
        seen = {}

        def _task(*args, **kwargs):
            seen.update(kwargs)
            built = MagicMock()
            built.id = "job-1"
            return built

        with patch(
            "isardvdi_common.models.storage.Task", side_effect=_task
        ) as Task_, patch(
            "isardvdi_common.models.storage.queue_coverage.enforce_shed"
        ), patch.object(
            Storage, "category", "cat-1"
        ), patch.object(
            Storage, "__setattr__", lambda self, name, value: None
        ):
            Task_.exists.return_value = False
            Task_._redis = MagicMock()
            disk.create_task(
                user_id="u-1", queue="storage.pool.default", task="convert", **extra
            )
        return seen

    def test_it_defaults_to_its_own_row(self):
        assert self._run()["index_owners"] == ["disk-1"]

    def test_a_caller_may_name_the_row_the_chain_locks_too(self):
        assert self._run(index_owners=["disk-1", "template-1"])["index_owners"] == [
            "disk-1",
            "template-1",
        ]
