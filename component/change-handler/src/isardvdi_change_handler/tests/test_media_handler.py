# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import AsyncMock

import pytest
from isardvdi_change_handler.tests.conftest import FakeRow


class TestMediaHandler:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.media import MediaHandler

        sio = AsyncMock()
        return MediaHandler(sio, "media")

    @pytest.mark.asyncio
    async def test_on_insert_adds_editable_for_userspace(self, handler):
        row = FakeRow(id="m1", user="u1", category="cat1")
        await handler.on_insert(row)

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["editable"] is True
        assert payload["id"] == "m1"

    @pytest.mark.asyncio
    async def test_on_insert_no_editable_for_admins(self, handler):
        row = FakeRow(id="m1", user="u1", category="cat1")
        await handler.on_insert(row)

        second_call = handler.socketio_server.emit.call_args_list[1]
        payload = json.loads(second_call[0][1])
        assert "editable" not in payload

    @pytest.mark.asyncio
    async def test_on_update_enriches_payload(self, handler):
        old = FakeRow(id="m1", status="Downloading", user="u1", category="cat1")
        new = FakeRow(id="m1", status="Downloaded", user="u1", category="cat1")
        await handler.on_update(old, new)

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["editable"] is True
        assert payload["user_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_on_delete_adds_editable_for_userspace(self, handler):
        row = FakeRow(id="m1", user="u1", category="cat1")
        await handler.on_delete(row)

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["editable"] is True

    @pytest.mark.asyncio
    async def test_with_editable_preserves_existing_additional_properties(
        self, handler
    ):
        row = FakeRow(
            id="m1",
            user="u1",
            category="cat1",
            additional_properties={"custom_field": "value"},
        )
        await handler.on_insert(row)

        first_call = handler.socketio_server.emit.call_args_list[0]
        payload = json.loads(first_call[0][1])
        assert payload["editable"] is True
        assert payload["custom_field"] == "value"

    @pytest.mark.asyncio
    async def test_on_insert_emits_to_user_category_and_admins(self, handler):
        """Pin the full (event, namespace, room) contract for all 3 insert emits:
        - userspace → user (room=u1) with editable=True
        - administrators → per-category (room=cat1) WITHOUT editable
        - administrators → admins (room=admins) via super, WITHOUT editable
        """
        row = FakeRow(id="m1", user="u1", category="cat1")
        await handler.on_insert(row)

        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 3

        # 1) user
        user_args, user_kw = calls[0]
        assert user_args[0] == "media_add"
        assert user_kw["namespace"] == "/userspace"
        assert user_kw["room"] == "u1"
        assert json.loads(user_args[1])["editable"] is True

        # 2) admin per-category
        cat_args, cat_kw = calls[1]
        assert cat_args[0] == "media_add"
        assert cat_kw["namespace"] == "/administrators"
        assert cat_kw["room"] == "cat1"
        assert "editable" not in json.loads(cat_args[1])

        # 3) admins room (via BaseHandler.on_insert — namespace/room as kwargs)
        base_args, base_kw = calls[2]
        assert base_args[0] == "media_add"
        assert base_kw["namespace"] == "/administrators"
        assert base_kw["room"] == "admins"
        assert "editable" not in json.loads(base_args[1])

    @pytest.mark.asyncio
    async def test_on_update_enrichment_reaches_userspace_payload(self, handler):
        """On update, the userspace payload must carry BOTH editable=True
        and the full enrichment dict.
        """
        old = FakeRow(id="m1", status="Downloading", user="u1", category="cat1")
        new = FakeRow(id="m1", status="Downloaded", user="u1", category="cat1")
        await handler.on_update(old, new)

        user_payload = json.loads(handler.socketio_server.emit.call_args_list[0][0][1])
        assert user_payload["editable"] is True
        assert user_payload["user_name"] == "Alice"
        assert user_payload["group_name"] == "G1"
        assert user_payload["category_name"] == "Cat"

    @pytest.mark.asyncio
    async def test_on_delete_emits_media_delete_to_user_category_and_admins(
        self, handler
    ):
        row = FakeRow(id="m1", user="u1", category="cat1")
        await handler.on_delete(row)

        calls = handler.socketio_server.emit.call_args_list
        assert len(calls) == 3
        assert calls[0][0][0] == "media_delete"
        assert calls[0][1]["room"] == "u1"
        assert json.loads(calls[0][0][1])["editable"] is True
        assert calls[1][0][0] == "media_delete"
        assert calls[1][1]["room"] == "cat1"
        # Super() on_delete passes namespace/room as kwargs.
        base_args, base_kw = calls[2]
        assert base_args[0] == "media_delete"
        assert base_kw["namespace"] == "/administrators"
        assert base_kw["room"] == "admins"


@pytest.mark.asyncio
async def test_media_transition_to_deleted_emits_only_delete(
    media_handler, fake_socketio, media_row_factory
):
    old_val = media_row_factory(id="m1", status="Downloaded")
    new_val = media_row_factory(id="m1", status="deleted")

    await media_handler.on_update(old_val, new_val)

    events = [e[0] for e in fake_socketio.emitted]
    assert "media_delete" in events
    assert (
        "media_update" not in events
    ), f"transition-to-deleted must not also emit media_update; got {events}"


class TestMediaHandlerInvalidFormatCleanup:
    """On the transition to ``DownloadFailedInvalidFormat`` the handler must
    delete the broken disk artefact so apiv3 + apiv4 stay symmetric.
    """

    @pytest.mark.asyncio
    async def test_transition_to_invalid_format_calls_delete_file(
        self, media_handler, media_row_factory, monkeypatch
    ):
        delete_calls: list[dict] = []

        class FakeMedia:
            def __init__(self, media_id):
                delete_calls.append({"phase": "init", "id": media_id})

            def delete_file(self, user_id=None, keep_status=None):
                delete_calls.append(
                    {"phase": "call", "user_id": user_id, "keep_status": keep_status}
                )

        monkeypatch.setattr("isardvdi_change_handler.handlers.media.Media", FakeMedia)

        old = media_row_factory(id="m1", status="Downloading", user="u1")
        new = media_row_factory(
            id="m1", status="DownloadFailedInvalidFormat", user="u1"
        )

        await media_handler.on_update(old, new)

        assert delete_calls == [
            {"phase": "init", "id": "m1"},
            {"phase": "call", "user_id": "u1", "keep_status": True},
        ]

    @pytest.mark.asyncio
    async def test_no_cleanup_when_already_invalid_format(
        self, media_handler, media_row_factory, monkeypatch
    ):
        """Repeated change-feed events with the same InvalidFormat status
        must not re-trigger delete_file.
        """
        called = False

        class FakeMedia:
            def __init__(self, _id):
                pass

            def delete_file(self, **_kwargs):
                nonlocal called
                called = True

        monkeypatch.setattr("isardvdi_change_handler.handlers.media.Media", FakeMedia)

        old = media_row_factory(id="m1", status="DownloadFailedInvalidFormat")
        new = media_row_factory(id="m1", status="DownloadFailedInvalidFormat")

        await media_handler.on_update(old, new)

        assert (
            called is False
        ), "delete_file must only fire on the InvalidFormat transition"

    @pytest.mark.asyncio
    async def test_no_cleanup_for_other_status_transitions(
        self, media_handler, media_row_factory, monkeypatch
    ):
        called = False

        class FakeMedia:
            def __init__(self, _id):
                pass

            def delete_file(self, **_kwargs):
                nonlocal called
                called = True

        monkeypatch.setattr("isardvdi_change_handler.handlers.media.Media", FakeMedia)

        old = media_row_factory(id="m1", status="Downloading")
        new = media_row_factory(id="m1", status="Downloaded")

        await media_handler.on_update(old, new)

        assert called is False

    @pytest.mark.asyncio
    async def test_invalid_format_still_emits_media_update(
        self, media_handler, fake_socketio, media_row_factory, monkeypatch
    ):
        """The cleanup must not suppress the user-facing update event —
        the UI still needs to render the failure state.
        """

        class FakeMedia:
            def __init__(self, _id):
                pass

            def delete_file(self, **_kwargs):
                pass

        monkeypatch.setattr("isardvdi_change_handler.handlers.media.Media", FakeMedia)

        old = media_row_factory(
            id="m1", status="Downloading", user="u1", category="cat1"
        )
        new = media_row_factory(
            id="m1", status="DownloadFailedInvalidFormat", user="u1", category="cat1"
        )

        await media_handler.on_update(old, new)

        events = [e[0] for e in fake_socketio.emitted]
        assert events.count("media_update") >= 2  # /userspace + /administrators


class TestMediaHandlerNoneRoomRegression:
    @pytest.fixture
    def handler(self):
        from isardvdi_change_handler.handlers.media import MediaHandler

        sio = AsyncMock()
        return MediaHandler(sio, "media")

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_category_is_none(self, handler):
        """Regression: category=None must NOT broadcast admin events to all admins."""
        await handler.on_insert(FakeRow(id="m1", user="u1", category=None))
        for c in handler.socketio_server.emit.await_args_list:
            room = (
                c.kwargs.get("room")
                if "room" in c.kwargs
                else (c.args[3] if len(c.args) >= 4 else None)
            )
            assert room is not None

    @pytest.mark.asyncio
    async def test_on_insert_skips_when_user_is_none(self, handler):
        """Regression: user=None must NOT broadcast to whole /userspace."""
        await handler.on_insert(FakeRow(id="m1", user=None, category="cat1"))
        for c in handler.socketio_server.emit.await_args_list:
            room = (
                c.kwargs.get("room")
                if "room" in c.kwargs
                else (c.args[3] if len(c.args) >= 4 else None)
            )
            assert room is not None
