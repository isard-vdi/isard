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

Gated by the ``CHANGEHANDLER_TASK_RESULTS_ENABLED`` environment
variable so MR-1 ships dark by default and only the storage-worker
producer side runs in production. Operators flip the flag on staging
or in a canary to validate the dual-write before MR-2 promotes the
consumer to canonical.
"""

import asyncio
import logging as log
import uuid

import redis.asyncio as aioredis
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.models.task import Task
from redis.exceptions import ResponseError

from ..task_results.feedback import emit_task_feedback
from ..task_results.registry import HANDLERS

STREAM_KEY = "stream:task-results"
CONSUMER_GROUP = "change-handler"
READ_COUNT = 32
BLOCK_MS = 5000
RECONNECT_DELAY_S = 5


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
    """
    entry = HANDLERS.get(dep_task.task)
    if entry is None:
        log.debug(
            "task_results: no handler registered for %r (queue=%s, id=%s)",
            dep_task.task,
            getattr(dep_task, "queue", "?"),
            dep_task.id,
        )
        return
    handler, is_async = entry
    kwargs = dep_task.kwargs or {}
    try:
        if is_async:
            await handler(redis_manager, dep_task, **kwargs)
        else:
            await asyncio.to_thread(handler, dep_task, **kwargs)
    except Exception:
        log.exception(
            "task_results: handler %s failed for task %s",
            dep_task.task,
            dep_task.id,
        )


async def _process_entry(redis_manager, fields):
    """Dispatch one ``stream:task-results`` entry.

    Empty / malformed entries are logged and skipped — they still get
    ACKed by the caller so a poison message doesn't block the group.
    """
    kind = fields.get("kind") or fields.get(b"kind")
    task_id = fields.get("task_id") or fields.get(b"task_id")
    if isinstance(kind, bytes):
        kind = kind.decode()
    if isinstance(task_id, bytes):
        task_id = task_id.decode()
    if not task_id:
        log.warning("task_results: entry missing task_id: %r", fields)
        return
    if kind not in ("result", "progress"):
        log.warning("task_results: unknown kind=%r for task=%s", kind, task_id)
        return

    # Both kinds emit the task SocketIO event (chain dict). Only
    # ``result`` advances the chain by running core dependents.
    await emit_task_feedback(redis_manager, task_id)
    if kind != "result":
        return

    try:
        task = await asyncio.to_thread(Task, task_id)
    except Exception:
        log.exception(
            "task_results: failed to hydrate Task(%s) — dependents skipped",
            task_id,
        )
        return

    dependents = await asyncio.to_thread(lambda: list(_walk_core_dependents(task)))
    for dep_task in dependents:
        await _run_handler(redis_manager, dep_task)


async def _read_and_dispatch(redis, redis_manager, consumer_name):
    """One XREADGROUP+dispatch+XACK iteration.

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
            try:
                await _process_entry(redis_manager, fields)
            except Exception:
                log.exception("task_results: process_entry raised for %s", entry_id)
            try:
                await redis.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
            except Exception:
                log.exception("task_results: XACK failed for %s", entry_id)
    return True


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
            while True:
                await _read_and_dispatch(redis, redis_manager, consumer_name)
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
