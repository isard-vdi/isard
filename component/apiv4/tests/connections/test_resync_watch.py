# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``async_watch_resync``, the lifespan task that resyncs HAProxy on request."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest
from api.connections import grpc_client
from api.connections.grpc_client import async_watch_resync


class _StopLoop(BaseException):
    """Escapes the watcher's ``except`` clauses to end its infinite loop."""


class _FakeRpcError(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.UNAVAILABLE


class _FakeStream:
    """An async iterator over scripted items; a ``BaseException`` item is raised."""

    def __init__(self, items):
        self._items = list(items)
        self.cancelled = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await _real_sleep(0)
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def cancel(self):
        self.cancelled = True


_real_sleep = asyncio.sleep


def _msg(reason, id=1):
    return MagicMock(reason=reason, id=id)


def _run(streams, monkeypatch, on_resync=None, ack=None):
    stub = MagicMock()
    stub.WatchResync = MagicMock(side_effect=streams)
    stub.AckResync = ack or AsyncMock()
    monkeypatch.setattr(
        grpc_client.haproxy_sync_pb2_grpc, "HaproxySyncServiceStub", lambda _c: stub
    )
    sleeps = []

    async def _sleep(delay):
        sleeps.append(delay)
        await _real_sleep(0)

    monkeypatch.setattr(grpc_client.asyncio, "sleep", _sleep)
    on_resync = on_resync or MagicMock(name="on_resync")

    with pytest.raises(_StopLoop):
        asyncio.run(async_watch_resync(MagicMock(name="channel"), on_resync))
    return on_resync, sleeps, stub


def test_every_message_triggers_a_resync_with_its_reason(monkeypatch):
    on_resync, _, _ = _run(
        [
            _FakeStream(
                [_msg("haproxy-sync started"), _msg("haproxy reload"), _StopLoop()]
            )
        ],
        monkeypatch,
    )

    assert [c.args[0] for c in on_resync.call_args_list] == [
        "haproxy-sync started",
        "haproxy reload",
    ]


def test_a_dropped_stream_is_reopened_and_keeps_serving(monkeypatch):
    on_resync, _, stub = _run(
        [
            _FakeStream([_msg("haproxy-sync started"), _FakeRpcError()]),
            _FakeStream([_msg("haproxy-sync started"), _StopLoop()]),
        ],
        monkeypatch,
    )

    assert stub.WatchResync.call_count == 2
    assert on_resync.call_count == 2


def test_backoff_grows_while_failing_and_resets_after_a_message(monkeypatch):
    _, sleeps, _ = _run(
        [
            _FakeRpcError(),
            _FakeRpcError(),
            _FakeStream([_msg("haproxy-sync started")]),
            _FakeStream([_StopLoop()]),
        ],
        monkeypatch,
    )

    assert sleeps == [1, 2, 1]


def test_a_failing_resync_does_not_stop_the_watcher(monkeypatch):
    on_resync = MagicMock(side_effect=[RuntimeError("rethinkdb down"), None])

    _run(
        [_FakeStream([_msg("haproxy reload"), _msg("haproxy reload"), _StopLoop()])],
        monkeypatch,
        on_resync,
    )

    assert on_resync.call_count == 2


def test_streams_are_cancelled_when_they_end(monkeypatch):
    first = _FakeStream([_msg("haproxy-sync started")])
    _run([first, _FakeStream([_StopLoop()])], monkeypatch)

    assert first.cancelled


def test_every_resync_reports_its_outcome(monkeypatch):
    on_resync = MagicMock(side_effect=[RuntimeError("rethinkdb down"), None])

    _, _, stub = _run(
        [
            _FakeStream(
                [_msg("haproxy reload", 7), _msg("haproxy reload", 8), _StopLoop()]
            )
        ],
        monkeypatch,
        on_resync,
    )

    acks = [c.args[0] for c in stub.AckResync.call_args_list]
    assert [(a.id, a.error) for a in acks] == [(7, "rethinkdb down"), (8, "")]


def test_a_failed_report_does_not_stop_the_stream(monkeypatch):
    on_resync, _, stub = _run(
        [
            _FakeStream(
                [_msg("haproxy reload", 1), _msg("haproxy reload", 2), _StopLoop()]
            )
        ],
        monkeypatch,
        ack=AsyncMock(side_effect=_FakeRpcError()),
    )

    assert stub.WatchResync.call_count == 1
    assert on_resync.call_count == 2
