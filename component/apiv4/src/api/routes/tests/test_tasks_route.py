#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from types import SimpleNamespace

import pytest
from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /tasks — user's own tasks (token_router)
# ══════════════════════════════════════════════════════════════════════════


def test_get_user_tasks(monkeypatch, test_client):
    expected_tasks = [
        {"id": "task-1", "status": "completed"},
        {"id": "task-2", "status": "queued"},
    ]

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_user_tasks",
        staticmethod(lambda user_id: expected_tasks),
    )

    jwt = MockJWT(role_id="user")
    response = test_client(url="/tasks", jwt=jwt)

    # ``response_model=list[TaskResponse]`` adds the declared optional
    # fields with None defaults; per-key asserts replace equality with
    # the partial stub (per ``feedback_fix_code_not_test.md``).
    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {"task-1", "task-2"}
    assert {row["status"] for row in body} == {"completed", "queued"}


def test_get_user_tasks_forwards_caller_user_id(monkeypatch, test_client):
    """Pin the ownership boundary — the service sees the caller's user_id,
    not anything read off the request body/query."""
    captured = {}

    def fake(user_id):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_user_tasks",
        staticmethod(fake),
    )
    jwt = MockJWT(role_id="user", user_id="u-7")
    test_client(url="/tasks", jwt=jwt)
    assert captured == {"user_id": "u-7"}


# ══════════════════════════════════════════════════════════════════════════
#  GET /task/{task_id} — single task with owner check (token_router)
# ══════════════════════════════════════════════════════════════════════════


def test_get_task(monkeypatch, test_client):
    expected_task = {
        "id": "task-1",
        "status": "completed",
        "user_id": "local-default-admin-admin",
    }
    mock_task = SimpleNamespace(to_dict=lambda: expected_task)

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_task_with_owner_check",
        staticmethod(lambda task_id, user_id, role_id: mock_task),
    )

    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/task-1", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "task-1"
    assert body["status"] == "completed"
    assert body["user_id"] == "local-default-admin-admin"


def test_get_task_not_found_returns_404(monkeypatch, test_client):
    def raise_not_found(task_id, user_id, role_id):
        raise Error("not_found", "Task not found")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_task_with_owner_check",
        staticmethod(raise_not_found),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/ghost", jwt=jwt)
    assert response.status_code == 404


def test_get_task_forbidden_returns_403(monkeypatch, test_client):
    """Service raises forbidden when a non-admin asks for another user's task.
    The route must surface that as 403, not 500."""

    def raise_forbidden(task_id, user_id, role_id):
        raise Error("forbidden", "Not authorized to access this task")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_task_with_owner_check",
        staticmethod(raise_forbidden),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/someone-elses", jwt=jwt)
    assert response.status_code == 403


def test_get_task_unexpected_error_is_500(monkeypatch, test_client):
    """Uncaught service errors become 500 via the route's except Exception arm."""

    def boom(task_id, user_id, role_id):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_task_with_owner_check",
        staticmethod(boom),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/t1", jwt=jwt)
    assert response.status_code == 500


def test_get_task_forwards_jwt_context(monkeypatch, test_client):
    """Route must pass both user_id and role_id to the owner-check service
    so admins bypass the task.user_id comparison."""
    captured = {}

    def fake(task_id, user_id, role_id):
        captured["task_id"] = task_id
        captured["user_id"] = user_id
        captured["role_id"] = role_id
        return SimpleNamespace(to_dict=lambda: {"id": task_id})

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_task_with_owner_check",
        staticmethod(fake),
    )
    jwt = MockJWT(role_id="admin", user_id="u-admin")
    test_client(url="/task/task-42", jwt=jwt)
    assert captured == {
        "task_id": "task-42",
        "user_id": "u-admin",
        "role_id": "admin",
    }


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /task/{task_id} — cancel queued task (token_router)
# ══════════════════════════════════════════════════════════════════════════


def test_cancel_task_success(monkeypatch, test_client):
    """Cancel returns 200 with EmptyResponse — the previous service
    return value isn't surfaced to the wire (response_model=EmptyResponse)."""
    calls = []
    monkeypatch.setattr(
        "api.services.tasks.TaskService.cancel_task",
        staticmethod(lambda task_id, user_id, role_id: calls.append(task_id) or None),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/task-1", method="DELETE", jwt=jwt)
    assert response.status_code == 204
    assert calls == ["task-1"]


def test_cancel_task_not_found_returns_404(monkeypatch, test_client):
    def raise_not_found(task_id, user_id, role_id):
        raise Error("not_found", "Task not found")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.cancel_task",
        staticmethod(raise_not_found),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/ghost", method="DELETE", jwt=jwt)
    assert response.status_code == 404


def test_cancel_task_wrong_status_returns_428(monkeypatch, test_client):
    """Cancelling a non-queued task must surface precondition_required as 428
    (RFC 6585), which is what the Error class in isardvdi_common maps it to and
    what the route now declares."""

    def raise_precondition(task_id, user_id, role_id):
        raise Error("precondition_required", "Task should be queued, but is completed")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.cancel_task",
        staticmethod(raise_precondition),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/task-done", method="DELETE", jwt=jwt)
    assert response.status_code == 428


def test_cancel_task_forwards_jwt_context(monkeypatch, test_client):
    """DELETE route must hand the JWT's user_id + role_id to the service
    so the owner check inside cancel_task() can run."""
    captured = {}

    def fake(task_id, user_id, role_id):
        captured["args"] = (task_id, user_id, role_id)
        return {"id": task_id, "status": "canceled"}

    monkeypatch.setattr(
        "api.services.tasks.TaskService.cancel_task",
        staticmethod(fake),
    )
    jwt = MockJWT(role_id="user", user_id="u-5")
    test_client(url="/task/t-9", method="DELETE", jwt=jwt)
    assert captured["args"] == ("t-9", "u-5", "user")


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/tasks — all/category tasks (manager_router)
# ══════════════════════════════════════════════════════════════════════════


def test_get_admin_tasks_admin_sees_all(monkeypatch, test_client):
    expected = [
        {"id": "t-1", "user_id": "u-1"},
        {"id": "t-2", "user_id": "u-2"},
    ]
    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_admin_tasks",
        staticmethod(lambda user_id, role_id, category_id, limit, offset: expected),
    )
    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/tasks", jwt=jwt)
    assert response.status_code == 200
    body = response.json()
    assert {row["id"] for row in body} == {"t-1", "t-2"}
    assert {row["user_id"] for row in body} == {"u-1", "u-2"}


def test_get_admin_tasks_forwards_role_and_category(monkeypatch, test_client):
    """Managers scope to their category; the route must hand the service the
    caller's role_id + category_id so that scoping can happen."""
    captured = {}

    def fake(user_id, role_id, category_id, limit, offset):
        captured["user_id"] = user_id
        captured["role_id"] = role_id
        captured["category_id"] = category_id
        captured["limit"] = limit
        captured["offset"] = offset
        return []

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_admin_tasks",
        staticmethod(fake),
    )
    jwt = MockJWT(role_id="manager", user_id="mgr-1", category_id="cat-a")
    test_client(
        url="/admin/tasks",
        jwt=jwt,
        db_tables_data={
            "categories": [
                {"id": "default"},
                {"id": "cat-a", "maintenance": False},
            ],
        },
    )
    assert captured == {
        "user_id": "mgr-1",
        "role_id": "manager",
        "category_id": "cat-a",
        # Bug 38 hardening: route defaults to a bounded page so the
        # response is never the full RQ history.
        "limit": 200,
        "offset": 0,
    }


def test_get_admin_tasks_pagination_query_params(monkeypatch, test_client):
    """Bug 38: the route accepts ``limit`` + ``offset`` query params
    and forwards them to the service. Pin the wiring so a future
    refactor doesn't drop the pagination contract."""
    captured = {}

    def fake(user_id, role_id, category_id, limit, offset):
        captured["limit"] = limit
        captured["offset"] = offset
        return []

    monkeypatch.setattr(
        "api.services.tasks.TaskService.get_admin_tasks",
        staticmethod(fake),
    )

    response = test_client(
        url="/admin/tasks?limit=50&offset=100",
        jwt=MockJWT(role_id="admin"),
    )
    assert response.status_code == 200
    assert captured == {"limit": 50, "offset": 100}


def test_get_admin_tasks_rejects_oversize_limit(test_client):
    """Bug 38: the upper bound on ``limit`` (10000) is enforced at the
    boundary so a typo can't request the unbounded payload that was
    the original 12 MB / 32 s problem."""
    response = test_client(
        url="/admin/tasks?limit=999999",
        jwt=MockJWT(role_id="admin"),
    )
    assert response.status_code == 400


def test_get_admin_tasks_rejects_advanced_role(test_client):
    """manager_router blocks role=advanced (advanced can read their own via
    /tasks, but not the admin/manager-wide view)."""
    jwt = MockJWT(role_id="advanced")
    response = test_client(url="/admin/tasks", jwt=jwt)
    assert response.status_code == 403


def test_get_admin_tasks_rejects_user_role(test_client):
    jwt = MockJWT(role_id="user")
    response = test_client(url="/admin/tasks", jwt=jwt)
    assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/task/{task_id}/retry — retry one failed task (admin_router)
# ══════════════════════════════════════════════════════════════════════════


def test_retry_task(monkeypatch, test_client):
    """Replaces v3 /task/{id}/retry shim. ``response_model=EmptyResponse``;
    the route doesn't surface the service return value."""
    calls = []
    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_task",
        staticmethod(lambda task_id: calls.append(task_id) or None),
    )

    jwt = MockJWT()
    response = test_client(url="/admin/task/task-1/retry", method="PUT", jwt=jwt)

    assert response.status_code == 204
    assert calls == ["task-1"]


def test_retry_task_not_found_returns_404(monkeypatch, test_client):
    def raise_not_found(task_id):
        raise Error("not_found", "Task not found")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_task",
        staticmethod(raise_not_found),
    )
    jwt = MockJWT()
    response = test_client(url="/admin/task/ghost/retry", method="PUT", jwt=jwt)
    assert response.status_code == 404


def test_retry_task_wrong_status_returns_428(monkeypatch, test_client):
    """Retry is only valid from status=failed; precondition_required
    surfaces as 428 (see test_cancel_task_wrong_status_returns_428)."""

    def raise_precondition(task_id):
        raise Error("precondition_required", "Task should be failed, but is queued")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_task",
        staticmethod(raise_precondition),
    )
    jwt = MockJWT()
    response = test_client(url="/admin/task/t-queued/retry", method="PUT", jwt=jwt)
    assert response.status_code == 428


def test_retry_task_rejects_non_admin(test_client):
    """admin_router → managers can't retry. No service patch — the role
    guard fires before the handler runs."""
    jwt = MockJWT(role_id="manager")
    response = test_client(url="/admin/task/t-1/retry", method="PUT", jwt=jwt)
    assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/tasks/retry — retry all failed storage tasks (admin_router)
# ══════════════════════════════════════════════════════════════════════════


def test_retry_all_failed_tasks(monkeypatch, test_client):
    calls = []
    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_all_failed_tasks",
        staticmethod(lambda: calls.append("retry") or {}),
    )

    jwt = MockJWT()
    response = test_client(url="/admin/tasks/retry", method="PUT", jwt=jwt)

    # Route returns 204 (no body) like every other ``EmptyResponse`` route.
    assert response.status_code == 204
    assert calls == ["retry"]


def test_retry_all_failed_tasks_rejects_non_admin(test_client):
    """admin_router blocks managers from bulk retry."""
    jwt = MockJWT(role_id="manager")
    response = test_client(url="/admin/tasks/retry", method="PUT", jwt=jwt)
    assert response.status_code == 403


def test_retry_all_failed_tasks_unexpected_error_is_500(monkeypatch, test_client):
    def boom():
        raise RuntimeError("storage backend down")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_all_failed_tasks",
        staticmethod(boom),
    )
    jwt = MockJWT()
    response = test_client(url="/admin/tasks/retry", method="PUT", jwt=jwt)
    assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/task/{task_id} — admin cancel, no owner/status gate (P2.4 §7/3)
# ══════════════════════════════════════════════════════════════════════════


def test_admin_cancel_task_success(monkeypatch, test_client):
    """Admin cancel returns 204; the service is handed only the task_id (no
    owner/role gate)."""
    calls = []
    monkeypatch.setattr(
        "api.services.tasks.TaskService.admin_cancel_task",
        staticmethod(lambda task_id: calls.append(task_id) or {}),
    )
    response = test_client(
        url="/admin/task/task-1", method="DELETE", jwt=MockJWT(role_id="admin")
    )
    assert response.status_code == 204
    assert calls == ["task-1"]


def test_admin_cancel_task_gone_returns_404(monkeypatch, test_client):
    def raise_not_found(task_id):
        raise Error("not_found", "Task not found")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.admin_cancel_task",
        staticmethod(raise_not_found),
    )
    response = test_client(
        url="/admin/task/ghost", method="DELETE", jwt=MockJWT(role_id="admin")
    )
    assert response.status_code == 404


def test_admin_cancel_task_rejects_user(test_client):
    """admin_router — a plain user cannot admin-cancel (guard fires first)."""
    response = test_client(
        url="/admin/task/t-1", method="DELETE", jwt=MockJWT(role_id="user")
    )
    assert response.status_code == 403


def test_admin_cancel_task_rejects_manager(test_client):
    """admin_router — a manager cannot admin-cancel."""
    response = test_client(
        url="/admin/task/t-1", method="DELETE", jwt=MockJWT(role_id="manager")
    )
    assert response.status_code == 403


def test_admin_cancel_task_service_no_owner_gate(monkeypatch):
    """The service cancels with NO ownership/status gate: present -> cancel()
    is called and {} returned, with no user_id/role_id ever consulted."""
    from api.services.tasks import TaskService

    calls = {}

    class FakeTask:
        def cancel(self):
            calls["canceled"] = True

    def fake_load(task_ids):
        calls["loaded"] = task_ids
        return [FakeTask()]

    monkeypatch.setattr("api.services.tasks.tasks_from_ids", fake_load)
    out = TaskService.admin_cancel_task("t-9")
    assert out == {}
    assert calls == {"loaded": ["t-9"], "canceled": True}


def test_admin_cancel_task_service_gone_raises(monkeypatch):
    """A task whose job is gone — or is there but unloadable — raises not_found
    (-> 404 at the route), never a bare NoSuchJobError the route would have to
    turn into a 500."""
    from api.services.tasks import TaskService

    monkeypatch.setattr("api.services.tasks.tasks_from_ids", lambda task_ids: [])
    with pytest.raises(Error) as excinfo:
        TaskService.admin_cancel_task("ghost")
    assert excinfo.value.status_code == 404


def test_cancel_task_forbidden_returns_403(monkeypatch, test_client):
    """``cancel_task`` runs the owner check first, so a non-owner gets 403.
    Proves the status the declaration below has to carry."""

    def raise_forbidden(task_id, user_id, role_id):
        raise Error("forbidden", "Not authorized to access this task")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.cancel_task",
        staticmethod(raise_forbidden),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/task/t-others", method="DELETE", jwt=jwt)
    assert response.status_code == 403


def test_retry_task_stranded_lane_returns_429(monkeypatch, test_client):
    """``Task.retry`` takes the same mandatory consumer gate as ``create_task``
    and raises a typed 429 for a lane with no live worker. It resolves to
    apiv4's own Error in-process, so the route re-raises it untouched."""

    def raise_stranded(task_id):
        raise Error("too_many_requests", "lane has no consumer")

    monkeypatch.setattr(
        "api.services.tasks.TaskService.retry_task",
        staticmethod(raise_stranded),
    )
    jwt = MockJWT()
    response = test_client(url="/admin/task/t-stranded/retry", method="PUT", jwt=jwt)
    assert response.status_code == 429


# ══════════════════════════════════════════════════════════════════════════
#  Declared responses == what the routes can actually raise
# ══════════════════════════════════════════════════════════════════════════

# Every status each task route can really produce, and the test that proves it.
# The generated clients are built from this schema, so a wrong declaration is a
# wrong client: 412 was declared where the runtime raises 428
# (``precondition_required`` maps to 428), and the owner check's 403 and the
# retry lane gate's 429 were not declared at all. 401 is contributed by the
# authenticated router itself rather than by the handler.
TASK_ROUTE_RESPONSES = {
    # 403 test_get_task_forbidden_returns_403
    # 404 test_get_task_not_found_returns_404
    # 500 test_get_task_unexpected_error_is_500
    ("GET", "/api/v4/task/{task_id}"): {401, 403, 404, 500},
    # 403 test_cancel_task_forbidden_returns_403
    # 404 test_cancel_task_not_found_returns_404
    # 428 test_cancel_task_wrong_status_returns_428
    ("DELETE", "/api/v4/task/{task_id}"): {401, 403, 404, 428, 500},
    # 404 test_admin_cancel_task_gone_returns_404
    ("DELETE", "/api/v4/admin/task/{task_id}"): {401, 404, 500},
    # 404 test_retry_task_not_found_returns_404
    # 428 test_retry_task_wrong_status_returns_428
    # 429 test_retry_task_stranded_lane_returns_429
    ("PUT", "/api/v4/admin/task/{task_id}/retry"): {401, 404, 428, 429, 500},
}


def _declared_statuses(method: str, path: str) -> set[int]:
    from api import app

    for route in app.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            return set(route.responses or {})
    raise AssertionError(f"no route registered for {method} {path}")


@pytest.mark.parametrize(
    ("method", "path"), sorted(TASK_ROUTE_RESPONSES), ids=lambda v: str(v)
)
def test_declared_responses_match_what_the_route_can_raise(method, path):
    assert _declared_statuses(method, path) == TASK_ROUTE_RESPONSES[(method, path)]
