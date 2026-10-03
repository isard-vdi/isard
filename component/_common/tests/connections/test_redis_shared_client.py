#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Redis clients reuse their connections and never probe for maintenance notifications."""

import pytest
from isardvdi_common.connections import redis_client
from isardvdi_common.connections.redis_blocking import blocking_client
from isardvdi_common.connections.redis_retry import RedisRetry

URL = "redis://:secret@redis.invalid:6379/0"


def _maint(client):
    return client.connection_pool.make_connection().maint_notifications_config


def test_the_same_arguments_get_the_same_client():
    assert redis_client.shared_client(URL) is redis_client.shared_client(URL)


def test_different_options_get_their_own_client():
    a = redis_client.shared_client(URL, socket_timeout=5)
    b = redis_client.shared_client(URL)
    assert a is not b
    assert a is redis_client.shared_client(URL, socket_timeout=5)


@pytest.mark.parametrize(
    "make",
    [
        lambda: redis_client.shared_client(URL),
        lambda: RedisRetry.from_url(URL),
        lambda: blocking_client(URL),
    ],
    ids=["shared", "rq-worker", "blocking"],
)
def test_no_client_probes_for_maintenance_notifications(make):
    config = _maint(make())
    assert config is None or config.enabled is False


class _FakeLock:
    def acquire(self):
        return True

    def release(self):
        pass


class _FakeClient:
    def __init__(self):
        self.closed = False

    def lock(self, *a, **k):
        return _FakeLock()

    def close(self):
        self.closed = True


def test_resource_lock_uses_the_shared_client_and_leaves_it_open(monkeypatch):
    from isardvdi_common.helpers import resource_lock

    client = _FakeClient()
    asked = []
    monkeypatch.setattr(
        resource_lock, "shared_client", lambda url, **k: asked.append(url) or client
    )
    monkeypatch.setattr(resource_lock, "rq_url", lambda: URL)

    for _ in range(2):
        with resource_lock.resource_lock("a", "b"):
            pass

    assert asked == [URL, URL]
    assert client.closed is False
