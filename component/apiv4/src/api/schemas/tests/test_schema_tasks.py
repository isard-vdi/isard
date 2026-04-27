# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/tasks.py``."""

import pytest
from api.schemas.tasks import TaskListResponse, TaskResponse
from pydantic import ValidationError


class TestTaskResponse:
    """Loose schema (every field optional except id) — task rows in
    the DB carry varying field sets depending on what the worker has
    written."""

    def test_id_required(self):
        with pytest.raises(ValidationError):
            TaskResponse()

    def test_minimal(self):
        t = TaskResponse(id="t-1")
        assert t.id == "t-1"

    def test_progress_float(self):
        t = TaskResponse(id="t-1", progress=0.42)
        assert t.progress == 0.42

    def test_result_accepts_any(self):
        """result: Optional[Any] — workers serialize arbitrary
        return values into this field. Pin the wide net."""
        assert TaskResponse(id="t-1", result={"ok": True}).result == {"ok": True}
        assert TaskResponse(id="t-1", result=42).result == 42
        assert TaskResponse(id="t-1", result="done").result == "done"

    def test_dependencies_list(self):
        t = TaskResponse(
            id="t-1",
            dependencies=[{"id": "t-0", "status": "finished"}],
            dependents=[{"id": "t-2"}],
        )
        assert t.dependencies[0]["id"] == "t-0"


class TestTaskListResponse:
    def test_tasks_required(self):
        with pytest.raises(ValidationError):
            TaskListResponse()

    def test_accepts_empty(self):
        assert TaskListResponse(tasks=[]).tasks == []
