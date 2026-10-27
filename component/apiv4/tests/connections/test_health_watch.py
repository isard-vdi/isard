# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``async_watch_health_check`` — the apiv4 lifespan task that
re-syncs HAProxy maps whenever the ``haproxy-sync`` gRPC server recovers.

The watcher consumes the Health Checking Protocol's server-streaming
``Watch`` over a ``grpc.aio`` channel. The aio API is load-bearing, not a
style choice: the Go health server (``pkg/grpc/server.go``) pushes the
current status on subscribe and then only on each *change*, so a sync
iterator over the stream blocks in C for as long as the service stays
healthy — pinning the event loop thread and hanging ``uvicorn --reload``.
That was the bug these tests guard against.

``on_reconnect`` must fire exactly once per not-serving→serving
transition, and never on the first observation (startup already performs
the initial sync).

These tests drive a fake ``HealthStub`` and run the coroutine via
``asyncio.run`` — no pytest-asyncio config dependency, matching the
sibling sync tests in this directory. The infinite watch loop is
terminated by scripting a final sentinel ``_StopLoop`` (a
``BaseException``, so neither ``except`` clause in the watcher swallows
it), then asserting it propagates out.
"""

import asyncio
from unittest.mock import MagicMock

import grpc
import pytest
from api.connections.grpc_client import async_watch_health_check
from grpc_health.v1 import health_pb2

SERVICE = "haproxy_sync.v1.HaproxySyncService"


class _StopLoop(BaseException):
    """Sentinel that escapes the watcher's ``except`` clauses to end the
    otherwise-infinite watch loop deterministically."""


class _FakeRpcError(grpc.RpcError):
    """A ``grpc.RpcError`` with a usable ``code()`` — what the stream
    raises when ``haproxy-sync`` goes away (e.g. mid-restart). The real
    type is ``grpc.aio.AioRpcError``, which subclasses ``grpc.RpcError``;
    the watcher only ever touches ``code()``."""

    def code(self):
        return grpc.StatusCode.UNAVAILABLE


class _FakeStream:
    """Stands in for a ``grpc.aio`` ``UnaryStreamCall``: an async iterator
    over a scripted list of items, plus the ``cancel()`` the watcher calls
    to tear the RPC down.

    An item that is a ``BaseException`` is raised instead of yielded, so a
    script can end a stream with a connection drop or with the
    ``_StopLoop`` sentinel. Running out of items ends the stream cleanly.
    """

    def __init__(self, items):
        self._items = list(items)
        self.cancelled = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0)
        if not self._items:
            raise StopAsyncIteration
        item = self._items.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def cancel(self):
        self.cancelled = True


class _NeverYieldingStream(_FakeStream):
    """A stream that stays open forever without emitting — the steady
    state of a healthy service once the initial status has been sent."""

    def __init__(self):
        super().__init__([])
        self.started = asyncio.Event()

    async def __anext__(self):
        self.started.set()
        await asyncio.Event().wait()  # never resolves


def _serving():
    return MagicMock(status=health_pb2.HealthCheckResponse.SERVING)


def _not_serving():
    return MagicMock(status=health_pb2.HealthCheckResponse.NOT_SERVING)


def _patch_stub(monkeypatch, streams):
    """Point ``HealthStub`` at a fake whose ``Watch`` returns ``streams``
    in order — one entry per (re)subscription."""
    fake_stub = MagicMock()
    fake_stub.Watch = MagicMock(side_effect=streams)
    monkeypatch.setattr(
        "grpc_health.v1.health_pb2_grpc.HealthStub",
        lambda _channel: fake_stub,
    )
    return fake_stub


def _run_watcher(streams, monkeypatch):
    """Drive ``async_watch_health_check`` against a scripted sequence of
    streams, returning the ``on_reconnect`` mock so the caller can assert
    on its invocation count.

    The script must end with a ``_StopLoop`` so the loop terminates; the
    call asserts that sentinel propagates out.
    """
    _patch_stub(monkeypatch, streams)
    on_reconnect = MagicMock(name="on_reconnect")

    with pytest.raises(_StopLoop):
        asyncio.run(
            async_watch_health_check(
                MagicMock(name="channel"),
                SERVICE,
                on_reconnect,
                retry_interval=0,
            )
        )
    return on_reconnect


def test_reconnect_fires_once_on_stream_drop_and_recovery(monkeypatch):
    """SERVING → stream drops → SERVING again resyncs exactly once.

    Pins the core contract: ``on_reconnect`` fires only on the
    not-serving→serving edge, not on the initial SERVING observation, and
    a broken stream is treated as not-serving so the recovery that
    follows is detected — rather than resetting state and missing the edge.
    """
    on_reconnect = _run_watcher(
        [
            _FakeStream([_serving(), _FakeRpcError()]),
            _FakeStream([_serving(), _StopLoop()]),
        ],
        monkeypatch,
    )

    assert on_reconnect.call_count == 1


def test_no_resync_while_steady_serving(monkeypatch):
    """A service that reports SERVING on every push never triggers a
    resync — guards against re-running the (expensive) HAProxy map sync
    on redundant status pushes, and against firing on the very first
    observation at startup."""
    on_reconnect = _run_watcher(
        [_FakeStream([_serving(), _serving(), _serving(), _StopLoop()])],
        monkeypatch,
    )

    assert on_reconnect.call_count == 0


def test_no_resync_on_initial_not_serving_then_serving_is_reconnect(monkeypatch):
    """If the first status is NOT_SERVING (service still coming up), the
    first subsequent SERVING counts as a reconnect and resyncs once — the
    initial observation only ever records state, it never itself resyncs.
    """
    on_reconnect = _run_watcher(
        [_FakeStream([_not_serving(), _serving(), _StopLoop()])],
        monkeypatch,
    )

    assert on_reconnect.call_count == 1


def test_clean_stream_end_resubscribes_without_resync(monkeypatch):
    """A stream that ends without error (graceful server shutdown)
    re-subscribes rather than exiting — and, because the last observed
    status was SERVING, the next SERVING is not a transition and must not
    resync. The ``retry_interval`` sleep between subscriptions is what
    keeps this from becoming a tight re-subscribe loop."""
    on_reconnect = _run_watcher(
        [
            _FakeStream([_serving()]),
            _FakeStream([_serving(), _StopLoop()]),
        ],
        monkeypatch,
    )

    assert on_reconnect.call_count == 0


def test_cancelling_the_task_tears_down_the_stream(monkeypatch):
    """Cancelling the watcher task ends it and closes the open RPC.

    This is the regression guard for the event-loop-blocking bug: a
    watcher that iterated a *sync* ``Watch`` could never pass it, because
    a task blocked in C has no await point at which cancellation can be
    delivered — it would sit on the loop thread forever, exactly as it
    did in uvicorn.

    Cancellation (rather than a "the loop still runs" assertion) is the
    deterministic form of this check: against blocking code, a liveness
    assertion would hang the test suite instead of failing it.
    """
    stream = _NeverYieldingStream()
    _patch_stub(monkeypatch, [stream])

    async def _main():
        task = asyncio.create_task(
            async_watch_health_check(
                MagicMock(name="channel"),
                SERVICE,
                MagicMock(name="on_reconnect"),
                retry_interval=0,
            )
        )
        await asyncio.wait_for(stream.started.wait(), timeout=1)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_main())

    assert stream.cancelled is True
