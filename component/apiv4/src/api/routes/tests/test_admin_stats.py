# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/stats.py — desktop/domain status, grouped category
stats, deployments and the explicit per-kind stats routes.

The literal /stats/categories[/...] paths each get their own test so a
future re-order under that prefix surfaces immediately.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/desktops/status, /stats/domains/status
# ══════════════════════════════════════════════════════════════════════════


class TestStatusEndpoints:
    def test_desktops_status(self, monkeypatch, test_client):
        # Service returns the single ``{"total": int, "status": {...}}``
        # dict the webapp consumer expects (see
        # ``static/admin/js/desktops_status.js`` reading ``data.total`` /
        # ``data.status``). Iterating that dict like a list of rows used
        # to 500 the route with ``StatsGenericResponse(**"total")``.
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_desktops_stats",
            staticmethod(lambda: {"total": 3, "status": {"Started": 3}}),
        )
        response = test_client(
            url="/admin/item/stats/desktops/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert body["status"] == {"Started": 3}

    def test_domains_status(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_domains_status",
            staticmethod(
                lambda: {
                    "desktop": {"Started": 1},
                    "template": {},
                }
            ),
        )
        response = test_client(
            url="/admin/item/stats/domains/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["desktop"] == {"Started": 1}
        assert response.json()["template"] == {}


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/categories  — declaration-order canary
# ══════════════════════════════════════════════════════════════════════════


class TestStatsCategories:
    """The literal /stats/categories[/...] endpoints each get their own
    test so a future re-order under that prefix surfaces immediately."""

    def test_grouped_categories(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_group_by_categories",
            staticmethod(
                lambda: {
                    "cat-a": {
                        "users": {"total": 0, "status": {}, "roles": {}},
                        "desktops": {"total": 0, "status": {}},
                        "templates": {"total": 0, "status": {}},
                    }
                }
            ),
        )
        response = test_client(
            url="/admin/item/stats/categories", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert "cat-a" in response.json()["category"]

    def test_categories_deployments(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_deployments",
            staticmethod(lambda: {"cat-a": 3}),
        )
        response = test_client(
            url="/admin/item/stats/categories/deployments", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["categories"] == {"cat-a": 3}


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/{kind} — explicit per-kind routes
# ══════════════════════════════════════════════════════════════════════════


class TestStatsKind:
    def test_kind_dispatch(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(
                lambda kind: captured.update(kind=kind)
                or [{"id": "h1", "status": "Started", "only_forced": False}]
            ),
        )
        response = test_client(
            url="/admin/items/stats/hypervisors", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert captured["kind"] == "hypervisors"

    def test_unknown_kind_propagates_400(self, monkeypatch, test_client):
        def reject(kind):
            raise Error("bad_request", f"Unknown kind: {kind}")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(reject),
        )
        response = test_client(
            url="/admin/items/stats/hypervisors", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(lambda kind: {}),
        )
        response = test_client(
            url="/admin/items/stats/users", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/domains/started-count
# ══════════════════════════════════════════════════════════════════════════


class TestAdminDomainsStartedCount:
    URL = "/admin/items/domains/started-count"

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
