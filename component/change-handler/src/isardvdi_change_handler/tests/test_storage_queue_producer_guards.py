# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard / decision paths of ``streams/storage_queue_producer.py``.

* ``_still_queued`` -- True only while the job still has a queue position; any
  error -> False (never emit a stale ``queued`` position).
* ``_collect`` -- skips the scheduler's own tasks and running/finished ones,
  and drops a candidate with no resolvable storage_id; emits the waiting ones.

Only the RQ / model collaborators are stubbed; the decisions are the code's.
"""

from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from isardvdi_change_handler.streams import storage_queue_producer as mod


class TestStillQueued:
    def test_queued_when_position_present(self):
        job = SimpleNamespace(get_position=lambda: 3)
        with patch.object(mod.Job, "fetch", return_value=job):
            assert mod._still_queued(MagicMock(), "t1") is True

    def test_not_queued_when_position_none(self):
        job = SimpleNamespace(get_position=lambda: None)
        with patch.object(mod.Job, "fetch", return_value=job):
            assert mod._still_queued(MagicMock(), "t1") is False

    def test_error_is_not_queued(self):
        with patch.object(mod.Job, "fetch", side_effect=RuntimeError()):
            assert mod._still_queued(MagicMock(), "t1") is False


class TestCollect:
    def _run(self, tasks, ests, storage_rows):
        """Drive _collect with one lane holding ``tasks`` (list of SimpleNamespace),
        ``ests`` keyed by task id, and a storage-id lookup ``storage_rows``.

        The producer resolves task -> storage two different ways depending on
        which side of the task-pointer retirement you are on: here it is one
        batched ``Storage.get_storage_ids_from_task_ids``; once the retirement
        lands it reads ``Task(task_id).storage_id`` instead, and the batched
        classmethod is gone. Feed BOTH, so the test states the same thing on
        either side rather than passing on one and erroring on the other.
        """
        conn = MagicMock()
        task_by_id = {t.id: t for t in tasks}
        storage_by_task = {r["task_id"]: r["storage_id"] for r in storage_rows}
        for task_id, task in task_by_id.items():
            if getattr(task, "storage_id", None) is None:
                task.storage_id = storage_by_task.get(task_id)
        with ExitStack() as stack:
            stack.enter_context(
                patch.object(mod, "_storage_lanes", return_value=["storage.poolA.high"])
            )
            stack.enter_context(
                patch.object(
                    mod,
                    "Queue",
                    return_value=SimpleNamespace(
                        get_job_ids=lambda a, b: [t.id for t in tasks]
                    ),
                )
            )
            stack.enter_context(
                patch.object(mod, "Task", side_effect=lambda jid: task_by_id[jid])
            )
            stack.enter_context(
                patch.object(
                    mod.queue_estimate,
                    "estimate_task",
                    side_effect=lambda t, c: ests[t.id],
                )
            )
            # Only where it still exists: patching a name the retirement removed
            # raises AttributeError before a single assertion runs.
            if hasattr(mod.Storage, "get_storage_ids_from_task_ids"):
                stack.enter_context(
                    patch.object(
                        mod.Storage,
                        "get_storage_ids_from_task_ids",
                        return_value=storage_rows,
                    )
                )
            return mod._collect(conn)

    def test_skips_scheduler_and_emits_waiting_user_task(self):
        tasks = [
            SimpleNamespace(id="sched", user_id="isard-scheduler"),
            SimpleNamespace(id="t1", user_id="u-alice"),
        ]
        ests = {
            "sched": {"effective_position": 1},
            "t1": {"effective_position": 2, "stranded": False},
        }
        # Both have a resolvable storage id, so the ONLY reason the scheduler
        # task is excluded is the user_id guard (not a missing storage row).
        out = self._run(
            tasks,
            ests,
            storage_rows=[
                {"task_id": "sched", "storage_id": "s-0"},
                {"task_id": "t1", "storage_id": "s-1"},
            ],
        )
        # Only the real user's waiting task is emitted, with the storage id.
        assert [(u, p["id"], p["storage_id"]) for u, p in out] == [
            ("u-alice", "t1", "s-1")
        ]

    def test_drops_candidate_without_storage_id(self):
        tasks = [SimpleNamespace(id="t1", user_id="u-alice")]
        ests = {"t1": {"effective_position": 2}}
        # storage lookup returns nothing for t1 -> cannot map to a card -> dropped.
        out = self._run(tasks, ests, storage_rows=[])
        assert out == []

    def test_skips_non_waiting_task(self):
        tasks = [SimpleNamespace(id="t1", user_id="u-alice")]
        # running/finished: no position and not stranded -> skipped before storage.
        ests = {"t1": {"effective_position": None, "stranded": False}}
        out = self._run(
            tasks, ests, storage_rows=[{"task_id": "t1", "storage_id": "s-1"}]
        )
        assert out == []
