# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_usage.py``.

Covers consumption requests, parameter CRUD, limits (with nested
UsageLimitsValues), groupings, credit CRUD, and reset-dates request.
"""

import pytest
from api.schemas.admin_usage import (
    UsageConsumptionRequest,
    UsageCreditCreateRequest,
    UsageCreditUpdateRequest,
    UsageGroupingCreateRequest,
    UsageGroupingUpdateRequest,
    UsageLimitCreateRequest,
    UsageLimitsValues,
    UsageLimitUpdateRequest,
    UsageParameterCreateRequest,
    UsageParameterIdsRequest,
    UsageParameterUpdateRequest,
    UsageResetDatesRequest,
    UsageStartEndRequest,
)
from pydantic import ValidationError

# ══════════════════════════════════════════════════════════════════════════
#  Consumption requests
# ══════════════════════════════════════════════════════════════════════════


class TestUsageConsumptionRequest:
    """All fields optional — the route does its own ownership check
    via service.check_item_ownership. Pin the optional shape so the
    PUT /admin/usage handler's exclude_none dump stays predictable."""

    def test_accepts_empty(self):
        r = UsageConsumptionRequest()
        assert r.start_date is None
        assert r.items_ids is None

    def test_accepts_partial(self):
        r = UsageConsumptionRequest(start_date="2026-01-01")
        dump = r.model_dump(exclude_none=True)
        assert dump == {"start_date": "2026-01-01"}

    def test_both_items_ids_and_item_ids_supported(self):
        """Note the schema declares BOTH `items_ids` AND `item_ids` —
        a v3 compatibility quirk. The service uses items_ids; item_ids
        is for ownership checks. Pin both so a future de-dup is intentional."""
        r = UsageConsumptionRequest(items_ids=["a"], item_ids=["b"])
        assert r.items_ids == ["a"]
        assert r.item_ids == ["b"]


class TestUsageStartEndRequest:
    def test_accepts_empty(self):
        r = UsageStartEndRequest()
        assert r.item_consumer is None

    def test_item_consumer_field(self):
        """item_consumer is the field the route inspects for the
        manager-hypervisor 403 guard. Pin so a future rename breaks
        loud at this schema test (and the route test)."""
        r = UsageStartEndRequest(item_consumer="hypervisor")
        assert r.item_consumer == "hypervisor"


# ══════════════════════════════════════════════════════════════════════════
#  Parameters
# ══════════════════════════════════════════════════════════════════════════


class TestUsageParameterIdsRequest:
    def test_accepts_empty(self):
        """ids defaults to None — and the route handler short-circuits
        to {} when ids is falsy. The schema tolerance is intentional."""
        r = UsageParameterIdsRequest()
        assert r.ids is None

    def test_accepts_list(self):
        r = UsageParameterIdsRequest(ids=["p-1", "p-2"])
        assert r.ids == ["p-1", "p-2"]

    def test_accepts_empty_list(self):
        """Empty list ≠ None — both make the handler return {}."""
        r = UsageParameterIdsRequest(ids=[])
        assert r.ids == []


class TestUsageParameterCreateRequest:
    _required = {
        "id": "p-new",
        "name": "p",
        "desc": "desc",
        "custom": True,
        "formula": "x*2",
        "item_type": "desktop",
        "units": "h",
    }

    def test_accepts_required(self):
        r = UsageParameterCreateRequest(**self._required)
        assert r.id == "p-new"
        assert r.custom is True

    @pytest.mark.parametrize(
        "missing",
        ["id", "name", "desc", "custom", "formula", "item_type", "units"],
    )
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UsageParameterCreateRequest(**payload)


class TestUsageParameterUpdateRequest:
    """id + custom required, everything else Optional."""

    def test_id_and_custom_required(self):
        with pytest.raises(ValidationError):
            UsageParameterUpdateRequest()
        with pytest.raises(ValidationError):
            UsageParameterUpdateRequest(id="p-1")

    def test_minimal_update(self):
        r = UsageParameterUpdateRequest(id="p-1", custom=False)
        assert r.id == "p-1"
        assert r.custom is False
        assert r.name is None


# ══════════════════════════════════════════════════════════════════════════
#  Limits (nested model)
# ══════════════════════════════════════════════════════════════════════════


class TestUsageLimitsValues:
    _required = {"hard": 100.0, "soft": 80.0, "exp_min": 0.0, "exp_max": 95.0}

    def test_accepts_required(self):
        v = UsageLimitsValues(**self._required)
        assert v.hard == 100.0

    @pytest.mark.parametrize("missing", ["hard", "soft", "exp_min", "exp_max"])
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UsageLimitsValues(**payload)

    def test_int_coerced_to_float(self):
        """Integer inputs coerce to float — the form UI sends ints
        for whole-number limits."""
        v = UsageLimitsValues(hard=100, soft=80, exp_min=0, exp_max=95)
        assert isinstance(v.hard, float)
        assert v.hard == 100.0


class TestUsageLimitCreateRequest:
    def _payload(self):
        return {
            "name": "Standard",
            "desc": "default",
            "limits": {"hard": 100, "soft": 80, "exp_min": 0, "exp_max": 95},
        }

    def test_accepts_required(self):
        r = UsageLimitCreateRequest(**self._payload())
        assert r.limits.hard == 100.0

    def test_missing_limits_rejected(self):
        with pytest.raises(ValidationError):
            UsageLimitCreateRequest(name="x", desc="y")

    def test_partial_limits_rejected(self):
        """The nested UsageLimitsValues requires all four — pin so a
        partial limits dict fails validation, not silently writes None."""
        payload = {
            "name": "x",
            "desc": "y",
            "limits": {"hard": 100, "soft": 80},  # exp_min/exp_max missing
        }
        with pytest.raises(ValidationError):
            UsageLimitCreateRequest(**payload)


class TestUsageLimitUpdateRequest:
    """Same required surface as Create."""

    def test_required_match_create(self):
        with pytest.raises(ValidationError):
            UsageLimitUpdateRequest()
        r = UsageLimitUpdateRequest(
            name="x",
            desc="y",
            limits={"hard": 1, "soft": 1, "exp_min": 0, "exp_max": 1},
        )
        assert r.name == "x"


# ══════════════════════════════════════════════════════════════════════════
#  Groupings
# ══════════════════════════════════════════════════════════════════════════


class TestUsageGroupingCreateRequest:
    _required = {
        "name": "g",
        "item_type": "desktop",
        "parameters": ["p-1"],
    }

    def test_accepts_required(self):
        r = UsageGroupingCreateRequest(**self._required)
        assert r.parameters == ["p-1"]
        assert r.desc is None

    @pytest.mark.parametrize("missing", ["name", "item_type", "parameters"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UsageGroupingCreateRequest(**payload)

    def test_empty_parameters_accepted(self):
        """Empty list valid (a grouping that doesn't include any
        parameters is unusual but not invalid at the schema level)."""
        r = UsageGroupingCreateRequest(name="g", item_type="desktop", parameters=[])
        assert r.parameters == []


class TestUsageGroupingUpdateRequest:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            UsageGroupingUpdateRequest()

    def test_id_only(self):
        r = UsageGroupingUpdateRequest(id="g-1")
        assert r.id == "g-1"
        assert r.name is None


# ══════════════════════════════════════════════════════════════════════════
#  Credits
# ══════════════════════════════════════════════════════════════════════════


class TestUsageCreditCreateRequest:
    _required = {
        "item_ids": ["i-1"],
        "item_consumer": "category",
        "item_type": "desktop",
        "grouping_id": "g-1",
        "limit_id": "l-1",
        "start_date": "2026-01-01",
    }

    def test_accepts_required(self):
        r = UsageCreditCreateRequest(**self._required)
        assert r.item_ids == ["i-1"]
        assert r.end_date is None

    @pytest.mark.parametrize(
        "missing",
        [
            "item_ids",
            "item_consumer",
            "item_type",
            "grouping_id",
            "limit_id",
            "start_date",
        ],
    )
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UsageCreditCreateRequest(**payload)

    def test_end_date_optional(self):
        """end_date is Optional — None means "no end" (open-ended credit)."""
        r = UsageCreditCreateRequest(**{**self._required, "end_date": None})
        assert r.end_date is None


class TestUsageCreditUpdateRequest:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            UsageCreditUpdateRequest()

    def test_partial_update(self):
        r = UsageCreditUpdateRequest(id="c-1", end_date="2026-12-31")
        dump = r.model_dump(exclude_none=True)
        assert dump == {"id": "c-1", "end_date": "2026-12-31"}


# ══════════════════════════════════════════════════════════════════════════
#  Reset dates
# ══════════════════════════════════════════════════════════════════════════


class TestUsageResetDatesRequest:
    def test_date_list_required(self):
        with pytest.raises(ValidationError):
            UsageResetDatesRequest()

    def test_accepts_empty_list(self):
        """Empty list = "no reset dates" — the handler clears the table.
        Pin so a future schema change that requires non-empty doesn't
        accidentally make "no reset dates" un-settable."""
        r = UsageResetDatesRequest(date_list=[])
        assert r.date_list == []

    def test_string_dates(self):
        r = UsageResetDatesRequest(date_list=["01/01/2026", "02/01/2026"])
        assert r.date_list == ["01/01/2026", "02/01/2026"]
