# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ownership / state guards of ``TaskService`` (services/tasks.py).

* ``get_task_with_owner_check`` -- unknown task -> not_found; a non-admin who is
  not the owner -> forbidden; the owner and an admin pass.
* ``cancel_task`` -- a task that is not ``queued`` -> precondition_required
  (and is not cancelled).

The real method decides; only the task lookup is stubbed. Asserts the
``Error`` type.
"""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.services import tasks as tasks_mod
from api.services.error import Error
from api.services.tasks import TaskService


@contextmanager
def _lookup(task=None):
    """Stub whichever task lookup ``_load`` happens to use.

    ``_load`` reads the task two different ways depending on which side of the
    task-pointer retirement you are on: here it is ``Task.exists`` followed by
    ``Task(id)``; once the retirement lands it is a single
    ``tasks_from_ids([id])``, and the bare ``exists`` check is gone precisely
    because it passed for a hash that could no longer be loaded.

    Stubbing only the first leaves the second picking a real, empty Redis, so
    every guard below collapses to ``not_found`` and asserts nothing about the
    guard it names. Feed BOTH — ``task=None`` means "no such task" on either
    implementation — so the test states the same thing on both sides instead of
    passing on one and lying on the other.
    """
    with ExitStack() as stack:
        if hasattr(tasks_mod, "Task"):
            T = stack.enter_context(patch("api.services.tasks.Task"))
            T.exists.return_value = task is not None
            T.return_value = task
        if hasattr(tasks_mod, "tasks_from_ids"):
            stack.enter_context(
                patch(
                    "api.services.tasks.tasks_from_ids",
                    return_value=[task] if task is not None else [],
                )
            )
        yield


class TestGetTaskWithOwnerCheck:
    def test_unknown_task_not_found(self):
        with _lookup(None):
            with pytest.raises(Error) as exc:
                TaskService.get_task_with_owner_check("ghost", "u1", "user")
        assert exc.value.error["error"] == "not_found"

    def test_non_owner_forbidden(self):
        with _lookup(SimpleNamespace(user_id="owner", status="queued")):
            with pytest.raises(Error) as exc:
                TaskService.get_task_with_owner_check("t1", "intruder", "user")
        assert exc.value.error["error"] == "forbidden"

    def test_owner_passes(self):
        inst = SimpleNamespace(user_id="owner", status="queued")
        with _lookup(inst):
            assert TaskService.get_task_with_owner_check("t1", "owner", "user") is inst

    def test_admin_bypasses_owner_check(self):
        inst = SimpleNamespace(user_id="someone-else", status="queued")
        with _lookup(inst):
            assert (
                TaskService.get_task_with_owner_check("t1", "admin-u", "admin") is inst
            )


class TestCancelTask:
    def test_non_queued_refused_and_not_cancelled(self):
        cancel = MagicMock(name="cancel")
        inst = SimpleNamespace(
            user_id="owner", status="Started", cancel=cancel, to_dict=lambda: {}
        )
        with _lookup(inst):
            with pytest.raises(Error) as exc:
                TaskService.cancel_task("t1", "owner", "user")
        assert exc.value.error["error"] == "precondition_required"
        cancel.assert_not_called()

    def test_queued_is_cancelled(self):
        cancel = MagicMock(name="cancel")
        inst = SimpleNamespace(
            user_id="owner",
            status="queued",
            cancel=cancel,
            to_dict=lambda: {"id": "t1"},
        )
        with _lookup(inst):
            assert TaskService.cancel_task("t1", "owner", "user") == {"id": "t1"}
        cancel.assert_called_once()
