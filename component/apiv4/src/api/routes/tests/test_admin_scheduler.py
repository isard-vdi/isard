#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT

MOCK_SYSTEM_JOBS = [
    {
        "id": "job-sys-1",
        "name": "cleanup_tokens",
        "kind": "interval",
        "next_run_time": 1800000000,
    },
    {
        "id": "job-sys-2",
        "name": "purge_recycle_bin",
        "kind": "cron",
        "next_run_time": 1800003600,
    },
]

MOCK_BOOKINGS_JOBS = [
    {
        "id": "job-book-1",
        "name": "booking_start",
        "kind": "date",
        "next_run_time": 1800000500,
        "kwargs": {"booking_id": "b1"},
    },
]


def test_admin_scheduler_jobs_system_returns_list(monkeypatch, test_client):
    """GET /admin/scheduler/jobs/system returns the list of system jobs."""
    captured_kwargs = {}

    def fake_admin_table_list(table, **kwargs):
        captured_kwargs["table"] = table
        captured_kwargs.update(kwargs)
        return MOCK_SYSTEM_JOBS

    monkeypatch.setattr(
        "api.services.admin_scheduler.ApiAdmin.admin_table_list",
        staticmethod(fake_admin_table_list),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/scheduler/jobs/system", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == MOCK_SYSTEM_JOBS
    # Verify the service queried the right table/index/filter
    assert captured_kwargs["table"] == "scheduler_jobs"
    assert captured_kwargs["id"] == "system"
    assert captured_kwargs["index"] == "type"
    assert captured_kwargs["order_by"] == "next_run_time"
    assert "kwargs" not in captured_kwargs["pluck"]


def test_admin_scheduler_jobs_bookings_returns_list(monkeypatch, test_client):
    """GET /admin/scheduler/jobs/bookings returns the list of bookings jobs with kwargs."""
    captured_kwargs = {}

    def fake_admin_table_list(table, **kwargs):
        captured_kwargs["table"] = table
        captured_kwargs.update(kwargs)
        return MOCK_BOOKINGS_JOBS

    monkeypatch.setattr(
        "api.services.admin_scheduler.ApiAdmin.admin_table_list",
        staticmethod(fake_admin_table_list),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/scheduler/jobs/bookings", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == MOCK_BOOKINGS_JOBS
    assert captured_kwargs["id"] == "bookings"
    # bookings variant must include kwargs in pluck (used by UI to show booking target)
    assert "kwargs" in captured_kwargs["pluck"]


def test_admin_scheduler_jobs_system_forbidden_for_non_admin(monkeypatch, test_client):
    """Non-admin roles must be rejected by admin router dependency."""
    monkeypatch.setattr(
        "api.services.admin_scheduler.ApiAdmin.admin_table_list",
        staticmethod(lambda *a, **kw: MOCK_SYSTEM_JOBS),
    )

    jwt = MockJWT(role_id="user")
    response = test_client(url="/admin/scheduler/jobs/system", jwt=jwt)

    assert response.status_code == 403


def test_admin_scheduler_jobs_system_handles_service_error(monkeypatch, test_client):
    """Unexpected service failures surface as 500 with internal_server error."""

    def boom(*a, **kw):
        raise RuntimeError("db connection lost")

    monkeypatch.setattr(
        "api.services.admin_scheduler.ApiAdmin.admin_table_list",
        staticmethod(boom),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/scheduler/jobs/system", jwt=jwt)

    assert response.status_code == 500
    body = response.json()
    assert body.get("error") == "internal_server"
