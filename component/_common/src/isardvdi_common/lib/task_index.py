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

"""Per-owner task index: the tasks a storage or media row has had.

A ZSET per owner, member = rq job id, score = when the job was enqueued. It
lives in the same store as the jobs it names, so the reference cannot outlive
what it points at the way the ``task`` row field does.

Pruned by RANK, never by clock. ``EXPIRE`` is per key, so every new task on a
busy disk refreshes it and a member outlives its own job by however long the
disk stays busy. Capping to the newest ``INDEX_CAP`` and dropping ids whose job
is gone on read makes a dangling member structurally impossible, and introduces
no new clock into a subsystem that already has four.

Writes are pipelined: the cost is then one round trip regardless of how many
owners a task names, which matters because a task may legitimately name several
(a convert destination has no tasks of its own and resolves through its origin;
a parked template row names the chain that will unpark it).
"""

import logging
import time

log = logging.getLogger(__name__)

STORAGE = "storage"
MEDIA = "media"

# Redis' own documented default, used only when the server will not answer.
_DEFAULT_LISTPACK_MAX = 128

# Resolved once per process: a CONFIG GET on every index write would double the
# cost of a write that is otherwise a single round trip.
_cap = None


def index_cap(connection):
    """How many task ids to keep per owner: one BELOW the listpack threshold.

    Deliberately not a round number, and deliberately not the threshold itself.
    Redis keeps a ZSET as a listpack until it grows past
    ``zset-max-listpack-entries`` and then converts it to a skiplist, which
    roughly doubles the bytes per member — and it never converts back. Each
    write here ZADDs before it trims, so a set capped *at* the threshold
    momentarily holds one member too many and is converted permanently, cap or
    no cap. Measured on a live server under this exact write pattern:

        cap=128  ->  128 members, skiplist,  126.4 B/member
        cap=127  ->  127 members, listpack,   65.1 B/member

    Read from the running server rather than assumed, because the threshold is
    tunable and an install that moved it should get a cap that still tracks
    where its own encoding flips.
    """
    global _cap
    if _cap is not None:
        return _cap
    threshold = _DEFAULT_LISTPACK_MAX
    try:
        configured = int(
            (connection.config_get("zset-max-listpack-entries") or {}).get(
                "zset-max-listpack-entries", _DEFAULT_LISTPACK_MAX
            )
        )
        if configured > 0:
            threshold = configured
    except Exception:
        log.debug("task index: server would not report its listpack threshold")
    _cap = max(1, threshold - 1)
    return _cap


def index_key(kind, owner_id):
    """The ZSET key holding ``owner_id``'s task ids."""
    return f"{kind}:{owner_id}:tasks"


def job_score(job):
    """When the job entered the system.

    Public because the v204 backfill scores the pointers it carries across with
    the same rule: a second definition would rank seeded entries against live
    ones by a different clock.

    ``enqueued_at`` is only set once the job reaches its queue, so a job built
    with ``enqueue=False`` — the create/register/enqueue ordering the recycle
    bin needs — falls back to ``created_at``.
    """
    for attr in ("enqueued_at", "created_at"):
        moment = getattr(job, attr, None)
        if moment is not None:
            try:
                return moment.timestamp()
            except Exception:
                pass
    return time.time()


def index_task(connection, job, owner_ids, kind=STORAGE):
    """Record ``job`` against every owner in ``owner_ids``, newest-capped.

    Never raises: this is bookkeeping beside the task, and a redis blip must
    not fail the operation the user actually asked for.
    """
    owners = [owner_id for owner_id in (owner_ids or []) if owner_id]
    if not owners:
        return
    try:
        score = job_score(job)
        cap = index_cap(connection)
        pipe = connection.pipeline(transaction=False)
        for owner_id in owners:
            key = index_key(kind, owner_id)
            pipe.zadd(key, {job.id: score})
            pipe.zremrangebyrank(key, 0, -(cap + 1))
        pipe.execute()
    except Exception:
        log.warning(
            "task index: could not index %s under %s",
            getattr(job, "id", "?"),
            owners,
            exc_info=True,
        )


def current_task_id(connection, owner_id, kind=STORAGE):
    """The task ``owner_id`` is busy with right now, or ``None``.

    The primitive that replaces the row's scalar ``task`` field. It answers the
    newest member whose job still EXISTS, not simply the newest: the scalar
    could name a job that had long expired, which is why every one of its
    readers already had to pair it with an existence check.

    Reads the index newest-first and proves liveness in one pipelined batch,
    stopping at the first survivor — so the common case (the newest member is
    alive) costs two round trips regardless of how much history the row has.
    Unlike :func:`owner_task_ids` this does not prune what it finds dead: it is
    on the task-creation path, and a listing pass reclaims those anyway.

    Answers ``None`` on any redis failure rather than raising: a reader asking
    "is this row busy" must not turn a blip into a failed operation.
    """
    key = index_key(kind, owner_id)
    try:
        members = [
            member.decode() if isinstance(member, bytes) else member
            for member in connection.zrevrange(key, 0, -1)
        ]
        if not members:
            return None
        pipe = connection.pipeline(transaction=False)
        for job_id in members:
            pipe.exists(f"rq:job:{job_id}")
        for job_id, alive in zip(members, pipe.execute()):
            if alive:
                return job_id
        return None
    except Exception:
        log.warning("task index: could not read %s", key, exc_info=True)
        return None


def owner_task_ids(connection, owner_id, kind=STORAGE):
    """``owner_id``'s task ids, newest first, proven to still exist.

    Members whose job rq has since dropped are removed from the answer AND
    from the index — the lazy half of "dangling is impossible". The liveness
    check is one pipelined sweep: per-member round trips make a full index cost
    an order of magnitude more.
    """
    key = index_key(kind, owner_id)
    try:
        members = [
            member.decode() if isinstance(member, bytes) else member
            for member in connection.zrevrange(key, 0, -1)
        ]
        if not members:
            return []
        pipe = connection.pipeline(transaction=False)
        for job_id in members:
            pipe.exists(f"rq:job:{job_id}")
        alive = pipe.execute()
        dangling = [job_id for job_id, exists in zip(members, alive) if not exists]
        if dangling:
            connection.zrem(key, *dangling)
        return [job_id for job_id, exists in zip(members, alive) if exists]
    except Exception:
        log.warning("task index: could not read %s", key, exc_info=True)
        return []
