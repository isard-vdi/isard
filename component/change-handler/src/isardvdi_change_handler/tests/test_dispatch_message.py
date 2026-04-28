# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``__main__.dispatch_message`` — the typed-envelope
deserialise + handler-forward path.

This was the boundary that broke when the change-handler was first
ingested into apiv4-integration: the loop body was passing the raw
Redis dict through to handlers that expected the Pydantic-typed
shape from ``changefeed_subscribers``. The fix calls
``subscriber.parse_dict(data)`` first and forwards
``envelope.change`` (a ``Change`` model with ``.new_val`` / ``.old_val``
typed rows). These tests pin that contract so a future refactor that
short-circuits ``parse_dict`` is caught early — and verify all the
swallow-and-log fallbacks remain in place.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from isardvdi_change_handler.__main__ import dispatch_message


@pytest.fixture
def logger():
    """Real ``logging.Logger`` API surface, no I/O. We assert on the
    mock so a future refactor that drops a warning is visible."""
    return MagicMock(warning=MagicMock(), info=MagicMock(), error=MagicMock())


@pytest.fixture
def handler():
    h = MagicMock()
    h.handle = AsyncMock()
    return h


@pytest.fixture
def envelope_with_change():
    """``subscriber.parse_dict`` returns an envelope whose ``.change``
    attribute is what the handler receives."""
    env = MagicMock()
    env.change = MagicMock(name="change_object")
    return env


# ══════════════════════════════════════════════════════════════════════════
#  Happy path
# ══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_forwards_envelope_change_to_handler(
        self, monkeypatch, logger, handler, envelope_with_change
    ):
        """The handler receives ``envelope.change`` — never the raw dict.
        This is the contract the apiv4-integration ingest broke; pin it."""
        subscriber = MagicMock(parse_dict=MagicMock(return_value=envelope_with_change))
        monkeypatch.setitem(
            __import__(
                "isardvdi_change_handler.__main__", fromlist=["TABLE_TO_SUBSCRIBER"]
            ).TABLE_TO_SUBSCRIBER,
            "users",
            subscriber,
        )
        data = {"table": "users", "new_val": {"id": "u1"}}

        await dispatch_message(data, {"users": handler}, logger)

        subscriber.parse_dict.assert_called_once_with(data)
        handler.handle.assert_awaited_once_with(envelope_with_change.change)
        # And not with the raw dict — guard the regression:
        assert handler.handle.await_args.args[0] is envelope_with_change.change
        assert handler.handle.await_args.args[0] is not data


# ══════════════════════════════════════════════════════════════════════════
#  Swallow-and-log paths (one bad payload must not kill the loop)
# ══════════════════════════════════════════════════════════════════════════


class TestSwallowAndLog:
    @pytest.mark.asyncio
    async def test_unknown_table_skipped(self, monkeypatch, logger, handler):
        """``TABLE_TO_SUBSCRIBER`` lookup miss → log warning and return.
        Handler is never called even if registered under another key."""
        # Don't touch TABLE_TO_SUBSCRIBER — "ghost" is naturally absent.
        await dispatch_message(
            {"table": "ghost", "new_val": {}},
            {"ghost": handler},
            logger,
        )
        logger.warning.assert_called()
        assert "ghost" in logger.warning.call_args.args[0]
        handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_table_field_skipped(self, monkeypatch, logger, handler):
        """``data["table"]`` missing → ``data.get("table")`` returns
        ``None`` and the lookup misses. No-op + warning."""
        await dispatch_message({}, {"users": handler}, logger)
        logger.warning.assert_called()
        handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_parse_dict_failure_swallowed(self, monkeypatch, logger, handler):
        """Malformed envelope → log error and return. Handler not
        called. The next message in the loop must still be processed
        (covered by the loop in production code; here we just assert
        the function returns rather than re-raising)."""
        bad_subscriber = MagicMock(
            parse_dict=MagicMock(side_effect=ValueError("schema mismatch"))
        )
        monkeypatch.setitem(
            __import__(
                "isardvdi_change_handler.__main__", fromlist=["TABLE_TO_SUBSCRIBER"]
            ).TABLE_TO_SUBSCRIBER,
            "users",
            bad_subscriber,
        )

        await dispatch_message(
            {"table": "users", "junk": True}, {"users": handler}, logger
        )

        logger.error.assert_called()
        handler.handle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_handler_registered_skipped(
        self, monkeypatch, logger, envelope_with_change
    ):
        """Subscriber resolves and parses fine, but the table is not in
        ``handler_map`` — log warning, do not raise."""
        subscriber = MagicMock(parse_dict=MagicMock(return_value=envelope_with_change))
        monkeypatch.setitem(
            __import__(
                "isardvdi_change_handler.__main__", fromlist=["TABLE_TO_SUBSCRIBER"]
            ).TABLE_TO_SUBSCRIBER,
            "users",
            subscriber,
        )

        # Empty handler_map → "no handler registered"
        await dispatch_message({"table": "users", "new_val": {}}, {}, logger)
        logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_handler_exception_swallowed(
        self, monkeypatch, logger, handler, envelope_with_change
    ):
        """Handler raises → traceback is logged but the listen loop
        keeps running. Critical: a single broken handler must not take
        down the entire change-handler service."""
        handler.handle.side_effect = RuntimeError("downstream broke")
        subscriber = MagicMock(parse_dict=MagicMock(return_value=envelope_with_change))
        monkeypatch.setitem(
            __import__(
                "isardvdi_change_handler.__main__", fromlist=["TABLE_TO_SUBSCRIBER"]
            ).TABLE_TO_SUBSCRIBER,
            "users",
            subscriber,
        )

        # Must not raise.
        await dispatch_message(
            {"table": "users", "new_val": {}}, {"users": handler}, logger
        )
        # Two error log calls: traceback + bare message — pin both.
        assert logger.error.call_count >= 2


# ══════════════════════════════════════════════════════════════════════════
#  Real subscriber wiring smoke-test
# ══════════════════════════════════════════════════════════════════════════


class TestRealSubscriberDeserialization:
    """Pin that ``TABLE_TO_SUBSCRIBER["users"]`` resolves and that its
    ``parse_dict`` accepts the dict shape the changefeed publisher
    emits. This is the inverse contract to changefeed's serialization
    test — together they cover the round-trip across the Redis hop."""

    @pytest.mark.asyncio
    async def test_users_envelope_round_trip_from_dict(
        self, monkeypatch, logger, handler
    ):
        from changefeed_subscribers import TABLE_TO_SUBSCRIBER

        if "users" not in TABLE_TO_SUBSCRIBER:
            pytest.skip("users subscriber not registered in this build")

        # Minimal users-table envelope shape — the subscriber's
        # Pydantic schema wraps ``new_val`` / ``old_val`` under a
        # nested ``change`` key; pin that here so a future schema
        # rename surfaces as a clear test failure.
        data = {
            "table": "users",
            "change": {
                "new_val": {"id": "u1", "name": "alice", "category": "default"},
                "old_val": None,
            },
        }

        await dispatch_message(data, {"users": handler}, logger)

        # The handler received an object with ``.new_val.id == "u1"``
        # — typed attribute access, not raw-dict subscript.
        handler.handle.assert_awaited_once()
        change = handler.handle.await_args.args[0]
        assert hasattr(change, "new_val")
        assert getattr(change.new_val, "id", None) == "u1"
