# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/analytics.py — storage/resource analytics, suggested
removals, graph configurations, desktop analytics, and echart-data
dispatcher.

Notable security boundary: the analytics POST endpoints accept a
`categories` filter, but the route MUST overwrite that filter to the
manager's own category when role_id == "manager". Otherwise a manager
could query analytics for any category by sending an arbitrary list.
TestCategoriesScoping pins this for every relevant endpoint.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  POST /analytics/storage, /analytics/resources/count
#  Both share the manager-category-override pattern.
# ══════════════════════════════════════════════════════════════════════════


class TestCategoriesScoping:
    """Critical fail-safe: regardless of what the body says, a manager
    MUST be scoped to their own category.
    """

    def _stub(self, monkeypatch, captured):
        def fake(categories):
            captured["categories"] = categories
            return {}

        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.storage_usage",
            staticmethod(fake),
        )
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.resource_count",
            staticmethod(fake),
        )

    def test_admin_passes_categories_through(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/analytics/storage",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": ["cat-a", "cat-b"]},
        )
        assert response.status_code == 200
        assert captured["categories"] == ["cat-a", "cat-b"]

    def test_admin_with_no_categories_passes_none(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/analytics/storage",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": None},
        )
        assert response.status_code == 200
        assert captured["categories"] is None

    def test_manager_categories_overridden_to_own_category(
        self, monkeypatch, test_client
    ):
        """A manager passing categories=['cat-other'] must be SILENTLY
        overridden to ['<their own category>']. Otherwise managers can
        enumerate analytics across any category."""
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/analytics/storage",
            method="POST",
            jwt=MockJWT(role_id="manager", category_id="default"),
            body={"categories": ["cat-other"]},
        )
        assert response.status_code == 200
        assert captured["categories"] == ["default"]

    def test_manager_with_no_categories_still_scoped(self, monkeypatch, test_client):
        captured = {}
        self._stub(monkeypatch, captured)
        response = test_client(
            url="/analytics/resources/count",
            method="POST",
            jwt=MockJWT(role_id="manager", category_id="default"),
            body={"categories": None},
        )
        assert response.status_code == 200
        assert captured["categories"] == ["default"]

    def test_user_forbidden(self, monkeypatch, test_client):
        self._stub(monkeypatch, {})
        response = test_client(
            url="/analytics/storage",
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"categories": None},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /analytics/suggested_removals
# ══════════════════════════════════════════════════════════════════════════


class TestSuggestedRemovals:
    URL = "/analytics/suggested_removals"

    def test_admin_with_required_months(self, monkeypatch, test_client):
        captured = {}

        def fake(categories, months_without_use=None):
            captured["categories"] = categories
            captured["months_without_use"] = months_without_use
            return []

        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.suggested_removals",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": None, "months_without_use": 6},
        )
        assert response.status_code == 200
        assert captured["months_without_use"] == 6

    def test_missing_months_rejected(self, test_client):
        """months_without_use is required — pin it so a future schema
        change that adds a default doesn't silently accept zero."""
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"categories": None},
        )
        assert response.status_code in (400, 422)

    def test_manager_categories_overridden(self, monkeypatch, test_client):
        captured = {}

        def fake(categories, months_without_use=None):
            captured["categories"] = categories
            return []

        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.suggested_removals",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="POST",
            jwt=MockJWT(role_id="manager", category_id="default"),
            body={"categories": ["cat-other"], "months_without_use": 6},
        )
        assert response.status_code == 200
        assert captured["categories"] == ["default"]


# ══════════════════════════════════════════════════════════════════════════
#  Graph configuration: list (manager), get/add/update/delete (admin)
# ══════════════════════════════════════════════════════════════════════════


class TestGraphConfig:
    def test_list_on_manager_router(self, monkeypatch, test_client):
        """List endpoint is on manager_router so the manager-side
        dashboard can render saved graphs. Admins should also work."""
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_usage_graphs_conf",
            staticmethod(lambda: [{"id": "g-1"}]),
        )
        response = test_client(url="/analytics/graph", jwt=MockJWT(role_id="manager"))
        assert response.status_code == 200
        assert response.json()[0]["id"] == "g-1"

    def test_list_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_usage_graphs_conf",
            staticmethod(lambda: []),
        )
        response = test_client(url="/analytics/graph", jwt=MockJWT(role_id="user"))
        assert response.status_code == 403

    def test_get_on_admin_router(self, monkeypatch, test_client):
        """Per-graph GET is admin-only. Pin so a future move to
        manager_router (which would let managers read each other's
        custom graphs) fails loud."""
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_usage_graph_conf",
            staticmethod(lambda cid: {"id": cid}),
        )
        # admin allowed
        response = test_client(url="/analytics/graph/g-1", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        # manager blocked
        response = test_client(
            url="/analytics/graph/g-1", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403

    def test_get_unknown_returns_404(self, monkeypatch, test_client):
        def fail(cid):
            raise Error("not_found", "Graph config not found")

        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_usage_graph_conf",
            staticmethod(fail),
        )
        response = test_client(
            url="/analytics/graph/ghost", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 404

    def test_add(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.add_usage_graph_conf",
            staticmethod(lambda data: captured.update(data=data)),
        )
        response = test_client(
            url="/analytics/graph",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"name": "Storage by month", "type": "line"},
        )
        assert response.status_code == 200
        assert captured["data"] == {"name": "Storage by month", "type": "line"}

    def test_update(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.update_usage_graph_conf",
            staticmethod(lambda cid, data: captured.update(cid=cid, data=data)),
        )
        response = test_client(
            url="/analytics/graph/g-1",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"name": "Renamed"},
        )
        assert response.status_code == 200
        assert captured == {"cid": "g-1", "data": {"name": "Renamed"}}

    def test_delete(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.delete_usage_graph_conf",
            staticmethod(lambda cid: captured.update(cid=cid)),
        )
        response = test_client(
            url="/analytics/graph/g-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["cid"] == "g-1"

    def test_manager_forbidden_on_mutation(self, monkeypatch, test_client):
        """Mutations are admin-only. Verify manager is blocked on each
        mutating verb."""
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.add_usage_graph_conf",
            staticmethod(lambda data: None),
        )
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.update_usage_graph_conf",
            staticmethod(lambda cid, data: None),
        )
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.delete_usage_graph_conf",
            staticmethod(lambda cid: None),
        )
        for method, url, body in [
            ("POST", "/analytics/graph", {"name": "x"}),
            ("PUT", "/analytics/graph/g-1", {"name": "y"}),
            ("DELETE", "/analytics/graph/g-1", None),
        ]:
            response = test_client(
                url=url,
                method=method,
                jwt=MockJWT(role_id="manager"),
                body=body or {},
            )
            assert response.status_code == 403, f"{method} {url} should be 403"


# ══════════════════════════════════════════════════════════════════════════
#  POST /analytics/desktops/{less_used,recently_used,most_used}
# ══════════════════════════════════════════════════════════════════════════


class TestDesktopAnalytics:
    """Three near-identical handlers — pin the service method name
    each one calls (typos in the dispatch are an easy regression).
    """

    def _payload(self, **overrides):
        body = {"days_before": 30, "limit": 10}
        body.update(overrides)
        return body

    def test_less_used_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_desktops_less_used",
            staticmethod(lambda *a, **k: called.update(yes="less") or []),
        )
        response = test_client(
            url="/analytics/desktops/less_used",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert called["yes"] == "less"

    def test_recently_used_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_desktops_recently_used",
            staticmethod(lambda *a, **k: called.update(yes="recent") or []),
        )
        response = test_client(
            url="/analytics/desktops/recently_used",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert called["yes"] == "recent"

    def test_most_used_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_desktops_most_used",
            staticmethod(lambda *a, **k: called.update(yes="most") or []),
        )
        response = test_client(
            url="/analytics/desktops/most_used",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert called["yes"] == "most"

    def test_status_falsy_coerces_to_false(self, monkeypatch, test_client):
        """The handler does `data.status or False` — None becomes False
        before the service call. Pin so the service isn't accidentally
        passed None and tries to filter on it."""
        captured = {}

        def fake(days_before, limit, not_in_directory_path, status):
            captured["status"] = status
            return []

        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_desktops_less_used",
            staticmethod(fake),
        )
        response = test_client(
            url="/analytics/desktops/less_used",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),  # status defaults to None
        )
        assert response.status_code == 200
        assert captured["status"] is False

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_desktops_less_used",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url="/analytics/desktops/less_used",
            method="POST",
            jwt=MockJWT(role_id="manager"),
            body=self._payload(),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  POST /admin/echart/{view}  — view dispatcher
# ══════════════════════════════════════════════════════════════════════════


class TestEchart:
    """Each view name routes to a different service method. A typo in
    the if/elif chain is an easy regression. Pin every branch.
    """

    def test_daily_items_dispatch(self, monkeypatch, test_client):
        called = {}
        # ``get_daily_items`` returns the eChart contract — a dict
        # ``{x, series}`` — distinct from the other views which return
        # ``list[{value, name}]``. The dedicated route preserves it.
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_daily_items",
            staticmethod(
                lambda table, date_field: (
                    called.update(table=table, df=date_field)
                    or {"x": ["2026-05-01T00:00:00"], "series": {date_field: [3]}}
                )
            ),
        )
        response = test_client(
            url="/admin/echart/daily_items",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"table": "users", "date_field": "created"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["x"] == ["2026-05-01T00:00:00"]
        assert body["series"] == {"created": [3]}
        assert called == {"table": "users", "df": "created"}

    def test_grouped_items_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_grouped_data",
            staticmethod(
                lambda table, group_field: called.update(t=table, g=group_field) or []
            ),
        )
        response = test_client(
            url="/admin/echart/grouped_items",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"table": "domains", "group_field": "kind"},
        )
        assert response.status_code == 200
        assert called == {"t": "domains", "g": "kind"}

    def test_grouped_unique_items_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_grouped_unique_data",
            staticmethod(
                lambda table, group_field, unique_field: called.update(
                    g=group_field, u=unique_field
                )
                or []
            ),
        )
        response = test_client(
            url="/admin/echart/grouped_unique_items",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "table": "domains",
                "group_field": "kind",
                "unique_field": "user",
            },
        )
        assert response.status_code == 200
        assert called == {"g": "kind", "u": "user"}

    def test_nested_array_dispatch(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_nested_array_grouped_data",
            staticmethod(
                lambda table, nested, group_field: called.update(
                    n=nested, g=group_field
                )
                or []
            ),
        )
        response = test_client(
            url="/admin/echart/nested_array_grouped_items",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "table": "users",
                "nested_array_field": "groups",
                "group_field": "role",
            },
        )
        assert response.status_code == 200
        assert called == {"n": "groups", "g": "role"}

    def test_unknown_view_returns_400(self, test_client):
        """The route raises Error("bad_request") for unknown views —
        not 500. Pin the typed status."""
        response = test_client(
            url="/admin/echart/no_such_view",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"table": "users"},
        )
        assert response.status_code == 400

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.analytics.AdminAnalyticsService.get_daily_items",
            staticmethod(lambda *a, **k: []),
        )
        response = test_client(
            url="/admin/echart/daily_items",
            method="POST",
            jwt=MockJWT(role_id="user"),
            body={"table": "users"},
        )
        assert response.status_code == 403
