#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api.services.error import Error
from isardvdi_common.models.task import Task


class TaskService:
    """Service for task management operations."""

    @staticmethod
    def get_task(task_id: str) -> dict:
        """Get a single task by ID."""
        if not Task.exists(task_id):
            raise Error("not_found", "Task not found")
        task = Task(task_id)
        return task.to_dict()

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
