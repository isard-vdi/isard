# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/reservables.py``."""

import pytest
from api.schemas.reservables import (
    AddReservableItemRequest,
    AvailableReservable,
    AvailableReservablesResponse,
    BookingProvisioningRequest,
    CheckLastResponse,
    CreatePlanRequest,
    EnableReservableRequest,
    PlannerPlanResponse,
    ReservableDetailResponse,
    ReservableItemResponse,
    ReservablePlans,
    ReservableProfileResponse,
    ReservablesListResponse,
    UpdatePlanRequest,
)
from pydantic import ValidationError


class TestReservablesListResponse:
    def test_required(self):
        with pytest.raises(ValidationError):
            ReservablesListResponse()

    def test_accepts_empty(self):
        assert ReservablesListResponse(reservables=[]).reservables == []


class TestReservablePlans:
    @pytest.mark.parametrize("missing", ["current", "active"])
    def test_required(self, missing):
        payload = {"current": 5, "active": True}
        del payload[missing]
        with pytest.raises(ValidationError):
            ReservablePlans(**payload)


class TestReservableItemResponse:
    _required = {
        "id": "r-1",
        "name": "GPU",
        "description": "x",
        "brand": "NVIDIA",
        "model": "A100",
        "memory": "40GB",
        "architecture": "Ampere",
        "profiles_enabled": [],
        "plans": {"current": 0, "active": False},
    }

    def test_accepts_required(self):
        r = ReservableItemResponse(**self._required)
        assert r.brand == "NVIDIA"
        assert r.active_profile is None

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            ReservableItemResponse(**payload)


class TestReservableDetailResponse:
    def test_items_required(self):
        with pytest.raises(ValidationError):
            ReservableDetailResponse()


class TestAvailableReservable:
    @pytest.mark.parametrize(
        "missing", ["id", "name", "description", "max_booking_date"]
    )
    def test_required(self, missing):
        payload = {
            "id": "r-1",
            "name": "R",
            "description": "x",
            "max_booking_date": "2026-12-31",
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            AvailableReservable(**payload)


class TestAvailableReservablesResponse:
    def test_accepts_none(self):
        """reservables_available is Optional — None means "no available
        reservables for this user". Distinct from [] which means "list
        is empty after filtering"."""
        r = AvailableReservablesResponse(reservables_available=None)
        assert r.reservables_available is None

    def test_accepts_list(self):
        r = AvailableReservablesResponse(reservables_available=[])
        assert r.reservables_available == []


class TestReservableProfileResponse:
    _required = {
        "id": "r-1",
        "brand": "NVIDIA",
        "model": "A100",
        "description": "x",
        "memory": "40GB",
        "architecture": "Ampere",
        "profiles": [],
    }

    @pytest.mark.parametrize("missing", list(_required))
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            ReservableProfileResponse(**payload)


class TestAddReservableItemRequest:
    @pytest.mark.parametrize("missing", ["name", "bookable"])
    def test_required(self, missing):
        payload = {"name": "GPU", "bookable": "yes"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AddReservableItemRequest(**payload)

    def test_description_default_empty(self):
        r = AddReservableItemRequest(name="GPU", bookable="yes")
        assert r.description == ""


class TestEnableReservableRequest:
    def test_enabled_required(self):
        with pytest.raises(ValidationError):
            EnableReservableRequest()


class TestCheckLastResponse:
    _required = {
        "last": [True, False],
        "desktops": [],
        "plans": [],
        "bookings": [],
        "deployments": [],
    }

    @pytest.mark.parametrize("missing", list(_required))
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            CheckLastResponse(**payload)


class TestPlannerPlanResponse:
    _required = {
        "id": "p-1",
        "item_type": "gpus",
        "item_id": "gpu-1",
        "subitem_id": "prof-1",
        "units": 1,
        "start": "2026-01-01",
        "end": "2026-01-02",
        "user_id": "u-1",
        "event_type": "booking",
    }

    def test_accepts_required(self):
        p = PlannerPlanResponse(**self._required)
        assert p.units == 1
        assert p.item is None
        assert p.bookings is None


class TestCreatePlanRequest:
    @pytest.mark.parametrize(
        "missing", ["item_type", "item_id", "subitem_id", "start", "end"]
    )
    def test_required(self, missing):
        payload = {
            "item_type": "gpus",
            "item_id": "gpu-1",
            "subitem_id": "prof-1",
            "start": "2026-01-01",
            "end": "2026-01-02",
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            CreatePlanRequest(**payload)


class TestUpdatePlanRequest:
    @pytest.mark.parametrize("missing", ["start", "end"])
    def test_required(self, missing):
        payload = {"start": "2026-01-01", "end": "2026-01-02"}
        del payload[missing]
        with pytest.raises(ValidationError):
            UpdatePlanRequest(**payload)


class TestBookingProvisioningRequest:
    @pytest.mark.parametrize(
        "missing", ["subitems", "units", "priority", "block_interval"]
    )
    def test_required(self, missing):
        payload = {
            "subitems": {},
            "units": 1,
            "priority": {},
            "block_interval": 60,
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            BookingProvisioningRequest(**payload)
