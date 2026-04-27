# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/planning.py``."""

from datetime import datetime, timezone

import pytest
from api.schemas.planning import (
    CreatePlanningRequest,
    PlanningDeleteResponse,
    PlanningItem,
    PlanningListResponse,
    ReservablePlans,
)
from pydantic import ValidationError


class TestCreatePlanningRequest:
    _required = {
        "item_type": "gpus",
        "item_id": "gpu-1",
        "subitem_id": "profile-1",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-02T00:00:00Z",
    }

    def test_accepts_required(self):
        r = CreatePlanningRequest(**self._required)
        assert r.item_type == "gpus"
        assert isinstance(r.start, datetime)

    @pytest.mark.parametrize(
        "missing", ["item_type", "item_id", "subitem_id", "start", "end"]
    )
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            CreatePlanningRequest(**payload)

    def test_datetime_string_coerced(self):
        """ISO 8601 strings coerce to datetime — pin the wire shape
        clients send."""
        r = CreatePlanningRequest(**self._required)
        assert r.start == datetime(2026, 1, 1, tzinfo=timezone.utc)


class TestPlanningItem:
    _required = {
        "id": "p-1",
        "item_id": "gpu-1",
        "subitem_id": "prof-1",
        "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-02T00:00:00Z",
    }

    def test_accepts_required(self):
        p = PlanningItem(**self._required)
        assert p.id == "p-1"
        assert p.item_type is None
        assert p.units is None
        assert p.priority is None

    @pytest.mark.parametrize("missing", ["id", "item_id", "subitem_id", "start", "end"])
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            PlanningItem(**payload)


class TestPlanningListResponse:
    def test_plannings_required(self):
        with pytest.raises(ValidationError):
            PlanningListResponse()

    def test_accepts_empty(self):
        assert PlanningListResponse(plannings=[]).plannings == []


class TestPlanningDeleteResponse:
    @pytest.mark.parametrize("missing", ["deleted", "plan_id"])
    def test_required(self, missing):
        payload = {"deleted": True, "plan_id": "p-1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            PlanningDeleteResponse(**payload)


class TestReservablePlans:
    @pytest.mark.parametrize("missing", ["current", "active"])
    def test_required(self, missing):
        payload = {"current": 5, "active": True}
        del payload[missing]
        with pytest.raises(ValidationError):
            ReservablePlans(**payload)

    def test_profile_optional(self):
        r = ReservablePlans(current=5, active=True)
        assert r.profile is None
