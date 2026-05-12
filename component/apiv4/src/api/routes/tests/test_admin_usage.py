# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for admin/usage.py — usage consumption analytics, parameters,
limits, groupings, credits, reset dates, and consolidation.

Critical security boundaries:

1. The hypervisor consumer is admin-only data. Manager attempts to
   query item_consumer="hypervisor" via /admin/usage/start_end or
   /admin/usage/distinct_items must return 403 — pinned by
   TestStartEndConsumption + TestDistinctItems.

2. Manager queries via /admin/usage/start_end MUST be scoped to the
   manager's own category — pinned by TestStartEndConsumption.

3. /admin/usage/credits/{consumer}/.../{item_id}/... rejects manager
   access to other categories when consumer == "category" — pinned
   by TestUsageCredits.

4. /admin/usage/consumers/{item_type} hides "hypervisor" from
   non-admins — pinned by TestUsageConsumers.

5. Date parsing in /admin/usage/reset_date/{start}/{end} must return
   a typed 400 (NOT 500) on invalid format. Same for
   /admin/usage/check/overlapping — pinned.
"""

from api.routes.tests.helpers import MockJWT
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/usage  — get_usage_consumption_between_dates
# ══════════════════════════════════════════════════════════════════════════


class TestUsageConsumption:
    URL = "/admin/usage"

    def test_admin_queries(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.check_item_ownership",
            staticmethod(lambda payload, filters: None),
        )

        def fake(start, end, ids, item_type, grouping):
            captured["start"] = start
            captured["end"] = end
            return {}

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumption_between_dates",
            staticmethod(fake),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        assert response.status_code == 200
        assert captured["start"] == "2026-01-01"

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.check_item_ownership",
            staticmethod(lambda *a: None),
        )
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumption_between_dates",
            staticmethod(lambda *a, **k: {}),
        )
        response = test_client(
            url=self.URL, method="PUT", jwt=MockJWT(role_id="user"), body={}
        )
        assert response.status_code == 403

    def test_ownership_check_403_propagates(self, monkeypatch, test_client):
        def reject(payload, filters):
            raise Error("forbidden", "Item not owned by caller")

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.check_item_ownership",
            staticmethod(reject),
        )
        # If check_item_ownership raises, the service must NOT run.
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumption_between_dates",
            staticmethod(lambda *a, **k: pytest_fail("service called")),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"items_ids": ["m-x"]},
        )
        assert response.status_code == 403


def pytest_fail(msg):
    raise AssertionError(msg)


# ══════════════════════════════════════════════════════════════════════════
#  PUT /admin/usage/start_end  — hypervisor + manager-category guards
# ══════════════════════════════════════════════════════════════════════════


class TestStartEndConsumption:
    URL = "/admin/usage/start_end"

    def _stub_service(self, monkeypatch, captured):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.check_item_ownership",
            staticmethod(lambda *a: None),
        )

        def fake(start, end, ids, item_type, item_consumer, grouping, manager_cat):
            captured["item_consumer"] = item_consumer
            captured["manager_cat"] = manager_cat
            return {}

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_start_end_consumption",
            staticmethod(fake),
        )

    def test_manager_blocked_from_hypervisor_consumer(self, monkeypatch, test_client):
        """Critical: manager cannot query hypervisor-level usage even
        with a valid token. Without this gate, hypervisor consumption
        leaks across categories."""
        captured = {}
        self._stub_service(monkeypatch, captured)
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"item_consumer": "hypervisor"},
        )
        assert response.status_code == 403
        # Service must NOT have been called.
        assert captured == {}

    def test_admin_allowed_on_hypervisor(self, monkeypatch, test_client):
        captured = {}
        self._stub_service(monkeypatch, captured)
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"item_consumer": "hypervisor"},
        )
        assert response.status_code == 200
        assert captured["item_consumer"] == "hypervisor"
        # Admin: manager_cat arg is None (no scoping).
        assert captured["manager_cat"] is None

    def test_manager_scoped_to_own_category(self, monkeypatch, test_client):
        """Manager sees only their own category's usage — the route
        passes their category_id as the manager_cat scope arg."""
        captured = {}
        self._stub_service(monkeypatch, captured)
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="manager", category_id="default"),
            body={"item_consumer": "category"},
        )
        assert response.status_code == 200
        assert captured["manager_cat"] == "default"

    def test_admin_no_manager_cat_scope(self, monkeypatch, test_client):
        captured = {}
        self._stub_service(monkeypatch, captured)
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"item_consumer": "category"},
        )
        assert response.status_code == 200
        assert captured["manager_cat"] is None

    def test_no_consumer_no_items_returns_400_not_500(self, monkeypatch, test_client):
        """Pins Bug 31 — when neither ``item_consumer`` nor
        ``items_ids`` is supplied, the service used to forward
        ``None`` to ``r.table(...).get_all(None, index="item_consumer")``
        which raises ``ReqlNonExistenceError: Keys cannot be NULL``;
        the route's generic ``except Exception`` swallowed that into a
        500 "Failed to get start/end consumption". The fix raises an
        explicit ``Error("bad_request", ...)`` at the service boundary.
        """
        # Don't stub the service — exercise the real validation.
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.check_item_ownership",
            staticmethod(lambda *a: None),
        )

        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"start_date": "2025-01-01", "end_date": "2026-01-01"},
        )

        assert response.status_code == 400, response.text
        body = response.json()
        assert body["description_code"] == "usage_consumer_required"


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/usage/consumers/{item_type}
# ══════════════════════════════════════════════════════════════════════════


class TestUsageConsumers:
    def test_admin_sees_hypervisor(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumers",
            staticmethod(lambda it: ["category", "hypervisor"]),
        )
        response = test_client(
            url="/admin/usage/consumers/desktop", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        assert "hypervisor" in response.json()

    def test_manager_does_not_see_hypervisor(self, monkeypatch, test_client):
        """Manager's response must have hypervisor stripped from the
        consumers list. Without this filter the dropdown UI offers a
        consumer the manager will then 403 on."""
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumers",
            staticmethod(lambda it: ["category", "hypervisor"]),
        )
        response = test_client(
            url="/admin/usage/consumers/desktop", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 200
        body = response.json()
        assert "hypervisor" not in body
        assert "category" in body

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_consumers",
            staticmethod(lambda it: []),
        )
        response = test_client(
            url="/admin/usage/consumers/desktop", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  GET /admin/usage/distinct_items/{consumer}/{start}/{end}
# ══════════════════════════════════════════════════════════════════════════


class TestDistinctItems:
    def test_manager_blocked_from_hypervisor(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_distinct_items",
            staticmethod(lambda *a, **k: called.update(yes=True) or []),
        )
        response = test_client(
            url="/admin/usage/distinct_items/hypervisor/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="manager"),
        )
        assert response.status_code == 403
        assert called == {}, "service must not be called when manager hits hypervisor"

    def test_admin_passes_through(self, monkeypatch, test_client):
        captured = {}

        def fake(consumer, start, end, manager_cat):
            captured["consumer"] = consumer
            captured["manager_cat"] = manager_cat
            return []

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_distinct_items",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/usage/distinct_items/category/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["manager_cat"] is None

    def test_manager_category_scoped(self, monkeypatch, test_client):
        captured = {}

        def fake(consumer, start, end, manager_cat):
            captured["manager_cat"] = manager_cat
            return []

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_distinct_items",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/usage/distinct_items/category/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="manager", category_id="default"),
        )
        assert response.status_code == 200
        assert captured["manager_cat"] == "default"


# ══════════════════════════════════════════════════════════════════════════
#  Consolidation: /admin/usage/consolidate/{item_type}/{days?}
# ══════════════════════════════════════════════════════════════════════════


class TestConsolidate:
    def test_consolidate_all(self, monkeypatch, test_client):
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.consolidate_consumptions",
            staticmethod(lambda *a, **k: called.update(args=a) or None),
        )
        response = test_client(
            url="/admin/usage/consolidate",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert called["args"] == ()  # no args

    def test_consolidate_item_type(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.consolidate_consumptions",
            staticmethod(lambda item_type, days: captured.update(it=item_type, d=days)),
        )
        response = test_client(
            url="/admin/usage/consolidate/desktop",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        # Defaults to 29 days when only item_type is given.
        assert captured == {"it": "desktop", "d": 29}

    def test_consolidate_item_with_days(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.consolidate_consumptions",
            staticmethod(lambda item_type, days: captured.update(it=item_type, d=days)),
        )
        response = test_client(
            url="/admin/usage/consolidate/desktop/7",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 204
        assert captured == {"it": "desktop", "d": 7}

    def test_manager_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.consolidate_consumptions",
            staticmethod(lambda *a, **k: None),
        )
        response = test_client(
            url="/admin/usage/consolidate",
            method="PUT",
            jwt=MockJWT(role_id="manager"),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Parameters: list (admin), list-by-ids (manager), CRUD (admin)
# ══════════════════════════════════════════════════════════════════════════


class TestParameters:
    def test_list_admin(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_parameters",
            staticmethod(lambda *a: [{"id": "p1"}]),
        )
        response = test_client(
            url="/admin/usage/parameters", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200

    def test_list_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_parameters",
            staticmethod(lambda *a: []),
        )
        response = test_client(
            url="/admin/usage/parameters", jwt=MockJWT(role_id="user")
        )
        assert response.status_code == 403

    def test_list_by_ids_manager_allowed(self, monkeypatch, test_client):
        """Manager can fetch parameters by id (manager_router) for the
        analytics dropdown."""
        captured = {}

        def fake(ids):
            captured["ids"] = ids
            return {p: {} for p in ids}

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_parameters",
            staticmethod(fake),
        )
        response = test_client(
            url="/admin/usage/list_parameters",
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"ids": ["p1", "p2"]},
        )
        assert response.status_code == 200
        assert captured["ids"] == ["p1", "p2"]

    def test_list_by_ids_empty_returns_empty_dict(self, monkeypatch, test_client):
        """When ids is empty/None the handler short-circuits to {} —
        does NOT call the service. Pin so a future change that calls
        the service with an empty list (which means "all" in some
        implementations) doesn't accidentally leak the full set."""
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_parameters",
            staticmethod(lambda *a: called.update(yes=True) or {}),
        )
        response = test_client(
            url="/admin/usage/list_parameters",
            method="PUT",
            jwt=MockJWT(role_id="manager"),
            body={"ids": []},
        )
        assert response.status_code == 200
        assert response.json() == {}
        assert called == {}, "service must not be called for empty ids"

    def test_create_admin(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_usage_parameters",
            staticmethod(lambda data: captured.update(data=data) or {"id": "new"}),
        )
        response = test_client(
            url="/admin/usage/parameters",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "id": "p-new",
                "name": "p",
                "desc": "x",
                "custom": True,
                "formula": "x*2",
                "item_type": "desktop",
                "units": "h",
            },
        )
        assert response.status_code == 200
        assert captured["data"]["id"] == "p-new"

    def test_create_missing_required_rejected(self, test_client):
        response = test_client(
            url="/admin/usage/parameters",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"id": "p-new"},
        )
        assert response.status_code in (400, 422)

    def test_delete_admin(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.delete_usage_parameters",
            staticmethod(lambda pid: captured.update(pid=pid) or {}),
        )
        response = test_client(
            url="/admin/usage/parameters/p-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["pid"] == "p-1"


# ══════════════════════════════════════════════════════════════════════════
#  Limits CRUD
# ══════════════════════════════════════════════════════════════════════════


class TestLimits:
    def _payload(self):
        return {
            "name": "Standard",
            "desc": "Default limits",
            "limits": {"hard": 100, "soft": 80, "exp_min": 0, "exp_max": 95},
        }

    def test_create(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_usage_limits",
            staticmethod(
                lambda name, desc, limits: captured.update(
                    name=name, desc=desc, limits=limits
                )
                or {"id": "l-1"}
            ),
        )
        response = test_client(
            url="/admin/usage/limits",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body=self._payload(),
        )
        assert response.status_code == 200
        assert captured["limits"]["hard"] == 100

    def test_create_missing_limits_rejected(self, test_client):
        response = test_client(
            url="/admin/usage/limits",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={"name": "x", "desc": "y"},
        )
        assert response.status_code in (400, 422)

    def test_user_forbidden(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_usage_limits",
            staticmethod(lambda *a: {}),
        )
        response = test_client(
            url="/admin/usage/limits",
            method="POST",
            jwt=MockJWT(role_id="user"),
            body=self._payload(),
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Credits — manager category check
# ══════════════════════════════════════════════════════════════════════════


class TestUsageCredits:
    def test_manager_blocked_from_other_category(self, monkeypatch, test_client):
        """Critical fail-safe: when consumer="category", a manager
        whose category_id != path item_id MUST get 403. Without this
        check, a manager can read another category's credits via path.
        """
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_credits",
            staticmethod(lambda *a, **k: called.update(yes=True) or []),
        )
        response = test_client(
            url="/admin/usage/credits/category/desktop/cat-other/g-1/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="manager", category_id="default"),
        )
        assert response.status_code == 403
        assert called == {}

    def test_manager_allowed_on_own_category(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_credits",
            staticmethod(
                lambda item_id, *a, **k: captured.update(item_id=item_id) or []
            ),
        )
        response = test_client(
            url="/admin/usage/credits/category/desktop/default/g-1/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="manager", category_id="default"),
        )
        assert response.status_code == 200
        assert captured["item_id"] == "default"

    def test_admin_no_category_check(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_credits",
            staticmethod(
                lambda item_id, *a, **k: captured.update(item_id=item_id) or []
            ),
        )
        response = test_client(
            url="/admin/usage/credits/category/desktop/cat-other/g-1/2026-01-01/2026-01-31",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["item_id"] == "cat-other"

    def test_create_credit(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_usage_credit",
            staticmethod(lambda data: captured.update(data=data) or {"id": "c-1"}),
        )
        response = test_client(
            url="/admin/usage/credits",
            method="POST",
            jwt=MockJWT(role_id="admin"),
            body={
                "item_ids": ["i-1"],
                "item_consumer": "category",
                "item_type": "desktop",
                "grouping_id": "g-1",
                "limit_id": "l-1",
                "start_date": "2026-01-01",
            },
        )
        assert response.status_code == 200
        assert captured["data"]["item_ids"] == ["i-1"]

    def test_delete_credit(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.delete_usage_credit",
            staticmethod(lambda cid: captured.update(cid=cid) or {}),
        )
        response = test_client(
            url="/admin/usage/credits/c-1",
            method="DELETE",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert captured["cid"] == "c-1"


# ══════════════════════════════════════════════════════════════════════════
#  Reset dates — date parsing path
# ══════════════════════════════════════════════════════════════════════════


class TestResetDates:
    def test_get_all(self, monkeypatch, test_client):
        from datetime import datetime

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_reset_dates",
            staticmethod(lambda *a: [datetime(2026, 1, 1), datetime(2026, 2, 1)]),
        )
        response = test_client(
            url="/admin/usage/reset_date", jwt=MockJWT(role_id="admin")
        )
        assert response.status_code == 200
        # Dates are formatted as MM/DD/YYYY for the v3-compatible UI.
        assert response.json() == ["01/01/2026", "02/01/2026"]

    def test_invalid_date_returns_400(self, monkeypatch, test_client):
        """The handler explicitly catches ValueError from strptime
        and re-raises Error("bad_request"). Pin so a refactor doesn't
        accidentally swallow the typed error and return 500."""
        called = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_reset_dates",
            staticmethod(lambda *a: called.update(yes=True) or []),
        )
        response = test_client(
            url="/admin/usage/reset_date/not-a-date/2026-12-31",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 400
        assert called == {}

    def test_set_dates(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_reset_dates",
            staticmethod(lambda dates: captured.update(count=len(dates))),
        )
        response = test_client(
            url="/admin/usage/reset_dates",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"date_list": ["01/01/2026", "02/01/2026"]},
        )
        assert response.status_code == 200
        assert captured["count"] == 2

    def test_user_forbidden_on_set(self, monkeypatch, test_client):
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.add_reset_dates",
            staticmethod(lambda dates: None),
        )
        response = test_client(
            url="/admin/usage/reset_dates",
            method="PUT",
            jwt=MockJWT(role_id="user"),
            body={"date_list": []},
        )
        assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Misc: unify item name, delete consumption data, check overlapping
# ══════════════════════════════════════════════════════════════════════════


class TestMisc:
    def test_unify_item_name(self, monkeypatch, test_client):
        captured = {}
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.unify_item_name",
            staticmethod(lambda iid: captured.update(iid=iid) or "Unified Name"),
        )
        response = test_client(
            url="/admin/usage/unify/i-1/item_name",
            method="PUT",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 200
        assert response.json() == {"name": "Unified Name"}
        assert captured["iid"] == "i-1"

    def test_check_overlapping_invalid_date_returns_400(self, monkeypatch, test_client):
        """check/overlapping path-validates dates and re-raises the
        ValueError as Error("bad_request"). Pin so the typed status
        sticks."""
        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_usage_credits_by_id",
            staticmethod(
                lambda cid: {
                    "item_id": "i-1",
                    "item_type": "desktop",
                    "grouping_id": "g-1",
                }
            ),
        )
        response = test_client(
            url="/admin/usage/check/overlapping/c-1/not-a-date/2026-01-31",
            jwt=MockJWT(role_id="admin"),
        )
        assert response.status_code == 400


# ══════════════════════════════════════════════════════════════════════════
#  GET / PUT /admin/usage/retention — UsageRetentionConfig
# ══════════════════════════════════════════════════════════════════════════


class TestUsageRetention:
    URL = "/admin/usage/retention"

    def test_get_returns_current_policy(self, monkeypatch, test_client):
        from isardvdi_common.schemas.usage import UsageRetentionConfig

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_retention_config",
            staticmethod(
                lambda: UsageRetentionConfig(
                    daily_months=2, weekly_months=8, total_months=24
                )
            ),
        )
        response = test_client(url=self.URL, method="GET", jwt=MockJWT(role_id="admin"))
        assert response.status_code == 200
        body = response.json()
        assert body["daily_months"] == 2
        assert body["weekly_months"] == 8
        assert body["total_months"] == 24

    def test_get_admin_only(self, monkeypatch, test_client):
        from isardvdi_common.schemas.usage import UsageRetentionConfig

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.get_retention_config",
            staticmethod(lambda: UsageRetentionConfig()),
        )
        response = test_client(
            url=self.URL, method="GET", jwt=MockJWT(role_id="manager")
        )
        assert response.status_code == 403

    def test_put_persists_validated_payload(self, monkeypatch, test_client):
        from isardvdi_common.schemas.usage import UsageRetentionConfig

        captured = {}

        def fake_update(data: UsageRetentionConfig) -> UsageRetentionConfig:
            captured["data"] = data.model_dump()
            return data

        monkeypatch.setattr(
            "api.routes.admin.usage.AdminUsageService.update_retention_config",
            staticmethod(fake_update),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"daily_months": 1, "weekly_months": 4, "total_months": 18},
        )
        assert response.status_code == 200
        assert captured["data"] == {
            "daily_months": 1,
            "weekly_months": 4,
            "total_months": 18,
        }

    def test_put_rejects_inverted_tier_ordering(self, monkeypatch, test_client):
        # Cross-field validation (weekly_months > daily_months) is
        # enforced at the service via ``assert_tier_ordering`` so the
        # response_model validator's body parse stays inside Pydantic's
        # JSON-serialisable error universe. The service raises
        # ``Error("bad_request")`` which the route re-raises and the
        # global handler renders as 400.
        from isardvdi_common.schemas.usage import UsageRetentionConfig

        # Use the real service so its Error-raising path is exercised;
        # only stub away the rdb-write helper so the test stays unit-
        # level. ``save_retention_config`` is the chokepoint for the
        # rdb update — if validation succeeded incorrectly, this stub
        # would be reached.
        monkeypatch.setattr(
            "api.services.admin.usage.save_retention_config",
            lambda conn, cfg: pytest_fail("db write attempted on invalid policy"),
        )
        response = test_client(
            url=self.URL,
            method="PUT",
            jwt=MockJWT(role_id="admin"),
            body={"daily_months": 6, "weekly_months": 3},
        )
        assert response.status_code == 400
        body = response.json()
        # Project's typed-error handler emits a JSON object describing
        # the failure. Pin the typed error name so future renames break
        # this test instead of silently shipping the wrong status code.
        assert "weekly_months" in (body.get("description") or body.get("error", ""))


# ─── Apiv3 TTLCache parity (US1 fix) ────────────────────────────────────


class TestUsageTTLCacheParity:
    """Apiv3 wrapped ``get_start_end_consumption``,
    ``get_usage_distinct_items``, and ``get_usage_consumers`` in 60s
    TTLCaches (``main:api/src/api/libv2/api_usage.py:185, 369, 414``).
    The apiv4 port silently dropped the decorators so every poll the
    admin usage page paid full cost — start_end took 30s+ on
    multi-tenant installs and the route timed out as 500.

    Pin that the second call within the cache window does NOT re-enter
    the underlying ``ConsumptionUsageProcessed`` query path."""

    def test_get_start_end_consumption_caches_within_ttl(self, monkeypatch):
        from api.services.admin import usage as svc

        # Reset the cache so this test runs deterministically regardless
        # of test ordering.
        svc._get_start_end_consumption_cache.clear()

        calls = {"list_distinct_items": 0}

        def fake_list(items_ids):
            calls["list_distinct_items"] += 1
            return []

        monkeypatch.setattr(
            svc.ConsumptionUsageProcessed,
            "list_distinct_items",
            staticmethod(fake_list),
        )
        monkeypatch.setattr(
            svc.AdminUsageService,
            "get_reset_dates",
            staticmethod(lambda s, e: []),
        )

        for _ in range(2):
            svc.AdminUsageService.get_start_end_consumption(
                start_date="2026-01-01",
                end_date="2026-01-31",
                items_ids=["item-1"],
                item_type="desktop",
                grouping_params=[],
            )
        assert calls["list_distinct_items"] == 1

    def test_get_usage_consumers_caches_within_ttl(self, monkeypatch):
        from api.services.admin import usage as svc

        svc._get_usage_consumers_cache.clear()

        calls = {"list_consumers": 0}

        def fake_list(item_type):
            calls["list_consumers"] += 1
            return [{"id": "c-1"}]

        monkeypatch.setattr(
            svc.UsageProcessed, "list_consumers", staticmethod(fake_list)
        )

        for _ in range(3):
            svc.AdminUsageService.get_usage_consumers("desktop")
        assert calls["list_consumers"] == 1

    def test_get_usage_distinct_items_caches_within_ttl(self, monkeypatch):
        from api.services.admin import usage as svc

        svc._get_usage_distinct_items_cache.clear()

        calls = {"list_distinct_consumer_items": 0}

        def fake_list(item_consumer, item_category=None):
            calls["list_distinct_consumer_items"] += 1
            return [{"item_id": "i-1", "item_name": "n-1"}]

        monkeypatch.setattr(
            svc.ConsumptionUsageProcessed,
            "list_distinct_consumer_items",
            staticmethod(fake_list),
        )

        for _ in range(3):
            svc.AdminUsageService.get_usage_distinct_items(
                "category", "2026-01-01", "2026-01-31", item_category="cat-1"
            )
        assert calls["list_distinct_consumer_items"] == 1

    def test_get_start_end_cache_keys_on_args(self, monkeypatch):
        """Different argument tuples must miss the cache and trigger a
        fresh underlying call. Pin so a refactor that ignores some args
        in the cache key (e.g. drops ``items_ids``) doesn't silently
        return stale data for a different filter."""
        from api.services.admin import usage as svc

        svc._get_start_end_consumption_cache.clear()

        calls = {"list_distinct_items": 0}

        def fake_list(items_ids):
            calls["list_distinct_items"] += 1
            return []

        monkeypatch.setattr(
            svc.ConsumptionUsageProcessed,
            "list_distinct_items",
            staticmethod(fake_list),
        )
        monkeypatch.setattr(
            svc.AdminUsageService,
            "get_reset_dates",
            staticmethod(lambda s, e: []),
        )

        svc.AdminUsageService.get_start_end_consumption(
            start_date="2026-01-01",
            end_date="2026-01-31",
            items_ids=["item-1"],
            item_type="desktop",
            grouping_params=[],
        )
        svc.AdminUsageService.get_start_end_consumption(
            start_date="2026-01-01",
            end_date="2026-01-31",
            items_ids=["item-2"],
            item_type="desktop",
            grouping_params=[],
        )
        assert calls["list_distinct_items"] == 2
