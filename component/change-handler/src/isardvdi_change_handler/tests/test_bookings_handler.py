# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


def _booking(**overrides):
    # Default to a future window so ``editable`` is True. Tests that need
    # a past booking pass ``start=`` and ``end=`` explicitly.
    future_start = datetime.now(timezone.utc) + timedelta(hours=2)
    future_end = future_start + timedelta(hours=1)
    base = dict(
        id="b1",
        user_id="u1",
        item_id="i1",
        item_type=None,
        start=future_start,
        end=future_end,
    )
    base.update(overrides)
    return FakeRow(**base)


class TestBookingsHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.bookings import BookingsHandler

        sio = AsyncMock()
        return BookingsHandler(sio, "bookings")

    @pytest.mark.asyncio
    async def test_insert_emits_booking_and_bookingitem_add(self, handler):
        await handler.on_insert(_booking())
        events = [c[0][0] for c in handler.socketio_server.emit.call_args_list]
        assert events[0] == "booking_add"
        assert events[1] == "bookingitem_add"

    @pytest.mark.asyncio
    async def test_insert_prepares_dates_and_adds_editable_and_event_type(
        self, handler
    ):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        await handler.on_insert(_booking(start=future, end=future + timedelta(hours=1)))
        payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        # ISO-8601 with offset, e.g. "2026-05-04T14:00+0000"
        assert "T" in payload["start"]
        assert "T" in payload["end"]
        assert payload["event_type"] == "event"
        assert payload["editable"] is True

    @pytest.mark.asyncio
    async def test_insert_marks_past_booking_not_editable(self, handler):
        """Pin Bug 2 — apiv4-integration was hard-coding ``editable=True``
        on every change-handler emission. Past bookings (start <= now)
        must surface ``editable=False`` so the Vue 2 calendar hides
        Edit/Delete buttons in real-time.
        """
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        await handler.on_insert(_booking(start=past, end=past + timedelta(hours=1)))
        payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        assert payload["editable"] is False

    @pytest.mark.asyncio
    async def test_update_emits_editable_for_future_booking(self, handler):
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        await handler.on_update(
            _booking(),
            _booking(start=future, end=future + timedelta(hours=1)),
        )
        payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        assert payload["editable"] is True

    @pytest.mark.asyncio
    async def test_update_marks_past_booking_not_editable(self, handler):
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        await handler.on_update(
            _booking(),
            _booking(start=past, end=past + timedelta(hours=1)),
        )
        payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        assert payload["editable"] is False

    @pytest.mark.asyncio
    async def test_delete_event_payload_carries_editable_flag(self, handler):
        """Delete emits both ``booking_delete`` (id-only) and
        ``bookingitem_delete`` (full payload). The bookingitem payload
        must still carry the editable flag so the calendar can hide UI
        for the no-longer-extant booking.
        """
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        await handler.on_delete(_booking(start=past, end=past + timedelta(hours=1)))
        # bookingitem_delete is the second emission
        bookingitem_payload = json.loads(
            handler.socketio_server.emit.call_args_list[1][0][1]
        )
        assert bookingitem_payload["editable"] is False

    @pytest.mark.asyncio
    async def test_update_emits_booking_and_bookingitem_update(self, handler):
        await handler.on_update(_booking(), _booking())
        events = [c[0][0] for c in handler.socketio_server.emit.call_args_list]
        assert "booking_update" in events
        assert "bookingitem_update" in events

    @pytest.mark.asyncio
    async def test_delete_emits_booking_delete_with_id_only(self, handler):
        await handler.on_delete(_booking())
        first = handler.socketio_server.emit.call_args_list[0]
        assert first[0][0] == "booking_delete"
        assert json.loads(first[0][1]) == {"id": "b1"}

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.bookings.DeploymentsProcessed.get_deployment",
        return_value={
            "id": "dep1",
            "user": "u1",
            "desktops": [
                {"id": "desk1", "user": "u1"},
                {"id": "desk2", "user": "u2"},
            ],
        },
    )
    async def test_deployment_booking_emits_deployment_and_desktop_updates(
        self, _mock_get, handler
    ):
        await handler.on_insert(_booking(item_type="deployment", item_id="dep1"))
        events = [c[0][0] for c in handler.socketio_server.emit.call_args_list]
        assert events.count("deployment_update") == 1
        assert events.count("desktop_update") == 2
        desktop_rooms = [
            c[1]["room"]
            for c in handler.socketio_server.emit.call_args_list
            if c[0][0] == "desktop_update"
        ]
        assert set(desktop_rooms) == {"u1", "u2"}

    @pytest.mark.asyncio
    @patch(
        "isardvdi_change_handler.handlers.bookings.DesktopsProcessed._parse_desktop",
        return_value={"id": "desk1", "user": "u1"},
    )
    @patch(
        "isardvdi_change_handler.handlers.bookings.Domain.get",
        return_value={"id": "desk1"},
    )
    async def test_desktop_booking_emits_single_desktop_update(
        self, _mock_domain, _mock_parse, handler
    ):
        await handler.on_insert(_booking(item_type="desktop", item_id="desk1"))
        events = [c[0][0] for c in handler.socketio_server.emit.call_args_list]
        assert events.count("desktop_update") == 1
        _mock_domain.assert_called_once_with("desk1")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("item_type", [None, "media", "template", "lab", ""])
    async def test_unknown_item_type_emits_no_extra_events(self, handler, item_type):
        """`send_booking_item_event` is the sole fan-out point that talks to
        deployments / desktops. Anything other than those two `item_type`
        values is silently dropped — pin that contract.
        """
        with patch(
            "isardvdi_change_handler.handlers.bookings.DeploymentsProcessed"
        ) as mock_dep, patch(
            "isardvdi_change_handler.handlers.bookings.DesktopsProcessed"
        ) as mock_desk, patch(
            "isardvdi_change_handler.handlers.bookings.Domain"
        ) as mock_domain:
            await handler.on_insert(_booking(item_type=item_type))
            events = [c[0][0] for c in handler.socketio_server.emit.call_args_list]
            assert events == ["booking_add", "bookingitem_add"]
            mock_dep.get_deployment.assert_not_called()
            mock_desk._parse_desktop.assert_not_called()
            mock_domain.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_user_id_is_none(self, handler):
        """Regression: user_id=None must NOT broadcast to whole /userspace."""
        await handler.on_insert(_booking(user_id=None))
        calls = [
            c
            for c in handler.socketio_server.emit.await_args_list
            if c.kwargs.get("room") is None or (len(c.args) >= 4 and c.args[3] is None)
        ]
        assert calls == []
