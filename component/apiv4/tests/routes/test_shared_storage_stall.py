"""Shared storage stall: hypervisor health reports in, fast 503s out.

* ``PUT /admin/item/hypervisor/{id}/health`` stores the report with the
  server's receive time, which is what the engine judges staleness by.
* ``GET /admin/item/shared-storage-stall`` exposes the engine's condition.
* While it is active, starting or creating a desktop fails at once with 503
  "Service temporarily unavailable" instead of queueing behind the storage.
"""

import time

import pytest
from isardvdi_common.helpers.shared_storage_stall import SharedStorageStall
from rethinkdb import r
from rethinkdb_mock import MockThink
from tests.routes.helpers import MockJWT

STALL = {
    "active": True,
    "since": 1700000000.0,
    "hypervisors": ["hyper-1", "hyper-2"],
    "mounts": ["/isard/groups"],
    "online": 3,
}


@pytest.fixture(autouse=True)
def fresh_cache(monkeypatch):
    monkeypatch.setattr(SharedStorageStall, "_cached_at", 0.0)
    monkeypatch.setattr(SharedStorageStall, "_cached", None)


def _bypass_owns_domain_id(monkeypatch):
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )


def _config(stall=None):
    row = {"id": 1, "maintenance": False}
    if stall is not None:
        row["shared_storage_stall"] = stall
    return {"config": [row]}


class TestHealthReport:
    def test_stored_with_the_server_receive_time(self, test_client_with_conn):
        tables = {"hypervisors": [{"id": "hyper-1"}], **_config()}
        mock_db = MockThink({"dbs": {"isard": {"tables": tables}}, "default": "isard"})
        before = time.time()
        with mock_db.connect() as conn:
            response = test_client_with_conn(
                db_tables_data=tables,
                conn=conn,
                url="/admin/item/hypervisor/hyper-1/health",
                method="PUT",
                body={
                    "health": {
                        "timestamp": 1,
                        "hung_mounts": ["/isard/groups"],
                        "received_at": 2,
                    }
                },
                jwt=MockJWT(),
            )
            health = r.table("hypervisors").get("hyper-1").run(conn)["health"]

        assert response.status_code == 204
        assert health["hung_mounts"] == ["/isard/groups"]
        # never the hypervisor's own clock, not even if it sends one
        assert health["received_at"] >= before

    def test_a_report_replaces_the_previous_one(self, test_client_with_conn):
        tables = {
            "hypervisors": [
                {"id": "hyper-1", "health": {"hung_mounts": ["/isard/old"]}}
            ],
            **_config(),
        }
        mock_db = MockThink({"dbs": {"isard": {"tables": tables}}, "default": "isard"})
        with mock_db.connect() as conn:
            test_client_with_conn(
                db_tables_data=tables,
                conn=conn,
                url="/admin/item/hypervisor/hyper-1/health",
                method="PUT",
                body={"health": {"hung_mounts": []}},
                jwt=MockJWT(),
            )
            health = r.table("hypervisors").get("hyper-1").run(conn)["health"]

        assert health["hung_mounts"] == []

    def test_a_body_without_health_is_rejected(self, test_client):
        response = test_client(
            url="/admin/item/hypervisor/hyper-1/health",
            method="PUT",
            body={"other": 1},
            jwt=MockJWT(),
            db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
        )
        assert response.status_code == 400

    def test_a_user_cannot_report(self, test_client):
        response = test_client(
            url="/admin/item/hypervisor/hyper-1/health",
            method="PUT",
            body={"health": {}},
            jwt=MockJWT(role_id="user"),
            db_tables_data={"hypervisors": [{"id": "hyper-1"}]},
        )
        assert response.status_code in (401, 403)


class TestStallCondition:
    def test_inactive_when_never_declared(self, test_client):
        response = test_client(url="/admin/item/shared-storage-stall", jwt=MockJWT())
        assert response.status_code == 200
        assert response.json()["active"] is False

    def test_active_with_its_detail(self, test_client):
        response = test_client(
            url="/admin/item/shared-storage-stall",
            jwt=MockJWT(),
            db_tables_data=_config(STALL),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["active"] is True
        assert body["hypervisors"] == ["hyper-1", "hyper-2"]
        assert body["mounts"] == ["/isard/groups"]


def _assert_503(response):
    assert response.status_code == 503
    body = response.json()
    assert body["description_code"] == "service_temporarily_unavailable"
    assert body["msg"] == "Service temporarily unavailable"


class TestFastRefusal:
    def test_start(self, monkeypatch, test_client):
        _bypass_owns_domain_id(monkeypatch)
        calls = []
        monkeypatch.setattr(
            "api.services.desktops.DesktopService.start_desktop",
            staticmethod(lambda *a, **k: calls.append(a)),
        )
        response = test_client(
            url="/item/desktop/desktop-1/start",
            method="PUT",
            jwt=MockJWT(),
            db_tables_data=_config(STALL),
        )
        _assert_503(response)
        assert calls == []

    def test_create(self, monkeypatch, test_client):
        calls = []
        monkeypatch.setattr(
            "api.services.desktops.DesktopService.create_desktop",
            staticmethod(lambda *a, **k: calls.append(a)),
        )
        response = test_client(
            url="/item/desktop",
            method="POST",
            body={"name": "d", "template_id": "t-1"},
            jwt=MockJWT(),
            db_tables_data=_config(STALL),
        )
        _assert_503(response)
        assert calls == []

    def test_create_nonpersistent(self, monkeypatch, test_client):
        calls = []
        monkeypatch.setattr(
            "api.services.desktops.DesktopService.create_nonpersistent_desktop",
            staticmethod(lambda *a, **k: calls.append(a)),
        )
        response = test_client(
            url="/item/desktop/new-nonpersistent",
            method="POST",
            body={"template_id": "template-1"},
            jwt=MockJWT(),
            db_tables_data=_config(STALL),
        )
        _assert_503(response)
        assert calls == []

    def test_a_cleared_condition_lets_the_start_through(self, monkeypatch, test_client):
        from api import app
        from api.dependencies.storage_pools import check_virt_storage_pool_availability

        _bypass_owns_domain_id(monkeypatch)
        calls = []
        monkeypatch.setattr(
            "api.services.desktops.DesktopService.start_desktop",
            staticmethod(lambda *a, **k: calls.append(a)),
        )

        async def no_pool_check():
            return None

        app.dependency_overrides[check_virt_storage_pool_availability] = no_pool_check
        try:
            response = test_client(
                url="/item/desktop/desktop-1/start",
                method="PUT",
                jwt=MockJWT(),
                db_tables_data=_config(
                    dict(STALL, active=False, cleared_at=1700000100.0)
                ),
            )
        finally:
            app.dependency_overrides.pop(check_virt_storage_pool_availability, None)

        assert response.status_code == 200
        assert len(calls) == 1
