#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.bookings.bookings`.

Covers the user-facing booking handlers that replace the v3 shims
``/booking/event``, ``/booking/event/{id}``,
``/booking/max_booking_date/{desktop_id}``,
``/booking/reservables_available``, ``/bookings/user``. Every test
monkeypatches the corresponding ``BookingsService`` method and relies
on the default ``MockJWT()`` for ``has_token`` so no DB fixtures are
required.
"""

from api.routes.tests.helpers import MockJWT


def test_get_user_bookings_empty(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_get_user_bookings(start_date, end_date, payload):
        captured["user_id"] = payload["user_id"]
        captured["has_start"] = start_date is not None
        captured["has_end"] = end_date is not None
        return []

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_user_bookings",
        staticmethod(fake_get_user_bookings),
    )

    response = test_client(url="/items/bookings", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == []
    assert captured["user_id"] == jwt.payload["user_id"]
    assert captured["has_start"] is True
    assert captured["has_end"] is True


def test_create_booking_event(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "id": "booking-new",
        "item_id": "desktop-1",
        "item_type": "desktop",
        "units": 1,
        "reservables": {"vgpus": ["NVIDIA-2Q"]},
        "start": "2026-05-01T10:00:00+00:00",
        "end": "2026-05-01T11:00:00+00:00",
        "title": "Lab session",
        "user_id": jwt.payload["user_id"],
        "editable": True,
    }
    captured = {}

    def fake_create(payload, new_event):
        captured["user_id"] = payload["user_id"]
        captured["item_id"] = new_event.item_id
        return stub

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.create_booking_event",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/item/booking/event",
        method="POST",
        body={
            "item_id": "desktop-1",
            "item_type": "desktop",
            "start": "2026-05-01T10:00:00Z",
            "end": "2026-05-01T11:00:00Z",
            "title": "Lab session",
        },
        jwt=jwt,
    )

    assert response.status_code == 201
    assert response.json()["id"] == "booking-new"
    assert captured == {
        "user_id": jwt.payload["user_id"],
        "item_id": "desktop-1",
    }


def test_delete_booking_event(monkeypatch, test_client):
    """DELETE /item/booking/event/{id} now wires to the real
    ``BookingsService.delete_booking_event`` and gates on
    ``Helpers.owns_booking_id``. Replaces the previous mock-only
    regression test that asserted the no-op contract.
    """
    jwt = MockJWT()
    captured = {}

    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_booking_id",
        staticmethod(lambda payload, booking_id: booking_id),
    )

    def fake_delete(booking_id):
        captured["booking_id"] = booking_id

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.delete_booking_event",
        staticmethod(fake_delete),
    )

    response = test_client(
        url="/item/booking/event/booking-1",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert captured == {"booking_id": "booking-1"}


def test_update_booking_event(monkeypatch, test_client):
    """PUT /item/booking/event/{id}/edit wires to
    ``CommonBookings.update`` via ``BookingsService.update_booking_event``
    and gates on ``Helpers.owns_booking_id``. Replaces the previous
    open_router mock that did nothing."""
    jwt = MockJWT()
    captured = {}

    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_booking_id",
        staticmethod(lambda payload, booking_id: booking_id),
    )

    def fake_update(payload, booking_id, title, start, end):
        captured["booking_id"] = booking_id
        captured["title"] = title
        captured["start"] = start
        captured["end"] = end
        captured["user_id"] = payload["user_id"]

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.update_booking_event",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/item/booking/event/booking-1/edit",
        method="PUT",
        body={
            "title": "Updated title",
            "start": "2026-01-01T10:00:00+00:00",
            "end": "2026-01-01T11:00:00+00:00",
        },
        jwt=jwt,
    )
    assert response.status_code == 200
    assert captured["booking_id"] == "booking-1"
    assert captured["title"] == "Updated title"
    assert captured["user_id"] == jwt.payload["user_id"]


def test_get_booking_priority_desktop(monkeypatch, test_client):
    """GET /items/bookings/get-priority-desktop/{item_id} now uses
    real ``CommonBookings.get_user_priority`` filtering by ownership
    and merges in the desktop ``name``. Replaces the previous
    hard-coded mock on ``open_router``."""
    jwt = MockJWT()

    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )

    def fake_get_priority(payload, desktop_id):
        return {
            "priority": {"NVIDIA-A16-1Q": 5},
            "forbid_time": 60,
            "max_time": 1440,
            "max_items": 3,
            "name": "test-desktop",
        }

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_user_priority_for_desktop",
        staticmethod(fake_get_priority),
    )

    response = test_client(
        url="/items/bookings/get-priority-desktop/desktop-1",
        jwt=jwt,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "test-desktop"
    assert body["priority"] == {"NVIDIA-A16-1Q": 5}
    assert body["forbid_time"] == 60


def test_get_max_booking_date(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_max_date(payload, desktop_id):
        captured["desktop_id"] = desktop_id
        return "2026-12-31T23:59:59+00:00"

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_max_booking_date",
        staticmethod(fake_max_date),
    )

    response = test_client(url="/item/booking/max-booking-date/desktop-1", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["max_booking_date"] == "2026-12-31T23:59:59+00:00"
    assert captured == {"desktop_id": "desktop-1"}


def test_get_reservables_available(monkeypatch, test_client):
    """AvailableReservablesResponse wraps
    ``reservables_available: Optional[list[AvailableReservable]]`` — i.e.
    a flat list of ``{id, name, description, max_booking_date}`` items,
    not a ``{vgpus: [...]}`` dict."""
    jwt = MockJWT()
    stub = [
        {
            "id": "gpu-1",
            "name": "NVIDIA vGPU 2Q",
            "description": "2 GB vGPU",
            "max_booking_date": "2026-12-31T23:59:59+00:00",
        }
    ]
    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_available_reservables",
        staticmethod(lambda payload: stub),
    )

    response = test_client(url="/item/booking/reservables-available", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["reservables_available"][0]["id"] == "gpu-1"
    assert body["reservables_available"][0]["name"] == "NVIDIA vGPU 2Q"


# ─── Admin planning & booking plans (T1/admin/* shim replacements) ──────


def test_delete_planning(monkeypatch, test_client):
    """DELETE /item/planning/{id} — replaces
    /admin/reservables_planner/{plan_id} shim."""
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.planning.PlanningService.delete_planning",
        staticmethod(lambda plan_id: calls.append(plan_id)),
    )

    response = test_client(
        url="/item/planning/plan-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json()["message_code"] == "item.deleted"
    assert calls == ["plan-1"]


def test_empty_booking_plan(monkeypatch, test_client):
    """DELETE /item/booking/empty/{plan_id} — replaces
    /admin/booking/empty/{plan_id} shim."""
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.bookings.BookingsService.empty_planning",
        staticmethod(lambda plan_id: calls.append(plan_id)),
    )

    response = test_client(
        url="/item/booking/empty/plan-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["plan-1"]


def test_get_booking_plans(monkeypatch, test_client):
    """GET /item/booking/{id}/plans — replaces
    /admin/booking/{booking_id}/plans shim. The route validates each
    plan through ``BookingPlanResponse`` which requires
    (id, item_type, item_id, subitem_id, units, start, end, user_id,
    event_type, item)."""
    jwt = MockJWT()
    stub = [
        {
            "id": "plan-1",
            "item_type": "desktop",
            "item_id": "desktop-1",
            "subitem_id": "sub-1",
            "units": 1,
            "start": "2026-05-01T10:00:00+00:00",
            "end": "2026-05-01T11:00:00+00:00",
            "user_id": "user-1",
            "event_type": "booking",
            "item": "Lab A",
        }
    ]
    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_booking_plans",
        staticmethod(lambda booking_id: stub),
    )

    response = test_client(url="/item/booking/booking-1/plans", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body[0]["id"] == "plan-1"
    assert body[0]["item_type"] == "desktop"


# ─── Admin reservables (T1/admin/reservables* shims) ───────────────────


def _stub_reservable_item(item_id: str = "gpu-1") -> dict:
    return {
        "id": item_id,
        "name": f"GPU {item_id}",
        "description": "Test GPU",
        "brand": "NVIDIA",
        "model": "A40",
        "memory": "48GB",
        "architecture": "Ampere",
        "active_profile": None,
        "changing_to_profile": None,
        "physical_device": "0000:01:00.0",
        "profiles_enabled": ["NVIDIA-2Q"],
        "plans": {"current": 0, "active": False, "profile": None},
    }


def test_list_reservables(monkeypatch, test_client):
    """GET /items/reservables — replaces /admin/reservables and
    /admin/reservables/gpus v3 shims (list of types)."""
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.reservables.ReservableService.get_reservables",
        staticmethod(lambda: ["gpus", "usbs"]),
    )

    response = test_client(url="/items/reservables", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"reservables": ["gpus", "usbs"]}


def test_get_reservable_items(monkeypatch, test_client):
    """GET /items/reservables/{type} — replaces v3
    /admin/reservables/{reservable_type} shim."""
    jwt = MockJWT()
    stub = [_stub_reservable_item("gpu-1"), _stub_reservable_item("gpu-2")]
    monkeypatch.setattr(
        "api.services.reservables.ReservableService.get_reservable_detail",
        staticmethod(lambda reservable_type: stub),
    )

    response = test_client(url="/items/reservables/gpus", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["id"] == "gpu-1"


def test_list_reservable_profiles(monkeypatch, test_client):
    """GET /items/reservables/profiles/{type} — this route is
    registered BEFORE /items/reservables/{reservable_type}; if the
    order is ever reversed FastAPI will resolve ``profiles`` as the
    path parameter and this test will fail with a not_found body from
    the generic ``get_reservable_items`` handler. That makes this a
    regression test for both the route wiring and the route-order
    invariant."""
    jwt = MockJWT()

    def fake_list_profiles(reservable_type):
        return [
            {"id": "NVIDIA-A16-1Q", "name": "1Q"},
            {"id": "NVIDIA-A16-2Q", "name": "2Q"},
        ]

    monkeypatch.setattr(
        "api.services.reservables.ReservableService.list_profiles",
        staticmethod(fake_list_profiles),
    )

    response = test_client(url="/items/reservables/profiles/gpus", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body[0]["id"] == "NVIDIA-A16-1Q"
    assert body[1]["id"] == "NVIDIA-A16-2Q"


def test_add_reservable_item(monkeypatch, test_client):
    """POST /item/reservable/{type} — replaces v3
    /admin/reservables/{reservable_type} POST shim."""
    jwt = MockJWT()
    captured = {}

    def fake_add(reservable_type, data):
        captured["type"] = reservable_type
        captured["name"] = data["name"]
        return {"id": "gpu-new"}

    monkeypatch.setattr(
        "api.services.reservables.ReservableService.add_item",
        staticmethod(fake_add),
    )

    response = test_client(
        url="/item/reservable/gpus",
        method="POST",
        body={"name": "A40", "bookable": "yes", "description": "Test"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "gpu-new"}
    assert captured == {"type": "gpus", "name": "A40"}


def test_delete_reservable_item(monkeypatch, test_client):
    """DELETE /item/reservable/{type}/{id} — replaces v3
    /admin/reservables/delete/{reservable_type}/{reservable_id} shim.
    Also pins the ``notify_user`` query-param forwarding (v4 parity)."""
    jwt = MockJWT()
    calls = []

    def fake_delete(reservable_type, item_id, notify_user=False):
        calls.append((reservable_type, item_id, notify_user))

    monkeypatch.setattr(
        "api.services.reservables.ReservableService.delete_item",
        staticmethod(fake_delete),
    )

    response = test_client(
        url="/item/reservable/gpus/gpu-1",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert calls == [("gpus", "gpu-1", False)]

    # Now exercise notify_user=true
    calls.clear()
    response = test_client(
        url="/item/reservable/gpus/gpu-2?notify_user=true",
        method="DELETE",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert calls == [("gpus", "gpu-2", True)]


def test_check_last_subitem(monkeypatch, test_client):
    """GET /item/reservable/check-last/{type}/{subitem}/{item} —
    replaces /admin/reservables/check/last/{reservable_type}/{subitem}/{item}
    shim."""
    jwt = MockJWT()
    stub = {
        "last": [False],
        "desktops": [],
        "plans": [],
        "bookings": [],
        "deployments": [],
    }
    monkeypatch.setattr(
        "api.services.reservables.ReservableService.check_last_subitem",
        staticmethod(lambda reservable_type, subitem_id, item_id: stub),
    )

    response = test_client(
        url="/item/reservable/check-last/gpus/NVIDIA-2Q/gpu-1",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == stub


def test_enable_reservable_subitem(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_enable(reservable_type, item_id, subitem_id, enabled, notify_user=False):
        captured["type"] = reservable_type
        captured["item_id"] = item_id
        captured["subitem_id"] = subitem_id
        captured["enabled"] = enabled
        captured["notify_user"] = notify_user
        return {"enabled": enabled}

    monkeypatch.setattr(
        "api.services.reservables.ReservableService.enable_subitem",
        staticmethod(fake_enable),
    )

    response = test_client(
        url="/item/reservable/enable/gpus/gpu-1/NVIDIA-2Q",
        method="PUT",
        body={"enabled": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {
        "type": "gpus",
        "item_id": "gpu-1",
        "subitem_id": "NVIDIA-2Q",
        "enabled": True,
        "notify_user": False,
    }


def test_delete_planner_plan(monkeypatch, test_client):
    """DELETE /item/reservables-planner/{id} — replaces v3
    /admin/reservables_planner/{plan_id} shim."""
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.reservables.ReservableService.delete_plan",
        staticmethod(lambda plan_id: calls.append(plan_id)),
    )

    response = test_client(
        url="/item/reservables-planner/plan-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["plan-1"]


def test_get_users_priorities(monkeypatch, test_client):
    """POST /items/bookings/priorities is on ``admin_router`` and expects
    a body matching ``GetUsersPrioritiesRequest`` (``rule_id``). The
    service receives the rule_id only (no payload kwarg in the route)."""
    jwt = MockJWT()  # default admin role satisfies admin_router
    stub = [
        {
            "id": "user-1",
            "user_id": "user-1",
            "item_type": "desktop",
            "priority": {"default": 0},
        }
    ]
    calls = []

    def fake_get(rule_id):
        calls.append(rule_id)
        return stub

    monkeypatch.setattr(
        "api.services.bookings.BookingsService.get_users_priorities",
        staticmethod(fake_get),
    )

    response = test_client(
        url="/items/bookings/priorities",
        method="POST",
        body={"rule_id": "default"},
        jwt=jwt,
    )

    # ``response_model=list[BookingPriorityUser]`` declares id/username/
    # name; extra fields like ``user_id`` round-trip via extra="allow"
    # but their order on the wire isn't pinned. Assert on the declared
    # ``id`` field only — that's what the schema documents.
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "user-1"
    assert calls == ["default"]
