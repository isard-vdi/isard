# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for the suites that assert on Redis's own behaviour.

What lives here asserts on rq's job graph (dependency sets, deferred
registries, ``Job.cancel``) or on the Lua ``ended_at`` stamp — things a mocked
connection cannot report without the mock becoming the thing under test. That
is why these are integration tests and not unit tests: they need the real
server, so they run against the stack's ``isard-redis`` like the rest of this
directory runs against the stack's apiv4.

They need Redis and nothing else — no apiv4, no auth, no socketio, no
hypervisor — so the session-wide stack fixtures of the parent conftest do not
apply. ``_cleanup_before_and_after`` is shadowed below for that reason.
"""

from __future__ import annotations

import os
import time
from typing import Iterator

import pytest

# Guards exclusive use of a scratch Redis db by one xdist worker at a time.
# The TTL is the crash hatch: a worker killed mid-test would otherwise wedge
# every later run on that db. The timeout is generous because a contending
# worker is waiting for a whole test, not a lock hold of a few milliseconds.
_SCRATCH_LOCK_KEY = "isard:test:chain-harness-lock"
_SCRATCH_LOCK_TTL_S = 300
_SCRATCH_LOCK_TIMEOUT_S = 120


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    """Shadow the parent's autouse fixture, which logs into apiv4.

    Same name as ``testing/integration/conftest.py`` so pytest resolves this
    one for everything under this directory. These suites create no apiv4
    objects, so there is nothing for the namespace cleanup to collect, and
    requiring an admin login would make them need the whole stack to assert on
    a Redis key.
    """
    yield


@pytest.fixture
def scratch_redis():
    """A real Redis on a scratch db, cleared around each test."""
    from ._chain_harness import scratch_connection

    connection = scratch_connection()
    if connection is None:
        pytest.fail(
            "no Redis reachable: these suites assert on the real server. "
            "They run on the stack network, where REDIS_HOST defaults to "
            "isard-redis; point REDIS_HOST/REDIS_PORT elsewhere to use another."
        )

    # Exclusive use of this db for the duration of the test. Each xdist worker
    # normally has a db to itself (see ``scratch_db``), so this lock is
    # uncontended — it exists for the case of more workers than the 15
    # available dbs, where two workers share one and would otherwise flush each
    # other's rq graph mid-test. Contending workers serialise instead.
    deadline = time.monotonic() + _SCRATCH_LOCK_TIMEOUT_S
    while not connection.set(
        _SCRATCH_LOCK_KEY, os.getpid(), nx=True, ex=_SCRATCH_LOCK_TTL_S
    ):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"scratch redis db busy for {_SCRATCH_LOCK_TIMEOUT_S}s; a "
                "previous run may have died holding the lock (it expires "
                f"after {_SCRATCH_LOCK_TTL_S}s)"
            )
        time.sleep(0.05)

    # The clear is INSIDE the lock: it is the thing that must not land in
    # another worker's test. It is NOT ``flushdb`` — that would delete the lock
    # we are holding and let the next worker in while this test still runs.
    lock_key = _SCRATCH_LOCK_KEY.encode()

    def clear_but_keep_the_lock():
        keys = [key for key in connection.scan_iter("*") if key != lock_key]
        if keys:
            connection.delete(*keys)

    clear_but_keep_the_lock()
    try:
        yield connection
    finally:
        clear_but_keep_the_lock()
        connection.delete(_SCRATCH_LOCK_KEY)


@pytest.fixture
def task_on_scratch_redis(scratch_redis):
    """Point every ``Task`` (and the ``CoreStep`` views it hands out) at the
    scratch db for the duration of the test."""
    import time as _time

    from isardvdi_common.lib import queue_coverage
    from isardvdi_common.models.task import Task

    original = Task.__dict__.get("_redis")
    Task._redis = scratch_redis
    # Date the fleet as seen just now: on a freshly flushed db every producer would
    # refuse for want of a consumer, and these tests are about the ordinary case.
    queue_coverage.note_fleet_seen(scratch_redis, _time.time())
    try:
        yield scratch_redis
    finally:
        if original is None:
            del Task._redis
        else:
            Task._redis = original
