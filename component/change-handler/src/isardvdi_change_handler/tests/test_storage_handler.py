# SPDX-License-Identifier: AGPL-3.0-or-later

"""The storage changefeed handler's two real decisions.

The first is what it refuses to send. ``Storage.__setattr__`` refreshes
``status_time`` on every write, so a row rewritten with an unchanged
status still produces a changefeed update; forwarding those costs the
frontend a DataTable invalidate per write. The suppression has to be
narrow, though - dropping an update that carried a real field change is
a silently stale row, which is worse than the noise it saves.

The second is whether ``status`` rides along. The listener branches on
its presence: with it, the row is moved between tables; without it, the
existing row is invalidated in place. So an update that changed only a
non-status field must NOT carry a status, or the row is torn out of its
table and re-added on a write that never changed which table it belongs
to.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


@pytest.fixture
def handler():
    from isardvdi_change_handler.handlers.storage import StorageHandler

    return StorageHandler(AsyncMock(), "storage")


def _emitted(handler):
    """The payloads the handler fanned out, decoded, with their rooms."""
    return [
        (json.loads(call.args[1]), call.kwargs.get("room"))
        for call in handler.emit.await_args_list
    ]


@pytest.fixture(autouse=True)
def _no_user_lookup():
    """Keep the category lookup out of the payload tests."""
    with patch(
        "isardvdi_change_handler.handlers.storage.Caches.get_cached_user_with_names",
        MagicMock(return_value=None),
    ):
        yield


# ---------------------------------------------------------------------------
# on_update — the suppression
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_status_time_only_write_is_not_forwarded(handler):
    """The write every unchanged-status save produces sends nothing."""
    handler.emit = AsyncMock()
    old = FakeRow(id="s1", status="ready", additional_properties={"status_time": 1})
    new = FakeRow(id="s1", status="ready", additional_properties={"status_time": 2})

    await handler.on_update(old, new)

    handler.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_real_field_change_under_an_unchanged_status_is_forwarded(handler):
    """Suppression must not swallow an update that carried content.

    ``progress`` moving while the row stays ``maintenance`` is the whole
    point of the progress bar; a suppression keyed on status alone would
    freeze it.
    """
    handler.emit = AsyncMock()
    old = FakeRow(id="s1", status="maintenance", additional_properties={"progress": 10})
    new = FakeRow(id="s1", status="maintenance", additional_properties={"progress": 90})

    await handler.on_update(old, new)

    payloads = _emitted(handler)
    assert payloads, "the progress change was suppressed"
    assert payloads[0][0]["progress"] == 90


@pytest.mark.asyncio
async def test_an_unchanged_status_is_left_out_of_the_payload(handler):
    """No status key means "invalidate in place", which is what happened.

    Including it here would move the row between tables on a write that
    did not change which table it belongs to.
    """
    handler.emit = AsyncMock()
    old = FakeRow(id="s1", status="ready", additional_properties={"progress": 10})
    new = FakeRow(id="s1", status="ready", additional_properties={"progress": 90})

    await handler.on_update(old, new)

    payload = _emitted(handler)[0][0]
    assert "status" not in payload


@pytest.mark.asyncio
async def test_a_changed_status_is_carried_so_the_row_moves_tables(handler):
    handler.emit = AsyncMock()
    old = FakeRow(id="s1", status="maintenance")
    new = FakeRow(id="s1", status="ready")

    await handler.on_update(old, new)

    payload = _emitted(handler)[0][0]
    assert payload["status"] == "ready"


@pytest.mark.asyncio
async def test_a_first_sighting_with_no_previous_row_is_forwarded(handler):
    """``old_val`` is None on a feed that starts mid-life; that is a real
    change, not a no-op, and must not be suppressed."""
    handler.emit = AsyncMock()

    await handler.on_update(None, FakeRow(id="s1", status="ready"))

    assert _emitted(handler)


# ---------------------------------------------------------------------------
# insert / delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_insert_always_carries_its_status(handler):
    handler.emit = AsyncMock()

    await handler.on_insert(FakeRow(id="s1", status="ready"))

    assert _emitted(handler)[0][0]["status"] == "ready"


@pytest.mark.asyncio
async def test_a_delete_is_announced_as_the_deleted_status(handler):
    """There is no delete branch in the listener, but any non-ready status
    removes the row from the ready table - so the deletion is spelled as
    one instead of being dropped."""
    handler.emit = AsyncMock()

    await handler.on_delete(FakeRow(id="s1", status="ready"))

    payload = _emitted(handler)[0][0]
    assert payload == {"id": "s1", "status": "deleted"}


# ---------------------------------------------------------------------------
# _emit_storage — the fan-out, and its fail-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_owner_and_their_category_both_get_the_event(handler):
    handler.emit = AsyncMock()

    with patch(
        "isardvdi_change_handler.handlers.storage.Caches.get_cached_user_with_names",
        MagicMock(return_value={"category": "cat1"}),
    ):
        await handler._emit_storage({"id": "s1"}, "u1")

    assert [room for _, room in _emitted(handler)] == ["admins", "u1", "cat1"]


@pytest.mark.asyncio
async def test_a_failed_user_lookup_still_reaches_the_admins(handler):
    """Fail open: the category room is a nicety, the admin broadcast is
    the one that keeps the admin storage table live. Letting the lookup
    take the whole emit down would blank that table on any cache fault.
    """
    handler.emit = AsyncMock()

    with patch(
        "isardvdi_change_handler.handlers.storage.Caches.get_cached_user_with_names",
        MagicMock(side_effect=RuntimeError("cache down")),
    ):
        await handler._emit_storage({"id": "s1"}, "u1")

    assert [room for _, room in _emitted(handler)] == ["admins", "u1"]


@pytest.mark.asyncio
async def test_a_row_with_no_owner_is_broadcast_to_admins_only(handler):
    handler.emit = AsyncMock()

    await handler._emit_storage({"id": "s1"}, None)

    assert [room for _, room in _emitted(handler)] == ["admins"]
