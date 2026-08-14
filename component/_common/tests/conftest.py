# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared fixtures for the isardvdi_common suites."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def empty_redis():
    """Answer the task model's Redis reads without a server behind them.

    These are unit tests and the stage runs no Redis, but the code still asks:
    the cancel record, a key's existence, the cancel script. Every one of those
    fails open, so the suite passed anyway — it just spent redis-py's full
    retry budget, ten attempts with exponential backoff, on each call.

    Nothing is faked. An empty Redis answers exactly this: no cancel record, no
    key, no rows touched.
    """
    from isardvdi_common.connections.redis_base import RedisBase

    stub = MagicMock(name="empty-redis")
    stub.hget.return_value = None
    stub.exists.return_value = 0
    stub.eval.return_value = 0
    original = RedisBase._redis
    RedisBase._redis = stub
    try:
        yield stub
    finally:
        RedisBase._redis = original
