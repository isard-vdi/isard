# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``async_watch_health_check`` — the apiv4 lifespan task that
re-syncs HAProxy maps whenever the ``haproxy-sync`` gRPC server recovers.

The watcher polls the standard gRPC Health Checking Protocol's unary
``Check`` (not the streaming ``Watch``: a long-lived ``Watch`` stream
cannot carry a finite deadline and is torn down with RST_STREAM when the
deadline elapses — the original bug). ``on_reconnect`` must fire exactly
once per not-serving→serving transition, and never on the first
observation (startup already performs the initial sync).

These tests drive a fake ``HealthStub`` and run the coroutine to
completion via ``asyncio.run`` — no pytest-asyncio config dependency,
matching the sibling sync tests in this directory. The infinite poll loop
is terminated by scripting a final sentinel ``_StopLoop`` (a
``BaseException``, so neither ``except grpc.RpcError`` nor
``except Exception`` in the watcher swallows it) as the last ``Check``
result, then asserting it propagates out.
"""

import asyncio
from unittest.mock import MagicMock

import grpc
import pytest
from api.connections.grpc_client import async_watch_health_check
from grpc_health.v1 import health_pb2


class _StopLoop(BaseException):
    """Sentinel that escapes the watcher's ``except`` clauses to end the
    otherwise-infinite poll loop deterministically."""


class _FakeRpcError(grpc.RpcError):
    """A ``grpc.RpcError`` with a usable ``code()`` — what ``Check`` raises
    when ``haproxy-sync`` is unreachable (e.g. mid-restart)."""

    def code(self):
        return grpc.StatusCode.UNAVAILABLE


def _serving():
    return MagicMock(status=health_pb2.HealthCheckResponse.SERVING)


def _not_serving():
    return MagicMock(status=health_pb2.HealthCheckResponse.NOT_SERVING)


def _run_watcher(check_results, monkeypatch):
    """Drive ``async_watch_health_check`` against a fake stub whose ``Check``
    yields ``check_results`` in order, returning the ``on_reconnect`` mock so
    the caller can assert on its invocation count.

    ``check_results`` must end with a ``_StopLoop`` instance so the loop
    terminates; the call asserts that sentinel propagates out.
    """
    fake_stub = MagicMock()
    fake_stub.Check = MagicMock(side_effect=check_results)
    monkeypatch.setattr(
        "grpc_health.v1.health_pb2_grpc.HealthStub",
        lambda _channel: fake_stub,
    )

    on_reconnect = MagicMock(name="on_reconnect")

    with pytest.raises(_StopLoop):
        asyncio.run(
            async_watch_health_check(
                MagicMock(name="channel"),
                "haproxy_sync.v1.HaproxySyncService",
                on_reconnect,
                interval=0,
            )
        )
    return on_reconnect, fake_stub


def test_reconnect_fires_once_on_down_up_transition(monkeypatch):
    """SERVING → unreachable → SERVING resyncs exactly once.

    Pins the core contract: ``on_reconnect`` fires only on the
    not-serving→serving edge (the third poll here), not on the initial
    SERVING observation, and a transient ``RpcError`` is treated as
    not-serving so the subsequent recovery is detected — rather than
    resetting state and missing the edge (the secondary bug in the
    original ``Watch`` implementation).
    """
    on_reconnect, _ = _run_watcher(
        [
            _serving(),  # first observation — records state, must NOT resync
            _FakeRpcError(),  # server down — treated as not-serving
            _serving(),  # recovery — the one resync
            _StopLoop(),  # end the loop
        ],
        monkeypatch,
    )

    assert on_reconnect.call_count == 1


def test_no_resync_while_steady_serving(monkeypatch):
    """A service that is SERVING on every poll never triggers a resync —
    guards against re-running the (expensive) HAProxy map sync on every
    poll, and against firing on the very first observation at startup.
    """
    on_reconnect, _ = _run_watcher(
        [_serving(), _serving(), _serving(), _StopLoop()],
        monkeypatch,
    )

    assert on_reconnect.call_count == 0


def test_no_resync_on_initial_not_serving_then_serving_is_reconnect(monkeypatch):
    """If the very first poll is NOT_SERVING (service still coming up),
    the first subsequent SERVING counts as a reconnect and resyncs once —
    the initial observation only ever records state, it never itself
    resyncs.
    """
    on_reconnect, _ = _run_watcher(
        [
            _not_serving(),  # first observation — records not-serving
            _serving(),  # transition to serving — resync
            _StopLoop(),
        ],
        monkeypatch,
    )

    assert on_reconnect.call_count == 1
