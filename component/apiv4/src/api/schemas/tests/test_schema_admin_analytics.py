# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_analytics.py``."""

import pytest
from api.schemas.admin_analytics import (
    AnalyticsCategoriesRequest,
    AnalyticsGraphCreateRequest,
    AnalyticsGraphUpdateRequest,
    AnalyticsSuggestedRemovalsRequest,
    DesktopAnalyticsRequest,
    EchartRequest,
)
from pydantic import ValidationError


class TestAnalyticsCategoriesRequest:
    def test_accepts_empty(self):
        r = AnalyticsCategoriesRequest()
        assert r.categories is None

    def test_accepts_categories_list(self):
        r = AnalyticsCategoriesRequest(categories=["cat-a", "cat-b"])
        assert r.categories == ["cat-a", "cat-b"]

    def test_accepts_empty_list(self):
        """Empty list ≠ None: the route's manager-override check is
        `if payload["role_id"] == "manager"` (always overrides). Pin
        both shapes so the wire contract is unambiguous."""
        assert AnalyticsCategoriesRequest(categories=[]).categories == []


class TestAnalyticsSuggestedRemovalsRequest:
    def test_months_required(self):
        """months_without_use is the only required field — it has no
        default, even though categories is optional."""
        with pytest.raises(ValidationError):
            AnalyticsSuggestedRemovalsRequest()

    def test_accepts_required(self):
        r = AnalyticsSuggestedRemovalsRequest(months_without_use=6)
        assert r.months_without_use == 6
        assert r.categories is None

    def test_zero_months_accepted(self):
        """Schema allows 0 — the meaning is "everything regardless of
        recency". Pin so a future min-bound flip is intentional."""
        r = AnalyticsSuggestedRemovalsRequest(months_without_use=0)
        assert r.months_without_use == 0


class TestAnalyticsGraphCreateRequest:
    """Every field optional — the admin UI uses partial drafts."""

    def test_accepts_empty(self):
        r = AnalyticsGraphCreateRequest()
        assert r.name is None
        assert r.type is None

    def test_accepts_full(self):
        r = AnalyticsGraphCreateRequest(
            name="Storage by month",
            grouping="g-1",
            type="line",
            consumer="category",
            item_type="desktop",
        )
        assert r.type == "line"


class TestAnalyticsGraphUpdateRequest:
    """Same shape as Create — pure passthrough partial-update."""

    def test_accepts_empty(self):
        r = AnalyticsGraphUpdateRequest()
        assert r.name is None

    def test_partial_update(self):
        r = AnalyticsGraphUpdateRequest(name="renamed")
        dump = r.model_dump(exclude_none=True)
        assert dump == {"name": "renamed"}


class TestDesktopAnalyticsRequest:
    def test_defaults(self):
        """Defaults: days_before=30, limit=10. Pin so a UI that doesn't
        send these still works."""
        r = DesktopAnalyticsRequest()
        assert r.days_before == 30
        assert r.limit == 10
        assert r.not_in_directory_path is None
        assert r.status is None

    def test_accepts_overrides(self):
        r = DesktopAnalyticsRequest(
            days_before=7,
            limit=5,
            not_in_directory_path="/tmp/",
            status="Stopped",
        )
        assert r.days_before == 7
        assert r.status == "Stopped"

    def test_string_int_coerced(self):
        """default=10 is int but Pydantic v2 coerces "5" → 5. Pin so
        the analytics dropdown that sends form-encoded values keeps
        working."""
        r = DesktopAnalyticsRequest(days_before="7", limit="5")
        assert r.days_before == 7
        assert r.limit == 5


class TestEchartRequest:
    def test_table_required(self):
        with pytest.raises(ValidationError):
            EchartRequest()

    def test_accepts_table_only(self):
        r = EchartRequest(table="users")
        assert r.table == "users"
        assert r.date_field is None
        assert r.group_field is None
        assert r.unique_field is None
        assert r.nested_array_field is None

    def test_accepts_full(self):
        r = EchartRequest(
            table="domains",
            date_field="created",
            group_field="kind",
            unique_field="user",
            nested_array_field="tags",
        )
        assert r.nested_array_field == "tags"
