# SPDX-License-Identifier: AGPL-3.0-or-later

"""The invariant: a client that issues a blocking Redis read must give the
server strictly more time to answer than the block it asks for.

redis-py 8.0.0 changed ``DEFAULT_SOCKET_TIMEOUT`` from ``None`` to 5 s, and
``redis.from_url`` bypasses ``Redis.__init__``, so a read blocking 5000 ms
against a 5 s socket deadline loses every time: the deadline starts when the
client sends, the server's BLOCK timer only starts when it receives.
"""

import ast
import inspect

import pytest
import redis
import redis.asyncio as aioredis
from isardvdi_common.connections import redis_blocking
from isardvdi_common.connections.redis_retry import RedisRetry
from isardvdi_common.connections.redis_urls import rq_url
from rq import Worker

URL = "redis://:@isard-redis:6379/0"

# Headroom the policy must leave over any block, whatever value it picks.
MIN_MARGIN_S = 1.0

BLOCKING_READ_METHODS = frozenset(
    {
        "blmove",
        "blmpop",
        "blpop",
        "brpop",
        "bzpopmax",
        "bzpopmin",
        "xread",
        "xreadgroup",
    }
)


def effective_socket_timeout(client):
    """What redis-py will really put on the socket, not what we asked for."""
    return client.connection_pool.make_connection().socket_timeout


def blocking_reads(module):
    """``(lineno, block_node)`` per read that actually blocks server-side.

    ``block=None`` and a missing ``block=`` are the non-blocking forms of the
    same commands, and they carry no deadline to outlast.
    """
    found = []
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in BLOCKING_READ_METHODS:
            continue
        block = next((kw.value for kw in node.keywords if kw.arg == "block"), None)
        if block is None or (isinstance(block, ast.Constant) and block.value is None):
            continue
        found.append((node.lineno, block))
    return found


def from_url_calls(module):
    return [
        node.lineno
        for node in ast.walk(ast.parse(inspect.getsource(module)))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "from_url"
    ]


class TestPolicy:
    @pytest.mark.parametrize("block_ms", [1, 100, 5000, 30000, 405000])
    def test_socket_timeout_exceeds_the_block(self, block_ms):
        assert redis_blocking.socket_timeout_for(block_ms) > block_ms / 1000.0

    @pytest.mark.parametrize("block_ms", [1, 100, 5000, 30000, 405000])
    def test_the_margin_survives_a_round_trip(self, block_ms):
        margin = redis_blocking.socket_timeout_for(block_ms) - block_ms / 1000.0
        assert margin >= MIN_MARGIN_S

    def test_the_margin_is_a_constant_not_a_ratio(self):
        """A ratio would shrink to nothing for a short block and balloon for a
        long one; the round trip it has to cover does neither."""
        small = redis_blocking.socket_timeout_for(100) - 0.1
        large = redis_blocking.socket_timeout_for(405000) - 405.0
        assert small == pytest.approx(large)

    @pytest.mark.parametrize("block_ms", [0, -1, None])
    def test_a_non_blocking_read_is_refused(self, block_ms):
        with pytest.raises(ValueError):
            redis_blocking.socket_timeout_for(block_ms)


class TestFactories:
    """The effective value is read off a real ``Connection``, so a redis-py
    bump that ignores or overrides the kwarg fails here, not in production."""

    def test_sync_client_beats_its_block(self):
        client = redis_blocking.blocking_client(URL, block_ms=5000)
        assert effective_socket_timeout(client) > 5.0

    def test_async_client_beats_its_block(self):
        client = redis_blocking.async_blocking_client(URL, block_ms=5000)
        assert effective_socket_timeout(client) > 5.0

    @pytest.mark.parametrize("block_ms", [100, 5000, 405000])
    def test_the_effective_value_tracks_the_block_it_was_given(self, block_ms):
        client = redis_blocking.blocking_client(URL, block_ms=block_ms)
        assert effective_socket_timeout(client) > block_ms / 1000.0

    def test_connect_timeout_is_explicit(self):
        client = redis_blocking.blocking_client(URL, block_ms=5000)
        connection = client.connection_pool.make_connection()
        assert connection.socket_connect_timeout is not None

    def test_caller_kwargs_survive(self):
        client = redis_blocking.blocking_client(
            URL, block_ms=5000, decode_responses=True
        )
        assert client.connection_pool.connection_kwargs["decode_responses"] is True

    def test_a_caller_socket_timeout_below_the_block_is_refused(self):
        with pytest.raises(ValueError):
            redis_blocking.blocking_client(URL, block_ms=5000, socket_timeout=5)

    def test_a_caller_socket_timeout_above_the_block_is_honoured(self):
        client = redis_blocking.blocking_client(URL, block_ms=5000, socket_timeout=60)
        assert effective_socket_timeout(client) == 60


class TestRedisStreamConsumer:
    """The sync call site. Under redis-py 8 defaults this is exactly 5.0 vs 5.0."""

    def test_the_client_it_builds_outlives_its_own_block(self):
        from isardvdi_common.redis_stream import STREAM_BLOCK_MS, RedisStreamConsumer

        client = RedisStreamConsumer(streams=["stream:a"], group="g")._connect()
        assert effective_socket_timeout(client) > STREAM_BLOCK_MS / 1000.0

    def test_it_does_not_build_its_own_client(self):
        import isardvdi_common.redis_stream as module

        assert blocking_reads(module), "no blocking read left to protect"
        assert from_url_calls(module) == []

    def test_every_block_it_passes_is_a_named_constant(self):
        import isardvdi_common.redis_stream as module

        for lineno, block in blocking_reads(module):
            assert isinstance(block, ast.Name), f"literal block= at line {lineno}"
            assert block.id == "STREAM_BLOCK_MS", f"unknown block= at line {lineno}"


class TestRqWorkerDequeue:
    """BLPOP, via rq. rq repairs redis-py 8's default itself, but only through
    one clause of one ``if``; this fails here if a bump ever drops it."""

    @staticmethod
    def _worker(connection, name):
        return Worker(["invariant-probe"], connection=connection, name=name)

    def test_the_worker_connection_outlives_its_dequeue(self):
        connection = RedisRetry.from_url(rq_url())
        worker = self._worker(connection, "invariant-probe-retry")
        assert effective_socket_timeout(connection) > worker.dequeue_timeout

    def test_the_policy_would_cover_that_block_unaided(self):
        connection = redis.Redis.from_url(rq_url())
        worker = self._worker(connection, "invariant-probe-plain")
        block_ms = worker.dequeue_timeout * 1000
        assert redis_blocking.socket_timeout_for(block_ms) > worker.dequeue_timeout


class TestTheLibraryDefaultIsStillTheHazard:
    """Why the factory has to exist. If a future redis-py makes these fail, the
    fix is still right but the urgency changed, and that should be visible."""

    def test_a_bare_from_url_does_not_beat_a_5000ms_block(self):
        assert effective_socket_timeout(redis.from_url(URL)) <= 5.0

    def test_a_bare_async_from_url_does_not_beat_a_5000ms_block(self):
        assert effective_socket_timeout(aioredis.from_url(URL)) <= 5.0
