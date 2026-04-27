# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/stats.py — general/desktop/domain/category stats and
the catch-all /stats/{kind} dispatcher.

This file is the route-declaration-order canary: admin/stats.py
declares ~10 endpoints under /stats/, with three literal paths
(/stats/categories, /stats/categories/limits,
/stats/categories/deployments) that MUST match before the
/stats/categories/{kind} and /stats/{kind} catch-alls. Each literal
endpoint here gets its own test that asserts the catch-all service
method is NEVER called — so a future re-order surfaces immediately
instead of silently bleeding data through the wrong handler.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /stats   (general)
# ══════════════════════════════════════════════════════════════════════════


class TestGeneralStats:
    def test_admin_gets_general(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(lambda: {"users": 10, "desktops": 50}),
        )
        response = test_client(url="/stats", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["users"] == 10

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(lambda: {}),
        )
        response = test_client(url="/stats", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(lambda: {}),
        )
        response = test_client(url="/stats", jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("DB down")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(boom),
        )
        response = test_client(url="/stats", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/desktops/status, /stats/domains/status, /stats/category/status
# ══════════════════════════════════════════════════════════════════════════


class TestStatusEndpoints:
    def test_desktops_status(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_desktops_stats",
            staticmethod(lambda: [{"status": "Started", "count": 3}]),
        )
        response = test_client(
            url="/stats/desktops/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_domains_status(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_domains_status",
            staticmethod(lambda: [{"kind": "desktop", "status": "Started"}]),
        )
        response = test_client(
            url="/stats/domains/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_category_status(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_category_status",
            staticmethod(lambda: [{"id": "cat-a", "wrong": 0}]),
        )
        response = test_client(
            url="/stats/category/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        # The handler wraps in {"categories": ...}.
        assert response.json()["categories"][0]["id"] == "cat-a"


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/categories  — declaration-order canary
# ══════════════════════════════════════════════════════════════════════════


class TestStatsCategories:
    """Each literal /stats/categories[/...] endpoint must match before
    the /stats/categories/{kind} catch-all. We pin this by setting
    get_categories_kind_state to assert it's NEVER called for the
    literal endpoints.
    """

    def _stub_kind_state_should_not_run(self, monkeypatch):
        def should_not_run(*a, **k):
            raise AssertionError(
                "get_categories_kind_state called — declaration-order regression "
                "in admin/stats.py: literal endpoint matched the {kind} catch-all"
            )

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_kind_state",
            staticmethod(should_not_run),
        )

    def test_grouped_categories(self, monkeypatch, test_client):
        self._stub_kind_state_should_not_run(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_group_by_categories",
            staticmethod(lambda: [{"id": "cat-a"}]),
        )
        response = test_client(url="/stats/categories", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["category"][0]["id"] == "cat-a"

    def test_categories_limits(self, monkeypatch, test_client):
        self._stub_kind_state_should_not_run(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_limits_hardware",
            staticmethod(lambda: [{"id": "cat-a", "hardware": {}}]),
        )
        response = test_client(
            url="/stats/categories/limits", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_categories_deployments(self, monkeypatch, test_client):
        self._stub_kind_state_should_not_run(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_deployments",
            staticmethod(lambda: [{"id": "cat-a", "deployments": 3}]),
        )
        response = test_client(
            url="/stats/categories/deployments", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_categories_kind_only(self, monkeypatch, test_client):
        captured = {}

        def fake(kind, state=None):
            captured["kind"] = kind
            captured["state"] = state
            return [{"id": "cat-a"}]

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_kind_state",
            staticmethod(fake),
        )
        response = test_client(
            url="/stats/categories/desktop", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured == {"kind": "desktop", "state": None}

    def test_categories_kind_state(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_kind_state",
            staticmethod(
                lambda kind, state: captured.update(kind=kind, state=state) or []
            ),
        )
        response = test_client(
            url="/stats/categories/desktop/Started",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured == {"kind": "desktop", "state": "Started"}


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/{kind} — top-level catch-all
# ══════════════════════════════════════════════════════════════════════════


class TestStatsKind:
    def test_kind_dispatch(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(lambda kind: captured.update(kind=kind) or {"data": []}),
        )
        response = test_client(url="/stats/hypervisors", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert captured["kind"] == "hypervisors"

    def test_unknown_kind_propagates_400(self, monkeypatch, test_client):
        def reject(kind):
            raise Error("bad_request", f"Unknown kind: {kind}")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(reject),
        )
        response = test_client(url="/stats/no_such_kind", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(lambda kind: {}),
        )
        response = test_client(url="/stats/users", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/domains/started-count
# ══════════════════════════════════════════════════════════════════════════


class TestAdminDomainsStartedCount:
    URL = "/admin/domains/started-count"

    def test_admin_gets_count(self, monkeypatch, test_client):
        """The route header note explicitly says this 3-segment path
        cannot collide with /admin/domains/{field}/{kind} on
        manager_router because the latter is 4 segments. Assert that
        the dedicated handler runs by patching it directly."""
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_domains_by_category_count",
            staticmethod(lambda: [{"id": "cat-a", "count": 5}]),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()[0]["count"] == 5

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_domains_by_category_count",
            staticmethod(lambda: []),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="user"))
        assert response.status_code == 403
