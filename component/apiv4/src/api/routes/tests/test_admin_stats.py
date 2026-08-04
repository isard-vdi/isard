# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/stats.py — desktop/domain status, grouped category
stats, deployments and the explicit per-kind stats routes.

The literal /stats/categories[/...] paths each get their own test so a
future re-order under that prefix surfaces immediately.
"""

from api.routes.tests.helpers import MockJWT
from api.schemas.admin.stats import (
    StatsKindDesktop,
    StatsKindHypervisor,
    StatsKindTemplate,
    StatsKindUser,
)
from api.services.error import Error
from fastapi.responses import JSONResponse

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
#  GET /stats/{kind} — wire payload
# ══════════════════════════════════════════════════════════════════════════


def _pydantic_bytes(model, rows, **dump):
    """The bytes the per-row Pydantic round-trip used to put on the wire."""
    return JSONResponse(
        content=[model(**row).model_dump(mode="json", **dump) for row in rows]
    ).body


class TestStatsKindPayload:
    """The inventories serialise the plucked rows straight to JSON. Pin
    the bytes against the Pydantic round-trip they replaced, and pin the
    two shapes the Go collector's generated decoder cannot accept: a
    ``null`` value, and a row short of a required field."""

    def _get(self, monkeypatch, test_client, rows, url):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(lambda kind: rows),
        )
        return test_client(url=url, jwt=MockJWT(role_id="admin"))

    def test_users_bytes_match_and_drop_nulls(self, monkeypatch, test_client):
        rows = [
            {"id": "u1", "role": "admin", "category": "c1", "group": "g1"},
            # Orphan rows: a null optional, and the same field absent.
            {"id": "u2", "role": None, "category": "c1", "group": "g1"},
            {"id": "u3", "category": "c1"},
        ]
        response = self._get(monkeypatch, test_client, rows, "/admin/items/stats/users")
        assert response.status_code == 200
        assert response.content == _pydantic_bytes(
            StatsKindUser, rows, exclude_none=True
        )
        assert b"null" not in response.content

    def test_users_row_without_id_is_dropped(self, monkeypatch, test_client):
        rows = [{"id": "u1", "role": "admin"}, {"role": "admin"}, {"id": None}]
        response = self._get(monkeypatch, test_client, rows, "/admin/items/stats/users")
        assert response.status_code == 200
        assert response.json() == [{"id": "u1", "role": "admin"}]

    def test_desktops_bytes_match(self, monkeypatch, test_client):
        rows = [{"id": "d1", "user": "u1"}, {"id": "d2", "user": "u2"}]
        response = self._get(
            monkeypatch, test_client, rows, "/admin/items/stats/desktops"
        )
        assert response.status_code == 200
        assert response.content == _pydantic_bytes(StatsKindDesktop, rows)

    def test_desktops_row_without_user_is_dropped(self, monkeypatch, test_client):
        rows = [{"id": "d1", "user": "u1"}, {"id": "d2"}, {"id": "d3", "user": None}]
        response = self._get(
            monkeypatch, test_client, rows, "/admin/items/stats/desktops"
        )
        assert response.status_code == 200
        assert response.json() == [{"id": "d1", "user": "u1"}]

    def test_templates_bytes_match_and_drop_rows_without_id(
        self, monkeypatch, test_client
    ):
        rows = [{"id": "t1"}, {"id": "t2"}]
        response = self._get(
            monkeypatch, test_client, rows, "/admin/items/stats/templates"
        )
        assert response.status_code == 200
        assert response.content == _pydantic_bytes(StatsKindTemplate, rows)

        response = self._get(
            monkeypatch, test_client, rows + [{}], "/admin/items/stats/templates"
        )
        assert response.status_code == 200
        assert response.json() == rows

    def test_hypervisors_bytes_match_and_drop_incomplete_rows(
        self, monkeypatch, test_client
    ):
        rows = [
            {"id": "h1", "status": "Online", "only_forced": False},
            {"id": "h2", "status": "Offline", "only_forced": True},
        ]
        response = self._get(
            monkeypatch, test_client, rows, "/admin/items/stats/hypervisors"
        )
        assert response.status_code == 200
        assert response.content == _pydantic_bytes(StatsKindHypervisor, rows)

        response = self._get(
            monkeypatch,
            test_client,
            rows + [{"id": "h3", "status": "Online"}],
            "/admin/items/stats/hypervisors",
        )
        assert response.status_code == 200
        assert response.json() == rows


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
