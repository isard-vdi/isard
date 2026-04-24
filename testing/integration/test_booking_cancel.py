# SPDX-License-Identifier: AGPL-3.0-or-later

"""Booking create + cancel round-trip against a live stack.

Covers the cancel path that v3 → apiv4 migration regressed on twice
(once on the ownership dependency, once on the service-layer
``CommonBookings.delete`` contract). A real-stack round-trip is the
only way to pin the whole chain:

    auth → owns_booking_id dep → BookingsService.delete_booking_event
           → CommonBookings.delete → DB writes + reservables release.

Test strategy:
1. Create a desktop in the session namespace (cleanup wipes it on
   teardown — booking rows cascade-delete when the domain is removed).
2. Attempt to create a booking event one hour out.
   - If the stack lacks reservables (no GPUs seeded), the POST will
     428 with "cannot book, no reservable units". We treat that as
     ``pytest.skip`` since the cancel path can't be exercised without
     a booking to cancel.
3. Verify the booking appears in GET /items/bookings.
4. DELETE the booking.
5. Confirm a second DELETE returns 404 — the row is actually gone.
6. Confirm the booking no longer appears in GET /items/bookings.

Error-only assertions (always run, cheap, don't need reservables):
- DELETE /item/booking/event/no-such-id → 404 for admin (owns_booking_id
  bypasses admin so it reaches the service layer's not_found).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from .helpers.client import IsardClient

# Give the server plenty of buffer from "now"; a booking that overlaps
# the current second can race the planner and 428 for reasons unrelated
# to the cancel path we're testing.
BOOKING_OFFSET_MIN = 60
BOOKING_DURATION_MIN = 30
DESKTOP_CREATE_TIMEOUT = 90


def _iso(dt: datetime) -> str:
    # apiv4 accepts AwareDatetime on input; we stringify so the JSON
    # encoder doesn't pass a naive datetime through.
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")


def _find_simple_template_id(client: IsardClient) -> str:
    """Pick any template the admin can derive a desktop from.

    The populate seed always ships at least one reference template;
    we take the first entry in /items/templates to stay decoupled from
    which template names exist in a given test stack.
    """
    templates = client.get("/api/v4/items/templates").get("templates", [])
    assert templates, "no templates available — is the stack seeded?"
    return templates[0]["id"]


@pytest.mark.real
def test_delete_nonexistent_booking_returns_404(admin_client: IsardClient):
    """owns_booking_id bypasses admin → the delete reaches the service,
    which raises not_found on an id that doesn't exist. 404 is the
    contract the frontend retry logic relies on."""
    resp = admin_client.raw("DELETE", "/api/v4/item/booking/event/does-not-exist-0000")
    assert (
        resp.status_code == 404
    ), f"expected 404 for missing booking; got {resp.status_code} body={resp.text[:200]}"


@pytest.mark.real
@pytest.mark.slow
def test_booking_create_then_cancel_roundtrip(
    admin_client: IsardClient,
    test_namespace: str,
):
    template_id = _find_simple_template_id(admin_client)

    # --- Step 1: create a desktop for the booking to target ---
    desktop_name = f"{test_namespace}booking_desktop"
    desktop = admin_client.post(
        "/api/v4/item/desktop",
        json_body={
            "template_id": template_id,
            "name": desktop_name,
            "description": "",
        },
    )
    desktop_id = desktop["id"]
    admin_client.poll_desktop_status(
        desktop_id, want={"Stopped"}, max_wait=DESKTOP_CREATE_TIMEOUT
    )

    # --- Step 2: attempt to book the desktop 1h out, 30 min long ---
    start = datetime.now(timezone.utc) + timedelta(minutes=BOOKING_OFFSET_MIN)
    end = start + timedelta(minutes=BOOKING_DURATION_MIN)
    title = f"{test_namespace}booking"
    resp = admin_client.raw(
        "POST",
        "/api/v4/item/booking/event",
        json={
            "item_id": desktop_id,
            "item_type": "desktop",
            "start": _iso(start),
            "end": _iso(end),
            "title": title,
            "now": False,
        },
    )
    # 428 = no reservables / quota — common on a stripped test stack.
    # Skip rather than fail: the cancel path can't be tested without a
    # booking and whether the stack is bookable is a stack config issue
    # not a code regression.
    if resp.status_code == 428:
        pytest.skip(
            f"stack rejected booking with 428: {resp.text[:200]} — no reservables seeded"
        )
    assert (
        resp.status_code == 201
    ), f"expected 201 from POST booking; got {resp.status_code} body={resp.text[:300]}"
    booking = resp.json()
    booking_id = booking["id"]
    # Make sure the server echoed back what we sent. ``reservables`` and
    # ``units`` are stack-dependent, so don't pin them here.
    assert booking["item_id"] == desktop_id
    assert booking["item_type"] == "desktop"
    assert booking["title"] == title

    # --- Step 3: confirm the booking is visible in the user list ---
    bookings = admin_client.get("/api/v4/items/bookings")
    assert any(
        b["id"] == booking_id for b in bookings
    ), f"booking {booking_id} not in /items/bookings; got ids={[b['id'] for b in bookings]}"

    # --- Step 4: delete it ---
    admin_client.delete(f"/api/v4/item/booking/event/{booking_id}", expected=(200, 204))

    # --- Step 5: second delete must 404 (the row is actually gone) ---
    second = admin_client.raw("DELETE", f"/api/v4/item/booking/event/{booking_id}")
    assert (
        second.status_code == 404
    ), f"second delete should 404; got {second.status_code} body={second.text[:200]}"

    # --- Step 6: gone from the listing ---
    after = admin_client.get("/api/v4/items/bookings")
    assert not any(
        b["id"] == booking_id for b in after
    ), f"booking {booking_id} still visible after delete"
