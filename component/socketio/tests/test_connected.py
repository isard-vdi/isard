import asyncio
from unittest import mock

import pytest
from isardvdi_common.lib.stats.connected import KEY_TTL_S, count_connected
from isardvdi_socketio.connected import Presence
from tests.fake_redis import FakeRedis

KEY = "socketio:connected:web-1"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def redis():
    return FakeRedis()


def test_counts_distinct_users_and_sockets(redis):
    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.add("sid-a", "user-1")
        await presence.add("sid-b", "user-1")
        await presence.add("sid-c", "user-2")
        assert count_connected(redis.sync()) == {"users": 2, "sockets": 3}
        await presence.remove("sid-a")
        assert count_connected(redis.sync()) == {"users": 2, "sockets": 2}
        await presence.remove("sid-c")
        assert count_connected(redis.sync()) == {"users": 1, "sockets": 1}

    _run(scenario())


def test_socket_without_user_counts_as_socket_only(redis):
    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.add("sid-a", None)
        assert count_connected(redis.sync()) == {"users": 0, "sockets": 1}

    _run(scenario())


def test_removing_an_unknown_sid_changes_nothing(redis):
    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.add("sid-a", "user-1")
        await presence.remove("sid-x")
        await presence.remove("sid-a")
        await presence.remove("sid-a")
        assert count_connected(redis.sync()) == {"users": 0, "sockets": 0}

    _run(scenario())


def test_start_clears_what_a_previous_run_left(redis):
    redis.hashes[KEY] = {"stale-1": "user-1", "stale-2": "user-2"}

    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.start()
        try:
            assert count_connected(redis.sync()) == {"users": 0, "sockets": 0}
            await presence.add("sid-a", "user-3")
            assert count_connected(redis.sync()) == {"users": 1, "sockets": 1}
        finally:
            await presence.stop()

    _run(scenario())


def test_every_write_sets_the_ttl_so_a_dead_process_expires(redis):
    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.add("sid-a", "user-1")
        assert redis.ttls[KEY] == KEY_TTL_S
        other = Presence(redis, key="socketio:connected:web-2")
        await other.add("sid-b", "user-2")
        redis.expire_now(KEY)
        assert count_connected(redis.sync()) == {"users": 1, "sockets": 1}

    _run(scenario())


def test_publish_restores_the_hash_after_redis_lost_it(redis):
    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.add("sid-a", "user-1")
        await presence.add("sid-b", "user-2")
        redis.hashes.clear()
        redis.ttls.clear()
        await presence.publish()
        assert count_connected(redis.sync()) == {"users": 2, "sockets": 2}
        assert redis.ttls[KEY] == KEY_TTL_S

    _run(scenario())


def test_heartbeat_republishes(redis, monkeypatch):
    monkeypatch.setattr("isardvdi_socketio.connected.HEARTBEAT_S", 0.01)

    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.start()
        try:
            await presence.add("sid-a", "user-1")
            redis.hashes.clear()
            await asyncio.sleep(0.05)
            assert count_connected(redis.sync()) == {"users": 1, "sockets": 1}
        finally:
            await presence.stop()
        assert KEY not in redis.hashes

    _run(scenario())


def test_redis_failure_does_not_raise(redis):
    redis.fail = True

    async def scenario():
        presence = Presence(redis, key=KEY)
        await presence.start()
        await presence.add("sid-a", "user-1")
        await presence.remove("sid-a")
        await presence.stop()

    _run(scenario())


def test_handlers_track_connections(pristine_module, monkeypatch, redis):
    presence = Presence(redis, key=KEY)
    monkeypatch.setattr(pristine_module, "presence", presence)
    fake_socketio = mock.MagicMock()
    fake_socketio.return_value.users_connect = mock.AsyncMock(
        side_effect=[True, True, False]
    )
    fake_socketio.return_value.quit_users_rooms = mock.AsyncMock(return_value={})
    monkeypatch.setattr(pristine_module, "SocketIO", fake_socketio)
    monkeypatch.setattr(
        pristine_module.Token,
        "get_token_payload",
        staticmethod(lambda jwt: {"user_id": jwt.removeprefix("jwt-")}),
    )

    async def scenario():
        m = pristine_module
        assert await m.connect("/userspace", "s1", {}, {"jwt": "jwt-u1"}) is True
        assert await m.connect("/administrators", "s2", {}, {"jwt": "jwt-u1"}) is True
        assert await m.connect("/userspace", "s3", {}, {"jwt": "jwt-u2"}) is False
        assert count_connected(redis.sync()) == {"users": 1, "sockets": 2}
        await m.disconnect("/userspace", "s1", "transport close")
        assert count_connected(redis.sync()) == {"users": 1, "sockets": 1}

    _run(scenario())


def test_asgi_lifespan_clears_on_startup_and_on_shutdown(pristine_module, redis):
    presence = pristine_module.presence
    key = presence.key
    presence.redis = redis
    redis.hashes[key] = {"stale": "user-1"}
    events = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
    sent = []

    async def receive():
        return next(events)

    async def send(message):
        if message["type"] == "lifespan.startup.complete":
            assert count_connected(redis.sync()) == {"users": 0, "sockets": 0}
            await presence.add("sid-a", "user-2")
        sent.append(message["type"])

    _run(pristine_module.app({"type": "lifespan"}, receive, send))
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
    assert key not in redis.hashes
