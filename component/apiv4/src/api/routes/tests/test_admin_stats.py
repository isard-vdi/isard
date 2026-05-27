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
        response = test_client(url="/admin/item/stats", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json()["users"] == 10

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(lambda: {}),
        )
        response = test_client(url="/admin/item/stats", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(lambda: {}),
        )
        response = test_client(url="/admin/item/stats", jwt=MockJWT(role_id="manager"))
        assert response.status_code == 403

    def test_unexpected_exception_returns_500(self, monkeypatch, test_client):
        def boom():
            raise RuntimeError("DB down")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_general_stats",
            staticmethod(boom),
        )
        response = test_client(url="/admin/item/stats", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500


# ══════════════════════════════════════════════════════════════════════════
#  GET /stats/desktops/status, /stats/domains/status, /stats/category/status
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

    def test_category_status(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_category_status",
            staticmethod(lambda: [{"id": "cat-a", "wrong": 0}]),
        )
        response = test_client(
            url="/admin/item/stats/category/status", jwt=MockJWT(role_id="admin")
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

    def test_categories_limits(self, monkeypatch, test_client):
        self._stub_kind_state_should_not_run(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_limits_hardware",
            staticmethod(lambda: [{"id": "cat-a", "hardware": {}}]),
        )
        response = test_client(
            url="/admin/item/stats/categories/limits", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_categories_deployments(self, monkeypatch, test_client):
        self._stub_kind_state_should_not_run(monkeypatch)
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_categories_deployments",
            staticmethod(lambda: {"cat-a": 3}),
        )
        response = test_client(
            url="/admin/item/stats/categories/deployments", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json()["categories"] == {"cat-a": 3}

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
            url="/admin/item/stats/categories/desktop", jwt=MockJWT(role_id="admin")
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
            url="/admin/item/stats/categories/desktop/Started",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured == {"kind": "desktop", "state": "Started"}


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
