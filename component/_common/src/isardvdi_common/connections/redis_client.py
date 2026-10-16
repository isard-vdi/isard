#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""One redis client per process, URL and options, for code that runs short commands."""

import threading
from typing import Any

import redis
from redis.maint_notifications import MaintNotificationsConfig

# CLIENT MAINT_NOTIFICATIONS is a Redis Enterprise command: plain Redis answers ERR on every connection.
NO_MAINT_NOTIFICATIONS = MaintNotificationsConfig(enabled=False)

_clients: dict[tuple, redis.Redis] = {}
_lock = threading.Lock()


def shared_client(url: str, **kwargs: Any) -> redis.Redis:
    """A client whose connection pool is reused by every caller with the same arguments."""
    key = (url, tuple(sorted(kwargs.items())))
    client = _clients.get(key)
    if client is None:
        with _lock:
            client = _clients.get(key)
            if client is None:
                kwargs.setdefault("maint_notifications_config", NO_MAINT_NOTIFICATIONS)
                client = redis.from_url(url, **kwargs)
                _clients[key] = client
    return client


def socketio_writer(url: str):
    """A write-only Socket.IO redis manager whose client does not probe either."""
    from socketio import RedisManager

    return RedisManager(
        url,
        write_only=True,
        redis_options={"maint_notifications_config": NO_MAINT_NOTIFICATIONS},
    )
