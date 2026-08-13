#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cluster-wide advisory mutex for check-then-write critical sections.

RethinkDB gives us atomicity *per document*, which is enough for a state
transition on one row (see ``StorageMigrationItem.claim``) but not for the shape
this module exists to protect: **read several rows, decide, then write a new
one**. The booking subsystem is full of that shape -- "does any plan overlap this
card? no -> insert" / "is there room left for this profile? yes -> insert the
booking" -- and no single conditional write can express it, because the decision
spans rows that do not exist yet.

So the exclusion has to live outside the data. The pattern is already in the
repo (``lib/storage/migration_run.advance``): a redis lease, taken for the
duration of the section, keyed by the resource it protects. This module
generalises it so the callers stop hand-rolling one each.

Two properties the callers depend on:

* **Per-resource, never global.** ``resource_lock`` takes the key(s) of the
  resource actually contended -- a GPU card, a vGPU profile, a user's booking
  quota. Two admins planning two different cards never meet. Serialising the
  whole planner instead would trade a rare corruption for a permanent queue.
* **Fail closed.** An unreachable redis raises rather than running the section
  unprotected. A capacity guard that silently stops guarding when its lock
  backend is down is worse than no guard at all: it is a guard nobody can point
  at. (Same reasoning as the fail-open admission gate the queue audit filed as a
  defect.)

Multiple keys are acquired in sorted order and re-entry on a key this thread
already holds is a no-op, so a nested critical section (``enable_subitem`` ->
``recompute_total_units``) can neither deadlock against a sibling nor against
itself -- redis-py locks are not reentrant on their own.
"""

import logging as log
import threading
from contextlib import contextmanager
from typing import Iterator

from isardvdi_common.connections.redis_urls import rq_url
from redis import Redis
from redis.exceptions import RedisError

# How long a lease outlives the holder. A crashed/killed worker must not wedge a
# card forever, so the lease expires on its own; the value sits well above the
# worst-case section (a handful of indexed rethink queries) so a live holder is
# never evicted mid-section.
LOCK_TTL = 30

# How long a caller queues behind the holder before giving up. Contention here is
# two admins clicking at once, not sustained load: waiting is the RIGHT answer
# (the loser then runs the overlap check against the winner's row and gets its
# honest 409), and the ceiling only exists so a wedged holder cannot pile up
# requests until the TTL clears it.
LOCK_WAIT = 20

# Bound on redis calls so a STALLED (not down) server surfaces as an error
# instead of hanging the request while its lease quietly lapses.
_SOCKET_TIMEOUT = 5

_held = threading.local()


def _held_keys() -> set:
    """Keys this thread already holds, for the re-entrancy no-op."""
    keys = getattr(_held, "keys", None)
    if keys is None:
        keys = set()
        _held.keys = keys
    return keys


@contextmanager
def resource_lock(
    *keys: str, ttl: int = LOCK_TTL, wait: float = LOCK_WAIT
) -> Iterator[None]:
    """Hold an exclusive lease on every named resource for the block's duration.

    Args:
        keys: resource names, e.g. ``"gpus:plan:<card_id>"``. Order is
            irrelevant -- they are always taken in sorted order, so two callers
            asking for the same set from opposite directions cannot deadlock.
            Keys this thread already holds are skipped (re-entrant).
        ttl: seconds the lease survives a holder that dies inside the section.
        wait: seconds to queue behind a current holder before giving up.

    Raises:
        Error: ``too_many_requests`` (429) when the lease could not be taken
            within ``wait`` -- retryable, the resource is genuinely busy.
            ``internal_server`` (500) when redis itself is unreachable, so the
            guarded section never runs unguarded.
    """
    from isardvdi_common.helpers.error_factory import Error

    held = _held_keys()
    wanted = sorted({key for key in keys if key not in held})
    if not wanted:
        yield
        return

    conn = Redis.from_url(
        rq_url(), socket_timeout=_SOCKET_TIMEOUT, socket_connect_timeout=_SOCKET_TIMEOUT
    )
    acquired = []
    try:
        for key in wanted:
            lock = conn.lock(
                f"lock:{key}",
                timeout=ttl,
                blocking_timeout=wait,
                # The token is thread-local, so acquire and release must happen
                # in this thread -- they do, both are in this function.
                thread_local=True,
            )
            try:
                got = lock.acquire()
            except RedisError as exc:
                raise Error(
                    "internal_server",
                    f"Could not reach the lock service for {key} ({type(exc).__name__})",
                    description_code="lock_unavailable",
                )
            if not got:
                raise Error(
                    "too_many_requests",
                    f"{key} is busy being modified by another request, retry",
                    description_code="resource_busy",
                )
            acquired.append(lock)
            held.add(key)
        yield
    finally:
        for lock in reversed(acquired):
            try:
                lock.release()
            except RedisError:
                # The lease lapsed and may already have been re-taken: releasing
                # it would steal someone else's. Nothing to do but say so -- a
                # section that outran its TTL ran (partly) unprotected.
                log.warning(
                    "resource_lock: lease %s was already gone at release; the "
                    "critical section outran its %ss TTL",
                    lock.name,
                    ttl,
                )
        for key in wanted:
            held.discard(key)
        try:
            conn.close()
        except RedisError:
            pass
