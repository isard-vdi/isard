# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ownership / state guards of ``TaskService`` (services/tasks.py).

* ``get_task_with_owner_check`` -- unknown task -> not_found; a non-admin who is
  not the owner -> forbidden; the owner and an admin pass.
* ``cancel_task`` -- a task that is not ``queued`` -> precondition_required
  (and is not cancelled).

The real method decides; only the ``Task`` model is stubbed. Asserts the
``Error`` type.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from api.services.error import Error
from api.services.tasks import TaskService


class TestGetTaskWithOwnerCheck:
    def test_unknown_task_not_found(self):
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = False
            with pytest.raises(Error) as exc:
                TaskService.get_task_with_owner_check("ghost", "u1", "user")
        assert exc.value.error["error"] == "not_found"

    def test_non_owner_forbidden(self):
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = True
            T.return_value = SimpleNamespace(user_id="owner", status="queued")
            with pytest.raises(Error) as exc:
                TaskService.get_task_with_owner_check("t1", "intruder", "user")
        assert exc.value.error["error"] == "forbidden"

    def test_owner_passes(self):
        inst = SimpleNamespace(user_id="owner", status="queued")
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = True
            T.return_value = inst
            assert TaskService.get_task_with_owner_check("t1", "owner", "user") is inst

    def test_admin_bypasses_owner_check(self):
        inst = SimpleNamespace(user_id="someone-else", status="queued")
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = True
            T.return_value = inst
            assert (
                TaskService.get_task_with_owner_check("t1", "admin-u", "admin") is inst
            )


class TestCancelTask:
    def test_non_queued_refused_and_not_cancelled(self):
        cancel = MagicMock(name="cancel")
        inst = SimpleNamespace(
            user_id="owner", status="Started", cancel=cancel, to_dict=lambda: {}
        )
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = True
            T.return_value = inst
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
        with patch("api.services.tasks.Task") as T:
            T.exists.return_value = True
            T.return_value = inst
            assert TaskService.cancel_task("t1", "owner", "user") == {"id": "t1"}
        cancel.assert_called_once()
