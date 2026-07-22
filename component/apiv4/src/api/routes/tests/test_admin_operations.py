# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/operations.py — list / start / stop hypervisors via the
external operations API. All endpoints live on admin_router and are
gated by ``AdminOperationsService.is_operations_api_enabled()`` — when
the operations API is not configured, every endpoint must return 403,
not silently call into a broken downstream.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error


def _enable(monkeypatch, enabled=True):
    monkeypatch.setattr(
        "api.routes.admin.operations.AdminOperationsService.is_operations_api_enabled",
        staticmethod(lambda: enabled),
    )


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/operations/hypervisors
# ══════════════════════════════════════════════════════════════════════════


class TestListHypervisors:
    URL = "/admin/items/operations/hypervisors"

    def test_admin_lists_hypervisors(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(lambda: [{"id": "h1", "state": "ON"}]),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "h1"

    def test_returns_403_when_operations_api_disabled(self, monkeypatch, test_client):
        """The handler must short-circuit before touching the downstream
        service when operations API is not configured. Otherwise an
        un-configured cluster surfaces 500 errors with stack traces.
        """
        _enable(monkeypatch, enabled=False)

        def should_not_be_called():
            raise AssertionError("list_hypervisors must not be called")

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(should_not_be_called),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        _enable(monkeypatch)

        def fail(_=None):
            raise Error("not_found", "Operations API endpoint not found")

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(fail),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 404

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        _enable(monkeypatch)

        def boom():
            raise RuntimeError("Operations service unreachable")

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.list_hypervisors",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/operations/hypervisor/{id}  — start
# ══════════════════════════════════════════════════════════════════════════


class TestStartHypervisor:
    URL = "/admin/item/operations/hypervisor/h-42"

    def test_admin_starts(self, monkeypatch, test_client):
        _enable(monkeypatch)
        captured = {}

        def fake_start(hyp_id):
            captured["hyp_id"] = hyp_id
            return {"state": "starting"}

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.start_hypervisor",
            staticmethod(fake_start),
        )
        response = test_client(url=self.URL, method="PUT", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["hyp_id"] == "h-42"
        assert response.json()["state"] == "starting"

    def test_disabled_operations_api_returns_403_before_start(
        self, monkeypatch, test_client
    ):
        _enable(monkeypatch, enabled=False)

        def should_not_be_called(hyp_id):
            raise AssertionError(
                "start_hypervisor must not run when operations api disabled"
            )

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.start_hypervisor",
            staticmethod(should_not_be_called),
        )
        response = test_client(url=self.URL, method="PUT", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.start_hypervisor",
            staticmethod(lambda h: {}),
        )
        response = test_client(url=self.URL, method="PUT", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  DELETE /admin/operations/hypervisor/{id} — stop (DESTRUCTIVE)
# ══════════════════════════════════════════════════════════════════════════


class TestStopHypervisor:
    URL = "/admin/item/operations/hypervisor/h-42"

    def test_admin_stops(self, monkeypatch, test_client):
        _enable(monkeypatch)
        captured = {}

        def fake_stop(hyp_id):
            captured["hyp_id"] = hyp_id
            return {"state": "stopping"}

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.stop_hypervisor",
            staticmethod(fake_stop),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["hyp_id"] == "h-42"

    def test_disabled_operations_api_returns_403_before_stop(
        self, monkeypatch, test_client
    ):
        """Critical fail-safe: a misconfigured operations API must NOT
        let an admin send a stop signal that could leak to the wrong
        downstream host. 403 before reaching the service.
        """
        _enable(monkeypatch, enabled=False)

        def should_not_be_called(hyp_id):
            raise AssertionError(
                "stop_hypervisor must not run when operations api disabled"
            )

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.stop_hypervisor",
            staticmethod(should_not_be_called),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.stop_hypervisor",
            staticmethod(lambda h: {}),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403

    def test_user_forbidden(self, monkeypatch, test_client):
        _enable(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.stop_hypervisor",
            staticmethod(lambda h: {}),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_typed_error_propagates(self, monkeypatch, test_client):
        _enable(monkeypatch)

        def reject(hyp_id):
            raise Error("not_found", "Hypervisor not registered with operations")

        monkeypatch.setattr(
            "api.routes.admin.operations.AdminOperationsService.stop_hypervisor",
            staticmethod(reject),
        )
        response = test_client(
            url=self.URL, method="DELETE", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404
