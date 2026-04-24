# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
import redis.exceptions as redis_err
import table_changefeed
from table_changefeed import TableChangefeed


class _FakeRedis:
    def __init__(self, publish_exc=None):
        self.published = []
        self._publish_exc = publish_exc

    async def publish(self, channel, payload):
        if self._publish_exc is not None:
            raise self._publish_exc
        self.published.append((channel, payload))

    async def xadd(self, *a, **kw):
        pass


class _BoomSubscriber:
    @staticmethod
    def serialize(_change):
        raise ValueError("schema drift: missing field `status`")


class _OkSubscriber:
    @staticmethod
    def serialize(_change):
        return b"payload"


@pytest.mark.asyncio
async def test_serialization_error_does_not_trigger_redis_reconnect(monkeypatch):
    redis = _FakeRedis()
    tcf = TableChangefeed(tables=[{"table": "domains"}], redis=redis)

    reconnect_calls = 0

    async def fake_reconnect():
        nonlocal reconnect_calls
        reconnect_calls += 1

    monkeypatch.setattr(tcf, "reconnect_redis", fake_reconnect)

    monkeypatch.setitem(
        table_changefeed.TABLE_TO_SUBSCRIBER,
        "domains",
        _BoomSubscriber,
    )

    change = {"new_val": {"table": "domains", "id": "x"}, "old_val": None}
    await tcf._publish_change(change)

    assert reconnect_calls == 0, "serialization failures must not reconnect Redis"
    assert (
        redis.published == []
    ), "serialization failures must not publish partial payloads"


@pytest.mark.asyncio
async def test_change_with_no_new_or_old_val_is_skipped(monkeypatch):
    redis = _FakeRedis()
    tcf = TableChangefeed(tables=[{"table": "domains"}], redis=redis)

    reconnect_calls = 0

    async def fake_reconnect():
        nonlocal reconnect_calls
        reconnect_calls += 1

    monkeypatch.setattr(tcf, "reconnect_redis", fake_reconnect)

    await tcf._publish_change({"new_val": None, "old_val": None})

    assert reconnect_calls == 0
    assert redis.published == []


@pytest.mark.asyncio
async def test_redis_connection_error_triggers_reconnect(monkeypatch):
    redis = _FakeRedis(publish_exc=redis_err.ConnectionError("boom"))
    tcf = TableChangefeed(tables=[{"table": "domains"}], redis=redis)

    reconnect_calls = 0

    async def fake_reconnect():
        nonlocal reconnect_calls
        reconnect_calls += 1

    monkeypatch.setattr(tcf, "reconnect_redis", fake_reconnect)

    monkeypatch.setitem(
        table_changefeed.TABLE_TO_SUBSCRIBER,
        "domains",
        _OkSubscriber,
    )

    change = {"new_val": {"table": "domains", "id": "x"}, "old_val": None}
    await tcf._publish_change(change)

    assert reconnect_calls == 1


@pytest.mark.asyncio
async def test_redis_timeout_error_triggers_reconnect(monkeypatch):
    redis = _FakeRedis(publish_exc=redis_err.TimeoutError("slow"))
    tcf = TableChangefeed(tables=[{"table": "domains"}], redis=redis)

    reconnect_calls = 0

    async def fake_reconnect():
        nonlocal reconnect_calls
        reconnect_calls += 1

    monkeypatch.setattr(tcf, "reconnect_redis", fake_reconnect)

    monkeypatch.setitem(
        table_changefeed.TABLE_TO_SUBSCRIBER,
        "domains",
        _OkSubscriber,
    )

    change = {"new_val": {"table": "domains", "id": "x"}, "old_val": None}
    await tcf._publish_change(change)

    assert reconnect_calls == 1
