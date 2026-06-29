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

"""Asyncio consumer for the ``stream:task-results`` Redis stream.

Coexists with the existing rethinkdb-changes pub/sub listener in
``__main__.listen_to_redis``. Both are launched via ``asyncio.gather``
so the existing changefeed-driven SocketIO fan-out keeps emitting per
table change exactly as today; this consumer only handles the new
storage-worker → change-handler bridge.

Started unconditionally from ``__main__.main`` — this consumer is the
canonical executor of the chain-handler bodies that used to live on
isard-core_worker.
"""

import asyncio
import logging as log
import time
import uuid

import redis
import redis.asyncio as aioredis
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.models.task import Task
from redis.exceptions import ResponseError
from rq import Queue
from rq.job import JobStatus

from ..task_results.feedback import emit_task_feedback
from ..task_results.registry import HANDLERS

STREAM_KEY = "stream:task-results"
CONSUMER_GROUP = "change-handler"
READ_COUNT = 32
BLOCK_MS = 5000
RECONNECT_DELAY_S = 5

# At-least-once recovery: an entry whose handler failed is left in the
# consumer group's Pending Entries List instead of being ACKed, so a later
# ``XAUTOCLAIM`` re-delivers it. A poison entry (one that fails every time —
# e.g. a malformed payload) is dead-lettered after ``MAX_DELIVERIES`` so it
# can never loop forever.
DEAD_STREAM = "stream:task-results:dead"
RECLAIM_IDLE_MS = 60000
RECLAIM_EVERY_S = 30
MAX_DELIVERIES = 5


async def _ensure_consumer_group(redis):
    """Create the consumer group if it doesn't yet exist.

    Uses ``MKSTREAM`` so first-boot scenarios (storage worker hasn't
    published yet) don't fail. ``BUSYGROUP`` is the normal "already
    exists" response and is swallowed.
    """
    try:
        await redis.xgroup_create(
            name=STREAM_KEY,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        log.info("task_results: created consumer group %r", CONSUMER_GROUP)
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def _walk_core_dependents(task):
    """Yield every dependent (recursively) whose RQ queue starts with
    ``core``. Dependents on storage queues are skipped — the storage
    worker will publish its own stream event when each finishes, which
    drives a separate dispatch.
    """
    for dep in task.dependents:
        try:
            queue = dep.queue
        except Exception:
            continue
        if queue and queue.startswith("core"):
            yield dep
            yield from _walk_core_dependents(dep)


async def _run_handler(redis_manager, dep_task):
    """Resolve and invoke the registered handler for ``dep_task``.

    Sync handlers run via ``asyncio.to_thread`` so the event loop
    stays responsive while rethink writes happen. Async handlers
    receive the SocketIO :class:`AsyncRedisManager` as their first
    argument (they emit ``storage`` SocketIO events alongside writes).

    Returns ``True`` if the handler ran to completion (or no handler is
    registered for ``dep_task.task`` — treated as a clean no-op), and
    ``False`` if the handler raised. Callers propagate this forward to
    ``Job.set_status`` so downstream handlers' ``depending_status`` reads
    reflect the real outcome.
    """
    entry = HANDLERS.get(dep_task.task)
    if entry is None:
        log.debug(
            "task_results: no handler registered for %r (queue=%s, id=%s)",
            dep_task.task,
            getattr(dep_task, "queue", "?"),
            dep_task.id,
        )
        return True
    handler, is_async = entry
    kwargs = dep_task.kwargs or {}
    try:
        if is_async:
            await handler(redis_manager, dep_task, **kwargs)
        else:
            await asyncio.to_thread(handler, dep_task, **kwargs)
        return True
    except Exception:
        log.exception(
            "task_results: handler %s failed for task %s",
            dep_task.task,
            dep_task.id,
        )
        return False


async def _release_storage_dependents(dep_task):
    """Push every non-``core`` dependent of ``dep_task`` from DEFERRED to
    QUEUED, mirroring what RQ's ``Worker._handle_job_success`` would do
    after a real worker finished a job.

    Background: ``_walk_core_dependents`` deliberately stops at the
    storage-queue boundary because the storage worker publishes its own
    ``stream:task-results`` entry per task and will drive a fresh
    dispatch. But for the worker to RUN the storage-queue dependent it
    has to be QUEUED, not DEFERRED. RQ's normal release path lives in
    ``Worker._handle_job_success`` and never runs for ``core``-queue
    parents — no worker pops the ``core`` queue. Without an explicit
    release, the next-stage storage Job sits DEFERRED forever and the
    chain dies at the ``storage -> core -> storage`` hand-off.

    Affects every chain that bounces back to a storage queue after a
    ``core`` handler (today: only
    ``Storage.enqueue_template_creation_chain_from_desktop`` — the first
    chain with that topology).

    ``Queue.enqueue_dependents`` works on the parent: for each dependent
    it removes the parent id from the dependent's dependencies set and
    pushes the dependent to its own origin queue if no other parent is
    still pending. Core-queue dependents end up QUEUED on ``core`` —
    harmless, since the walker still yields and handles them in-process
    and the trailing ``job.delete`` loop drops them after dispatch.
    """
    try:
        children = await asyncio.to_thread(lambda: list(dep_task.dependents))
    except Exception:
        log.exception(
            "task_results: could not enumerate dependents of %s for release",
            getattr(dep_task, "id", "?"),
        )
        return
    has_storage_child = any(
        getattr(child, "queue", "") and not child.queue.startswith("core")
        for child in children
    )
    if not has_storage_child:
        return
    try:
        conn = redis.from_url(rq_url())
        # ``Queue(...)`` here is just the gateway to ``enqueue_dependents``
        # — the method routes each dependent to its OWN ``origin`` queue,
        # so the queue name we pass is irrelevant beyond construction.
        queue = Queue(connection=conn)
        await asyncio.to_thread(queue.enqueue_dependents, dep_task.job)
    except Exception:
        log.exception(
            "task_results: failed to release storage dependents of %s",
            getattr(dep_task, "id", "?"),
        )


async def _set_job_status(dep_task, status):
    """Best-effort RQ ``Job.set_status`` wrapper.

    isard-core_worker used to mark each chain step's RQ Job ``FINISHED``
    (or ``FAILED``) before RQ released the next dependent, which is what
    ``task.depending_status`` reads. With change-handler as the sole
    executor we must do that transition ourselves between in-process
    dispatches — otherwise sibling/child handlers see the parent as
    ``deferred``/``queued`` and the gate
    ``if task.depending_status == "finished"`` always fails, silently
    breaking 17 of 18 chains in the registry.
    """
    try:
        await asyncio.to_thread(dep_task.job.set_status, status)
    except Exception:
        log.exception(
            "task_results: could not mark %s as %s",
            getattr(dep_task, "id", "?"),
            status,
        )


async def _process_entry(redis_manager, fields):
    """Dispatch one ``stream:task-results`` entry.

    Returns ``True`` when the entry was fully handled (so the caller may
    ACK it) and ``False`` when it must be retried — a handler raised or the
    Task could not be hydrated. Malformed / non-``result`` entries return
    ``True``: there is nothing to retry, so they are ACKed and dropped.
    """
    kind = fields.get("kind") or fields.get(b"kind")
    task_id = fields.get("task_id") or fields.get(b"task_id")
    if isinstance(kind, bytes):
        kind = kind.decode()
    if isinstance(task_id, bytes):
        task_id = task_id.decode()
    if not task_id:
        log.warning("task_results: entry missing task_id: %r", fields)
        return True
    if kind not in ("result", "progress"):
        log.warning("task_results: unknown kind=%r for task=%s", kind, task_id)
        return True

    # Both kinds emit the task SocketIO event (chain dict). Only
    # ``result`` advances the chain by running core dependents.
    await emit_task_feedback(redis_manager, task_id)
    if kind != "result":
        return True

    try:
        task = await asyncio.to_thread(Task, task_id)
    except Exception:
        log.exception(
            "task_results: failed to hydrate Task(%s) — will retry",
            task_id,
        )
        return False

    # The storage worker publishes the stream event from within the
    # wrapped task function, *before* RQ's own post-perform code marks
    # the Job FINISHED. Marking it ourselves here closes that race so
    # the first direct dependent reads ``depending_status="finished"``.
    await _set_job_status(task, JobStatus.FINISHED)

    dependents = await asyncio.to_thread(lambda: list(_walk_core_dependents(task)))
    all_ok = True
    for dep_task in dependents:
        ok = await _run_handler(redis_manager, dep_task)
        all_ok = all_ok and ok
        # Propagate the outcome onto this dep's RQ Job before the next
        # sibling/child runs, so handlers that gate on
        # ``task.depending_status`` see the right value (was "deferred"
        # otherwise — no worker on the core queue ever marks it).
        await _set_job_status(dep_task, JobStatus.FINISHED if ok else JobStatus.FAILED)
        # Release any deferred storage-queue dependent of this core dep so
        # the storage worker actually picks it up. See helper docstring
        # for why ``set_status(FINISHED)`` alone is not enough. Skipped
        # when the handler failed — failure must NOT advance the chain.
        if ok:
            await _release_storage_dependents(dep_task)

    # MR-3 of the core_worker retirement: core_worker is gone, so the
    # ``core`` queue has no consumer. RQ would otherwise move each
    # dependent Job from DEFERRED to QUEUED when its storage parent
    # completes, and the Job would sit on the queue forever. Now that
    # change-handler is the sole executor, drop the Job objects after
    # the in-process handlers have run. Done after the dispatch loop
    # (not inline) so the recursive ``Task.dependents`` walk still
    # finds nested dependents via each parent's ``meta["dependent_ids"]``.
    #
    # ONLY drop them when the whole entry succeeded. On a partial failure
    # the Jobs are kept so a later ``XAUTOCLAIM`` redelivery can re-walk
    # the chain and re-run the failed handler (every handler is an
    # idempotent upsert, so re-running the ones that already succeeded is
    # safe). Deleting them here would make the redelivery a no-op and
    # leave the chain wedged.
    if all_ok:
        for dep_task in dependents:
            try:
                await asyncio.to_thread(dep_task.job.delete)
            except Exception:
                log.exception(
                    "task_results: failed to drop RQ Job %s after dispatch",
                    dep_task.id,
                )
    return all_ok


async def _ack(redis, entry_id):
    try:
        await redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
    except Exception:
        log.exception("task_results: XACK failed for %s", entry_id)


async def _read_and_dispatch(redis, redis_manager, consumer_name):
    """One XREADGROUP+dispatch+XACK iteration.

    The entry is ACKed only when :func:`_process_entry` reports success. A
    handler failure (or a raise) leaves the entry in the group's Pending
    Entries List so :func:`_reclaim_pending` re-delivers it later. The
    per-entry ``try`` keeps one bad entry from stalling the rest of the batch.

    Returns ``True`` if any entries were processed (so the caller can
    skip the block-and-wait next iteration), ``False`` otherwise.
    """
    response = await redis.xreadgroup(
        groupname=CONSUMER_GROUP,
        consumername=consumer_name,
        streams={STREAM_KEY: ">"},
        count=READ_COUNT,
        block=BLOCK_MS,
    )
    if not response:
        return False
    for _stream, entries in response:
        for entry_id, fields in entries:
            ok = False
            try:
                ok = await _process_entry(redis_manager, fields)
            except Exception:
                log.exception("task_results: process_entry raised for %s", entry_id)
            if ok:
                await _ack(redis, entry_id)
    return True


async def _delivery_count(redis, entry_id):
    """How many times this PEL entry has been delivered (redis increments it
    on every XREADGROUP / XCLAIM / XAUTOCLAIM). 0 if it can't be read."""
    try:
        pending = await redis.xpending_range(
            STREAM_KEY, CONSUMER_GROUP, min=entry_id, max=entry_id, count=1
        )
        if pending:
            return int(pending[0]["times_delivered"])
    except Exception:
        log.exception("task_results: xpending_range failed for %s", entry_id)
    return 0


async def _reclaim_pending(redis, redis_manager, consumer_name):
    """Re-deliver entries that have been stuck in the PEL longer than
    ``RECLAIM_IDLE_MS`` (a previous delivery failed and was never ACKed).

    Each reclaimed entry is re-dispatched and ACKed on success; one that has
    already been delivered more than ``MAX_DELIVERIES`` times is moved to the
    dead-letter stream and ACKed, so a poison entry can never loop forever.
    """
    try:
        response = await redis.xautoclaim(
            STREAM_KEY,
            CONSUMER_GROUP,
            consumer_name,
            min_idle_time=RECLAIM_IDLE_MS,
            count=READ_COUNT,
        )
    except Exception:
        log.exception("task_results: xautoclaim failed")
        return
    # redis-py returns [cursor, [(id, fields), ...]] (older) or
    # [cursor, [...], [deleted_ids]] (redis >= 7). We only need the entries.
    entries = response[1] if len(response) >= 2 else []
    for entry_id, fields in entries:
        if not fields:
            # Entry no longer in the stream (trimmed); drop it from the PEL.
            await _ack(redis, entry_id)
            continue
        delivered = await _delivery_count(redis, entry_id)
        if delivered > MAX_DELIVERIES:
            try:
                await redis.xadd(DEAD_STREAM, fields)
                await _ack(redis, entry_id)
                log.warning(
                    "task_results: dead-lettered %s after %s deliveries",
                    entry_id,
                    delivered,
                )
            except Exception:
                log.exception("task_results: dead-letter failed for %s", entry_id)
            continue
        ok = False
        try:
            ok = await _process_entry(redis_manager, fields)
        except Exception:
            log.exception("task_results: reclaim process_entry raised for %s", entry_id)
        if ok:
            await _ack(redis, entry_id)


async def run(redis_manager):
    """Long-running consumer entrypoint.

    Loops forever, reconnecting on any Redis error with a short
    backoff. Designed to be started alongside ``listen_to_redis`` via
    ``asyncio.gather`` in ``__main__``.
    """
    consumer_name = f"change-handler-{uuid.uuid4()}"
    log.warning("task_results: stream consumer starting as %s", consumer_name)
    while True:
        redis = None
        try:
            redis = aioredis.from_url(rq_url(), decode_responses=True)
            await redis.ping()
            await _ensure_consumer_group(redis)
            log.warning(
                "task_results: connected to %s; reading group=%s",
                STREAM_KEY,
                CONSUMER_GROUP,
            )
            last_reclaim = time.monotonic()
            while True:
                await _read_and_dispatch(redis, redis_manager, consumer_name)
                # Periodically sweep the PEL so an entry whose handler failed
                # (and was therefore not ACKed) gets retried, and a poison
                # entry is dead-lettered rather than retried forever.
                if time.monotonic() - last_reclaim >= RECLAIM_EVERY_S:
                    await _reclaim_pending(redis, redis_manager, consumer_name)
                    last_reclaim = time.monotonic()
        except Exception as e:
            log.warning("task_results: stream consumer error: %s", e)
        finally:
            if redis is not None:
                try:
                    await redis.aclose()
                except Exception:
                    pass
        log.warning("task_results: reconnecting in %ss", RECONNECT_DELAY_S)
        await asyncio.sleep(RECONNECT_DELAY_S)
