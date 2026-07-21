#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Periodic producer of live queue position/ETA for WAITING storage tasks.

``emit_task_feedback`` only fires once a task runs (progress) or finishes
(result), so a task sitting *queued* pushes nothing — the user would see no
position until it starts. This sweep fills that gap: every few seconds it takes
the head-of-line queued storage tasks, estimates each, and emits a compact
``task`` event to the owning user's ``/userspace`` room, which the frontend task
handler maps onto the desktop card. It mirrors the engine's
``update_desktops_queue`` for the hypervisor-start queue.

Bounded by design: at most ``_MAX_PER_LANE`` jobs per lane, ``_MAX_LOADS`` Task
fetches and ``_MAX_EMITS`` emits per sweep (a cap hit is logged, not silent), one
batched storage-id lookup, and it only emits for a task that is genuinely
waiting. Each task is re-checked to be still queued immediately before emitting,
so a task that started/finished during the sweep never gets a stale ``queued``
event after its own terminal feedback. A failed sweep is logged and retried."""

import asyncio
import json
import logging as log

from isardvdi_common.lib import queue_estimate, queue_tiers
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.task import Task
from rq import Queue
from rq.job import Job

_INTERVAL = 12  # seconds between sweeps
_MAX_PER_LANE = 25  # only the head-of-line jobs matter for the position UX
_MAX_EMITS = 300  # hard cap on emit-worthy candidates per sweep
_MAX_LOADS = 600  # hard cap on Task fetches per sweep (bounds work even when
#                   most head-of-line jobs are filtered out, e.g. scheduler-owned)

_RQ_QUEUES_KEY = "rq:queues"
_RQ_QUEUE_PREFIX = "rq:queue:"


def _dec(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _storage_lanes(conn):
    lanes = []
    for raw in conn.smembers(_RQ_QUEUES_KEY) or []:
        name = _dec(raw)
        if name.startswith(_RQ_QUEUE_PREFIX):
            name = name[len(_RQ_QUEUE_PREFIX) :]
        if queue_tiers.parse_storage_queue(name):
            lanes.append(name)
    return lanes


def _still_queued(conn, task_id):
    """True while the task is still sitting in its queue (position not None);
    False once it has started / finished / vanished. Used to drop a stale
    ``queued`` position that would otherwise land after the task's terminal
    feedback event. On any error, treat as not-queued so we never emit stale."""
    try:
        return Job.fetch(task_id, connection=conn).get_position() is not None
    except Exception:
        return False


def _collect(conn):
    """Bounded sweep of head-of-line queued storage tasks -> ``[(user_id,
    payload), ...]``. Sync (run in a thread); never raises."""
    candidates = []
    loads = 0
    truncated = False
    try:
        lanes = _storage_lanes(conn)
    except Exception:
        return []
    for lane in lanes:
        if loads >= _MAX_LOADS or len(candidates) >= _MAX_EMITS:
            truncated = True
            break
        try:
            job_ids = Queue(lane, connection=conn).get_job_ids(0, _MAX_PER_LANE - 1)
        except Exception:
            continue
        for job_id in job_ids:
            if loads >= _MAX_LOADS or len(candidates) >= _MAX_EMITS:
                truncated = True
                break
            try:
                task = Task(job_id)
            except Exception:
                continue
            loads += 1
            user_id = getattr(task, "user_id", None)
            if not user_id or user_id == "isard-scheduler":
                continue
            est = queue_estimate.estimate_task(task, conn)
            # Inform only about a task that is actually waiting (queued with a
            # position) or confidently stranded; skip running/finished ones.
            if est.get("effective_position") is None and not est.get("stranded"):
                continue
            candidates.append((task.id, user_id, est))

    if truncated:
        # Never silent: an operator can see the sweep capped and that some
        # waiting tasks get their position on a later sweep instead.
        log.info(
            "storage_queue_producer: sweep hit cap (%d loads, %d candidates); "
            "remaining waiting tasks get their position next sweep",
            loads,
            len(candidates),
        )

    # One batched task_id -> storage_id lookup for the whole sweep.
    storage_by_task = {}
    if candidates:
        try:
            for row in Storage.get_storage_ids_from_task_ids(
                [task_id for task_id, _, _ in candidates]
            ):
                storage_by_task[row["task_id"]] = row["storage_id"]
        except Exception:
            storage_by_task = {}

    out = []
    for task_id, user_id, est in candidates:
        storage_id = storage_by_task.get(task_id)
        if not storage_id:
            continue  # without it the frontend cannot map the task to a card
        out.append(
            (
                user_id,
                {
                    "id": task_id,
                    "storage_id": storage_id,
                    "status": "queued",
                    "pending": True,
                    **est,
                },
            )
        )
    return out


async def run(redis_manager, interval_s=_INTERVAL):
    """Sweep loop: push the live estimate of waiting storage tasks to owners."""
    from isardvdi_common.connections.redis_base import RedisBase

    conn = RedisBase._redis
    while True:
        try:
            items = await asyncio.to_thread(_collect, conn)
            for user_id, payload in items:
                # Re-check right before emit: the task may have started/finished
                # during the sweep's storage lookup, in which case its own
                # feedback event already settled the card — do not overwrite it
                # with a stale 'queued'.
                if not await asyncio.to_thread(_still_queued, conn, payload["id"]):
                    continue
                await redis_manager.emit(
                    "task",
                    json.dumps(payload),
                    namespace="/userspace",
                    room=user_id,
                )
        except Exception:
            log.exception("storage_queue_producer: sweep failed")
        await asyncio.sleep(interval_s)
