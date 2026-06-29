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

"""Periodic self-heal for storage / download task chains.

change-handler is the sole executor of the ``core``-queue tail of every
storage chain (see :mod:`task_results_consumer`). If a core handler raises,
the consumer logs it but the dependent storage-queue job is never released and
the row never finalizes: the storage stays ``maintenance``, the domain stays
``Downloading`` and the dependent RQ job stays **DEFERRED forever**.
``Task.pending`` then reports the whole chain as pending indefinitely, so the
``storage_pending_task`` 428 guard blocks template-creation / downloads /
deletes on that storage with no recovery anywhere.

This module runs two idempotent passes on a timer (plus one eager pass on
startup):

**Pass 1 — orphaned DEFERRED jobs.** A DEFERRED job whose dependencies are all
terminal (finished/failed/canceled) and have been terminal longer than a grace
window is an orphan no worker will ever run. The grace window is what keeps the
pass from racing the consumer's own release path. For a ``core``-queue orphan
we re-run exactly what the consumer would have (run handler → mark FINISHED/
FAILED → release storage dependents → delete the dead core job), which also
drives its own core dependents. For a storage-queue orphan whose parents all
finished we release it so the storage worker picks it up; if a parent
failed/canceled we cancel it (releasing its dependents for failure handling).

**Pass 2 — storages stuck in ``maintenance`` whose backing task is dead.** When
the orphan job is gone entirely (e.g. cleaned up) the row can be left stuck with
no task to replay. Finalize from the row's own ``qemu-img-info``: a valid disk
(``virtual-size > 0``) becomes ``ready`` via the canonical
:func:`_apply_storage_update` (which only promotes the safe
``_DOMAIN_PRE_READY_STATUSES`` set — a running VM is never yanked); otherwise we
re-issue ``check_backing_chain`` for an authoritative recheck. A storage whose
task is still alive is left untouched.
"""

import asyncio
import logging as log
from datetime import datetime, timezone

from isardvdi_common.models.storage import Storage
from isardvdi_common.models.task import Task
from rq.job import JobStatus

from ..task_results.storage import _apply_storage_update, send_status_socket
from .task_results_consumer import (
    _release_storage_dependents,
    _run_handler,
    _set_job_status,
    _walk_core_dependents,
)

GRACE_S = 120
RECONCILE_EVERY_S = 90

_TERMINAL = (
    JobStatus.FINISHED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.STOPPED,
)


def _as_aware_utc(dt):
    """Normalise an RQ ``ended_at`` (naive or aware) to aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _deps_terminal_and_aged(task, now, grace_s):
    """True if every dependency is terminal AND the most recent one ended
    longer than ``grace_s`` ago.

    A DEFERRED job with no dependencies, a non-terminal dependency, or a
    dependency whose ``ended_at`` we cannot read is treated as NOT an orphan —
    we only ever act on chains we can prove are dead and settled, never on one
    the consumer might still be about to release.
    """
    deps = task.dependencies
    if not deps:
        return False
    newest = None
    for dep in deps:
        if dep.job_status not in _TERMINAL:
            return False
        ended = _as_aware_utc(getattr(dep.job, "ended_at", None))
        if ended is None:
            return False
        if newest is None or ended > newest:
            newest = ended
    return (now - newest).total_seconds() >= grace_s


async def _release_via_parents(task):
    """Release a storage-queue orphan by re-running ``enqueue_dependents`` on
    each finished parent, pushing the orphan DEFERRED → QUEUED so the storage
    worker runs it. Reuses the same mechanism the consumer's
    :func:`_release_storage_dependents` relies on, applied here to the parent.
    """
    import redis
    from isardvdi_common.connections.redis_urls import rq_url
    from rq import Queue

    try:
        conn = redis.from_url(rq_url())
        queue = Queue(connection=conn)
        for parent in task.dependencies:
            await asyncio.to_thread(queue.enqueue_dependents, parent.job)
    except Exception:
        log.exception(
            "reconcile: failed to release storage orphan %s via parents",
            getattr(task, "id", "?"),
        )


async def _heal_core_orphan(redis_manager, task):
    """Re-run the missed core dispatch for ``task`` and its nested core
    dependents, mirroring :func:`_process_entry` in the consumer.
    """
    chain = [task] + list(_walk_core_dependents(task))
    for dep_task in chain:
        ok = await _run_handler(redis_manager, dep_task)
        await _set_job_status(dep_task, JobStatus.FINISHED if ok else JobStatus.FAILED)
        if ok:
            await _release_storage_dependents(dep_task)
    for dep_task in chain:
        try:
            await asyncio.to_thread(dep_task.job.delete)
        except Exception:
            log.exception(
                "reconcile: could not delete healed core orphan %s",
                getattr(dep_task, "id", "?"),
            )
    return 1


async def _heal_storage_orphan(task):
    """Heal a storage-queue orphan: release it if every parent finished, else
    cancel it (a failed parent means the op failed; cancelling releases its
    dependents so their failure handling runs)."""
    any_failed = any(
        dep.job_status in (JobStatus.FAILED, JobStatus.CANCELED)
        for dep in task.dependencies
    )
    if any_failed:
        try:
            await asyncio.to_thread(lambda: task.job.cancel(enqueue_dependents=True))
        except Exception:
            log.exception(
                "reconcile: could not cancel storage orphan %s",
                getattr(task, "id", "?"),
            )
        return 1
    await _release_via_parents(task)
    return 1


async def _reconcile_orphan_deferred(redis_manager, now=None, grace_s=GRACE_S):
    """Pass 1: heal orphaned DEFERRED jobs. Returns the count healed."""
    now = now or datetime.now(timezone.utc)
    try:
        deferred = await asyncio.to_thread(Task.get_by_status, JobStatus.DEFERRED.value)
    except Exception:
        log.exception("reconcile: could not list DEFERRED tasks")
        return 0
    healed = 0
    for task in deferred:
        try:
            if not _deps_terminal_and_aged(task, now, grace_s):
                continue
            queue = getattr(task, "queue", "") or ""
            if queue.startswith("core"):
                healed += await _heal_core_orphan(redis_manager, task)
            else:
                healed += await _heal_storage_orphan(task)
        except Exception:
            log.exception(
                "reconcile: orphan heal failed for %s", getattr(task, "id", "?")
            )
    if healed:
        log.warning("reconcile: healed %s orphaned DEFERRED task(s)", healed)
    return healed


def _task_alive(storage):
    """True if the storage's backing task still exists and is pending — in
    which case Pass 1 / the consumer will finalize it and Pass 2 must not
    interfere."""
    task_id = storage.task
    if not task_id or not Task.exists(task_id):
        return False
    try:
        return Task(task_id).pending
    except Exception:
        return False


async def _finalize_stuck_storage(redis_manager, storage):
    """Finalize one stuck ``maintenance`` storage from its on-disk reality.

    Valid disk (``qemu-img-info.virtual-size > 0``) → ``ready`` via the
    canonical handler; otherwise re-issue ``check_backing_chain`` for an
    authoritative recheck (which drives the row to ready/deleted through the
    normal path). Returns 1 only when finalized in place.
    """
    qemu_img_info = getattr(storage, "qemu-img-info", None)
    virtual_size = 0
    if isinstance(qemu_img_info, dict):
        virtual_size = qemu_img_info.get("virtual-size", 0) or 0
    if virtual_size > 0:
        _apply_storage_update({"id": storage.id, "status": "ready"})
        await send_status_socket(
            redis_manager, storage.id, "ready", getattr(storage, "user_id", None)
        )
        log.warning(
            "reconcile: finalized stuck storage %s (maintenance → ready)",
            storage.id,
        )
        return 1
    try:
        storage.check_backing_chain(user_id=getattr(storage, "user_id", None))
        log.warning(
            "reconcile: stuck storage %s has no valid disk info; re-issued "
            "check_backing_chain",
            storage.id,
        )
    except Exception:
        log.exception(
            "reconcile: could not re-issue check_backing_chain for %s",
            storage.id,
        )
    return 0


async def _reconcile_stuck_storage(redis_manager):
    """Pass 2: finalize storages stuck in ``maintenance`` whose task is dead.
    Returns the count finalized."""
    try:
        stuck = await asyncio.to_thread(Storage.get_index, ["maintenance"], "status")
    except Exception:
        log.exception("reconcile: could not list maintenance storages")
        return 0
    healed = 0
    for storage in stuck:
        try:
            if _task_alive(storage):
                continue
            healed += await _finalize_stuck_storage(redis_manager, storage)
        except Exception:
            log.exception(
                "reconcile: finalize failed for storage %s",
                getattr(storage, "id", "?"),
            )
    return healed


async def run(redis_manager, interval_s=RECONCILE_EVERY_S, grace_s=GRACE_S):
    """Long-running reconcile loop: an eager pass on startup, then both passes
    every ``interval_s`` seconds. Started alongside the changefeed listener and
    the task-results consumer in :func:`__main__.main`.

    Each pass swallows its own errors, so a transient Redis/DB hiccup never
    kills the loop — the next tick simply retries.
    """
    log.warning(
        "reconcile: self-heal starting (every %ss, grace %ss)", interval_s, grace_s
    )
    while True:
        try:
            await _reconcile_orphan_deferred(redis_manager, grace_s=grace_s)
            await _reconcile_stuck_storage(redis_manager)
        except Exception:
            log.exception("reconcile: pass raised")
        await asyncio.sleep(interval_s)
