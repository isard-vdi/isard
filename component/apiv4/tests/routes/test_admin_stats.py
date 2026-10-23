# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/stats.py — desktop/domain status, grouped category
stats, deployments and the explicit per-kind stats routes.

The literal /stats/categories[/...] paths each get their own test so a
future re-order under that prefix surfaces immediately.
"""

from api.schemas.admin.stats import (
    StatsKindDesktop,
    StatsKindHypervisor,
    StatsKindTemplate,
    StatsKindUser,
)
from api.services.error import Error
from fastapi.responses import JSONResponse
from tests.routes.helpers import MockJWT

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

    def test_unavailable_cache_is_a_503(self, monkeypatch, test_client):
        """A wedged refresh past max_stale is unavailable data, not a 500."""
        from isardvdi_common.helpers.stale_while_revalidate import CacheUnavailable

        def wedged():
            raise CacheUnavailable("refresh has not answered")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_domains_status",
            staticmethod(wedged),
        )
        response = test_client(
            url="/admin/item/stats/domains/status", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 503
        assert response.json()["error"] == "service_unavailable"

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
        assert response.content == _pydantic_bytes(
            StatsKindHypervisor, rows, exclude_none=True
        )

        response = self._get(
            monkeypatch,
            test_client,
            rows + [{"id": "h3", "status": "Online"}],
            "/admin/items/stats/hypervisors",
        )
        assert response.status_code == 200
        assert response.json() == rows

    def test_hypervisors_carry_the_degraded_state_without_nulls(
        self, monkeypatch, test_client
    ):
        reason = "storage: not responding: /isard/groups"
        rows = [
            {
                "id": "h1",
                "status": "Online",
                "only_forced": False,
                "degraded": {"is_degraded": True, "reason": reason},
            },
            {
                "id": "h2",
                "status": "Online",
                "only_forced": False,
                "degraded": {"is_degraded": False, "reason": None},
            },
            {"id": "h3", "status": "Online", "only_forced": False},
        ]
        response = self._get(
            monkeypatch, test_client, rows, "/admin/items/stats/hypervisors"
        )
        assert response.status_code == 200
        assert response.json() == [
            {
                "id": "h1",
                "status": "Online",
                "only_forced": False,
                "degraded": True,
                "degraded_reason": reason,
            },
            {"id": "h2", "status": "Online", "only_forced": False},
            {"id": "h3", "status": "Online", "only_forced": False},
        ]
        assert b"null" not in response.content
        assert rows[0]["degraded"] == {"is_degraded": True, "reason": reason}


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


class TestStatsKindOffLoop:
    def test_inventory_is_encoded_in_the_reading_thread(self, monkeypatch, test_client):
        import threading

        import api.routes.admin.stats as stats_routes

        seen = {}
        real_to_json = stats_routes.to_json

        def get_kind(kind):
            seen["read"] = threading.get_ident()
            return [{"id": "t1"}]

        def to_json(value):
            seen["encode"] = threading.get_ident()
            return real_to_json(value)

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_kind",
            staticmethod(get_kind),
        )
        monkeypatch.setattr("api.routes.admin.stats.to_json", to_json)
        response = test_client(
            url="/admin/items/stats/templates", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert response.json() == [{"id": "t1"}]
        assert seen["encode"] == seen["read"]


class TestConnectedUsers:
    URL = "/admin/item/stats/connected-users"

    def test_admin_gets_users_and_sockets(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_connected_users",
            staticmethod(lambda: {"users": 2, "sockets": 5}),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"users": 2, "sockets": 5}

    def test_reads_the_socketio_redis(self, monkeypatch, test_client):
        import api.services.admin.stats as service

        class Redis:
            def scan_iter(self, match, count=None):
                assert match == "socketio:connected:*"
                return ["socketio:connected:a", "socketio:connected:b"]

            def hvals(self, key):
                return {
                    "socketio:connected:a": [b"u1", b"u1"],
                    "socketio:connected:b": [b"u1", b"u2", b""],
                }[key]

        urls = []

        def shared_client(url):
            urls.append(url)
            return Redis()

        monkeypatch.setattr(service, "shared_client", shared_client)
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        assert response.json() == {"users": 2, "sockets": 5}
        assert urls and urls[0].endswith("/3")

    def test_redis_failure_is_500(self, monkeypatch, test_client):
        def boom():
            raise ConnectionError("redis down")

        monkeypatch.setattr(
            "api.routes.admin.stats.AdminStatsService.get_connected_users",
            staticmethod(boom),
        )
        response = test_client(url=self.URL, jwt=MockJWT(role_id="admin"))
        assert response.status_code == 500

    def test_is_admin_only(self, test_client):
        for role in ("manager", "user"):
            response = test_client(url=self.URL, jwt=MockJWT(role_id=role))
            assert response.status_code == 403
