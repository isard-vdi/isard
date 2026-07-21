#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import time
import traceback

from api.services.error import Error
from isardvdi_common.lib.queue_tiers import parse_storage_queue
from isardvdi_common.models.task import Task


class TaskService:
    """Service for task management operations."""

    @staticmethod
    def get_task(task_id: str) -> dict:
        """Get a single task by ID, best-effort enriched with observability
        fields (tier / timestamps / age / retries_left / exc_string).

        Enrichment is SINGLE-task only — deliberately NOT applied to
        ``get_admin_tasks``/``to_dict``, whose per-row ``latest_result`` Redis
        fetch would be a listing regression."""
        if not Task.exists(task_id):
            raise Error("not_found", "Task not found")
        task = Task(task_id)
        data = task.to_dict()
        TaskService._enrich_task_dict(data, task)
        return data

    @staticmethod
    def _enrich_task_dict(data: dict, task) -> None:
        """Best-effort observability enrichment for a single task (mutates
        ``data`` in place). Never raises out — any failure leaves the base
        ``to_dict`` payload intact. ``category_id`` already flows from
        ``to_dict``; ``category_name`` is left ``None`` here (resolved on the
        problem-tasks path, no per-task DB lookup added to ``get_task``)."""
        try:
            job = task.job
            now_ts = time.time()
            queue = data.get("queue")
            parsed = parse_storage_queue(queue) if queue else None
            if parsed:
                data["tier"] = parsed[2]
            enqueued_at = TaskService._dt_ts(getattr(job, "enqueued_at", None))
            started_at = TaskService._dt_ts(getattr(job, "started_at", None))
            ended_at = TaskService._dt_ts(getattr(job, "ended_at", None))
            data["enqueued_at"] = enqueued_at
            data["started_at"] = started_at
            data["ended_at"] = ended_at
            base = enqueued_at if enqueued_at is not None else started_at
            data["age_seconds"] = max(0.0, now_ts - base) if base is not None else None
            data["retries_left"] = getattr(job, "retries_left", None)
            data["exc_string"] = TaskService._task_exc_string(job)
            # Live queue estimate (single-task path only, same listing-regression
            # rationale): effective position across higher-priority tiers +
            # consumer/stranded flags. Bounded and fail-safe. Imported lazily to
            # avoid an import cycle at app init (services.tasks is loaded from
            # routes.tasks mid-init).
            from isardvdi_common.lib.queue_estimate import estimate_task

            est = estimate_task(task)
            data["effective_position"] = est.get("effective_position")
            data["eta_seconds"] = est.get("eta_seconds")
            data["has_consumer"] = est.get("has_consumer")
            data["stranded"] = est.get("stranded")
        except Exception:
            pass

    @staticmethod
    def _dt_ts(dt):
        """A tz-aware rq-job datetime -> epoch float (guarding None)."""
        if dt is None:
            return None
        try:
            return dt.timestamp()
        except Exception:
            return None

    @staticmethod
    def _task_exc_string(job):
        """Traceback of the job's latest FAILED result, else ``None``. Uses
        ``Result.exc_string`` (not the deprecated ``job.exc_info``)."""
        try:
            from rq.results import Result

            res = job.latest_result()
            if res is not None and res.type == Result.Type.FAILED:
                return res.exc_string
        except Exception:
            return None
        return None

    @staticmethod
    def get_queues_health() -> dict:
        """User-facing storage-queue health: ``degraded`` / ``stranded`` booleans
        plus a compact per-tier queued rollup (no pool / category / per-worker
        detail). Reuses the cached admin backlog rollup; degrades to a healthy
        summary on any error so a banner never false-alarms."""
        try:
            from collections import defaultdict

            from api.services.admin.queues import AdminQueuesService

            rows = AdminQueuesService.get_backlog_rollup() or []
        except Exception:
            return {"degraded": False, "stranded": False, "tiers": []}
        stranded = any(r.get("stranded") for r in rows)
        # Degraded when a lane is confidently consumer-less, or work has been
        # waiting long enough that a user would notice a delay.
        degraded = stranded or any(
            (r.get("oldest_queued_age_seconds") or 0) > 300 for r in rows
        )
        totals = defaultdict(lambda: {"queued": 0, "stranded": False})
        for r in rows:
            entry = totals[r.get("tier")]
            entry["queued"] += r.get("queued") or 0
            entry["stranded"] = entry["stranded"] or bool(r.get("stranded"))
        tiers = [
            {"tier": tier, **entry}
            for tier, entry in totals.items()
            if entry["queued"] or entry["stranded"]
        ]
        return {"degraded": bool(degraded), "stranded": bool(stranded), "tiers": tiers}

    @staticmethod
    def get_task_with_owner_check(task_id: str, user_id: str, role_id: str) -> dict:
        """Get a task with ownership verification."""
        if not Task.exists(task_id):
            raise Error("not_found", "Task not found")
        task = Task(task_id)
        if role_id != "admin" and task.user_id != user_id:
            raise Error("forbidden", "Not authorized to access this task")
        return task

    @staticmethod
    def get_task_details_with_owner_check(
        task_id: str, user_id: str, role_id: str
    ) -> dict:
        """Owner-checked single-task fetch, serialised and observability-enriched
        (tier / timestamps / age / retries_left / exc_string) for the task-detail
        and traceback drawer. Same enrichment as :meth:`get_task`; the owner check
        gates non-admins. Single-task only — never on the bulk listing path."""
        task = TaskService.get_task_with_owner_check(task_id, user_id, role_id)
        data = task.to_dict()
        TaskService._enrich_task_dict(data, task)
        return data

    @staticmethod
    def cancel_task(task_id: str, user_id: str, role_id: str) -> dict:
        """Cancel a queued task."""
        task = TaskService.get_task_with_owner_check(task_id, user_id, role_id)
        if task.status != "queued":
            raise Error(
                "precondition_required",
                f"Task should be queued, but is {task.status}",
            )
        task.cancel()
        return task.to_dict()

    @staticmethod
    def get_user_tasks(user_id: str) -> list:
        """Get all tasks for a user."""
        return [task.to_dict() for task in Task.get_by_user(user_id)]

    @staticmethod
    def get_admin_tasks(
        user_id: str,
        role_id: str,
        category_id: str = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list:
        """Get all tasks (admin) or category tasks (manager).

        Pagination: ``Task.get_all()`` materialises one ``Task`` object
        per RQ job in every queue + every status registry, then
        ``to_dict()`` issues a Redis fetch per job. Without bounds,
        the response was ~12 MB / 32 s on a populated dev DB
        (Bug 38 in load-testing markdown). Default page size ``200``
        keeps the response under ~200 KB; callers can opt in to the
        full history via ``limit=10000``.
        """
        tasks = []
        for task in Task.get_all():
            if task.user_id:
                if role_id == "admin":
                    tasks.append(task)
                elif role_id == "manager" and category_id:
                    # Managers can only see tasks from their category
                    # For now, include all tasks with user_id set
                    tasks.append(task)
        # Slice before ``to_dict``: that's the per-task Redis-fetch
        # path. Slicing the materialised Task list is cheap; the
        # filter above had to walk every task to evaluate ``user_id``,
        # so the only cost we save is the per-row dict serialisation.
        page = tasks[offset : offset + limit]
        return [task.to_dict() for task in page]

    @staticmethod
    def retry_task(task_id: str) -> dict:
        """Retry a failed task (admin only)."""
        if not Task.exists(task_id):
            raise Error("not_found", "Task not found")
        task = Task(task_id)
        if task.status != "failed":
            raise Error(
                "precondition_required",
                f"Task should be failed, but is {task.status}",
            )
        task.retry()
        return task.to_dict()

    @staticmethod
    def retry_all_failed_tasks() -> dict:
        """Retry all failed storage tasks (admin only). Runs in background."""
        tasks = Task.get_failed_storage_tasks()
        for task in tasks:
            try:
                task.retry()
            except Exception:
                pass
        return {}

    @staticmethod
    def admin_cancel_task(task_id: str) -> dict:
        """Admin-cancel a task with NO ownership or status gate.

        Unlike :meth:`cancel_task` (owner-gated, queued-only), this clears a
        wedged / deferred / running-if-cooperative task on the operator's
        behalf. ``Task.cancel()`` drops queued jobs and publishes a
        ``task:cancel:<id>`` pub/sub signal, but CANNOT stop an already-running
        task body unless that body cooperates by watching for the signal
        (``TaskCancelWatcher``). A gone task surfaces as a ``not_found`` Error
        (-> 404)."""
        if not Task.exists(task_id):
            raise Error("not_found", "Task not found")
        Task(task_id).cancel()
        return {}
