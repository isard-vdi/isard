# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_notify.py``."""

import pytest
from api.schemas.admin_notify import (
    DesktopQueueItem,
    NotifyDesktopRequest,
    NotifyUserDesktopRequest,
    SocketioEmitRequest,
)
from pydantic import ValidationError


class TestNotifyUserDesktopRequest:
    _required = {"user_id": "u-1", "type": "warning"}

    def test_accepts_required(self):
        r = NotifyUserDesktopRequest(**self._required)
        assert r.user_id == "u-1"
        assert r.type == "warning"
        assert r.msg_code is None
        assert r.params is None

    @pytest.mark.parametrize("missing", ["user_id", "type"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            NotifyUserDesktopRequest(**payload)

    def test_accepts_full(self):
        r = NotifyUserDesktopRequest(
            user_id="u-1",
            type="info",
            msg_code="shutdown_imminent",
            params={"minutes": 10},
        )
        assert r.params == {"minutes": 10}


class TestNotifyDesktopRequest:
    _required = {"desktop_id": "d-1", "type": "info"}

    def test_accepts_required(self):
        r = NotifyDesktopRequest(**self._required)
        assert r.desktop_id == "d-1"

    @pytest.mark.parametrize("missing", ["desktop_id", "type"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            NotifyDesktopRequest(**payload)


class TestDesktopQueueItem:
    def test_accepts_required(self):
        i = DesktopQueueItem(desktop_id="d-1")
        assert i.desktop_id == "d-1"

    def test_missing_desktop_id_rejected(self):
        with pytest.raises(ValidationError):
            DesktopQueueItem()


class TestSocketioEmitRequest:
    """All fields Optional — the service is responsible for rejecting
    payloads that omit `event`. Pin so the schema doesn't accidentally
    start enforcing requireds."""

    def test_accepts_empty(self):
        r = SocketioEmitRequest()
        assert r.event is None
        assert r.data is None
        assert r.namespace is None
        assert r.room is None

    def test_accepts_full(self):
        r = SocketioEmitRequest(
            event="foo",
            data={"a": 1},
            namespace="/admin",
            room="admins",
        )
        assert r.event == "foo"
        assert r.data == {"a": 1}

    def test_data_accepts_arbitrary(self):
        """data: Optional[Any] — pin that it accepts list, str, etc."""
        assert SocketioEmitRequest(data=[1, 2, 3]).data == [1, 2, 3]
        assert SocketioEmitRequest(data="hello").data == "hello"
