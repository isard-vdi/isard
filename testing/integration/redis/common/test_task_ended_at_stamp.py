# SPDX-License-Identifier: AGPL-3.0-or-later

"""``ended_at`` stamp semantics, proved against a real redis.

The stamp runs as a Lua script, so a mocked connection cannot tell us whether
it actually writes — which is why these live here rather than beside the rest
of the ``Task.cancel()`` chain-closure tests: what they assert on is the
server's behaviour, not our use of it. The empty-field trap below was found by
running it for real.

Never the rq db: these write fixed ``rq:job:test-stamp-*`` keys, and a test has
no business writing into the db real jobs live in.
"""

from __future__ import annotations

import os

import pytest
import redis as redis_lib


def _redis():
    """The one criterion for "is there a real Redis here", shared with every
    other suite that needs one: an explicit ``ISARD_TEST_REDIS`` if set,
    otherwise the server the rest of the stack is configured against.

    The connect timeout keeps an unresolvable host from becoming a hung job.
    """
    url = os.environ.get("ISARD_TEST_REDIS")
    if url:
        connection = redis_lib.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    else:
        connection = redis_lib.Redis(
            host=os.environ.get("REDIS_HOST") or "isard-redis",
            port=int(os.environ.get("REDIS_PORT") or 6379),
            password=os.environ.get("REDIS_PASSWORD", ""),
            db=int(os.environ.get("TASK_CHAIN_TEST_REDIS_DB", "9")),
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    assert (
        connection.get_connection_kwargs().get("db") != 0
    ), "refusing to run against the rq db"
    try:
        connection.ping()
    except Exception as error:
        pytest.fail(f"no Redis for the real-redis stamp tests: {error}")
    return connection


class TestEndedAtStampSemantics:
    def test_stamps_when_the_field_is_empty(self):
        """RQ serialises an unset ``ended_at`` as an EMPTY field, not a missing
        one — a plain ``HSETNX`` writes nothing and the chain can never age."""
        from isardvdi_common.models.task import _stamp_ended_at

        conn = _redis()
        key = "rq:job:test-stamp-empty"
        conn.delete(key)
        conn.hset(key, mapping={"status": "canceled", "ended_at": ""})

        _stamp_ended_at(conn, "test-stamp-empty")

        assert conn.hget(key, "ended_at") not in (b"", None)
        conn.delete(key)

    def test_does_not_overwrite_a_real_timestamp(self):
        from isardvdi_common.models.task import _stamp_ended_at

        conn = _redis()
        key = "rq:job:test-stamp-keep"
        conn.delete(key)
        conn.hset(
            key, mapping={"status": "finished", "ended_at": "2020-01-01T00:00:00Z"}
        )

        _stamp_ended_at(conn, "test-stamp-keep")

        assert conn.hget(key, "ended_at") == b"2020-01-01T00:00:00Z"
        conn.delete(key)

    def test_does_not_resurrect_a_deleted_job(self):
        """A concurrently-deleted job must not come back as a status-only ghost
        hash — those poison every chain walk that meets them."""
        from isardvdi_common.models.task import _stamp_ended_at

        conn = _redis()
        key = "rq:job:test-stamp-gone"
        conn.delete(key)

        _stamp_ended_at(conn, "test-stamp-gone")

        assert conn.exists(key) == 0
