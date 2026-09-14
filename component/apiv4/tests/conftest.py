# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures shared by every apiv4 suite, ``tests/routes`` and ``tests/services``
alike."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def empty_redis():
    """Answer the code's Redis reads like an empty Redis: no server runs in
    the unit suites, and without this each read burns redis-py's full retry
    budget against an unreachable host."""
    from isardvdi_common.connections.redis_base import RedisBase

    stub = MagicMock(name="empty-redis")
    stub.hget.return_value = None
    stub.exists.return_value = 0
    stub.eval.return_value = 0
    stub.zrevrange.return_value = []
    original = RedisBase._redis
    RedisBase._redis = stub
    try:
        yield stub
    finally:
        RedisBase._redis = original
