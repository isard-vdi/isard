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

IDEMPOTENCY INVARIANT (load-bearing — read before adding a handler)
------------------------------------------------------------------
Delivery is **at-least-once**: a handler that raises leaves its entry in the
Pending Entries List, and ``_reclaim_pending`` re-delivers it (up to
``MAX_DELIVERIES`` times) — so the WHOLE chain of finalize handlers for that
entry can run again. **Every finalize handler MUST therefore be idempotent**:
an ``init_document`` upsert or a guarded delete, never a blind increment,
append, or "create if first time" side effect. RQ Job objects are dropped only
on a fully-successful pass, so a partial failure preserves chain state for a
clean replay. The only deliberately non-idempotent effect is the
fire-and-forget ``storage`` status socket; a redelivery re-emit is harmless
(the frontend is idempotent to status), and intra-pass repeats are collapsed
by ``dedup_status_emits`` — but a *new* non-idempotent DB write here would
corrupt on replay.
"""

import asyncio
import logging as log
import time
import uuid

import redis
import redis.asyncio as aioredis
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.helpers.task_streams import CANCELED_KIND
from isardvdi_common.models.task import (
    _TERMINAL_STATUSES,
    CoreStep,
    Task,
    _stamp_ended_at,
    was_canceled,
)
from redis.exceptions import ResponseError
from rq import Queue
from rq.job import JobStatus

from ..task_results.feedback import emit_task_feedback
from ..task_results.migration import send_migration_socket
from ..task_results.registry import HANDLERS
from ..task_results.storage import dedup_status_emits
from .trim import PROGRESS_STREAM, RESULT_STREAM, compute_trim_floor

STREAM_KEY = RESULT_STREAM
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
# Nothing consumes the dead-letter stream, so an uncapped XADD grows for ever.
# It is a forensic record, not a queue: keep a bounded, recent window.
DEAD_STREAM_MAXLEN = 10000
RECLAIM_IDLE_MS = 60000
RECLAIM_EVERY_S = 30
MAX_DELIVERIES = 5

# Consumer-driven MINID trim (stopgap ①): periodically trim the result
# stream down to the read+ACK frontier so an unread completion can NEVER be
# trimmed before it is delivered. Replaces the producer's tight approximate
# MAXLEN (which discarded unread ``kind=result`` entries under a burst).
TRIM_EVERY_S = 5


async def _ensure_consumer_group(redis, stream=STREAM_KEY):
    """Create the consumer group on ``stream`` if it doesn't yet exist.

    Uses ``MKSTREAM`` so first-boot scenarios (storage worker hasn't
    published yet) don't fail. ``BUSYGROUP`` is the normal "already
    exists" response and is swallowed.
    """
    try:
        await redis.xgroup_create(
            name=stream,
            groupname=CONSUMER_GROUP,
            id="0",
            mkstream=True,
        )
        log.info(
            "task_results: created consumer group %r on %s", CONSUMER_GROUP, stream
        )
    except ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise


def _is_canceled(task):
    """True when this chain member is cancelled."""
    try:
        return task.job_status == JobStatus.CANCELED
    except Exception:
        return False


def _is_settled(task):
    """True when this chain member will never run again.

    A settled storage member is one a dead chain may be walked THROUGH: it has
    no further event of its own to drive a dispatch, so anything the chain
    declared behind it is reachable only from here.
    """
    try:
        return task.job_status in (
            JobStatus.FINISHED,
            JobStatus.FAILED,
            JobStatus.STOPPED,
            JobStatus.CANCELED,
        )
    except Exception:
        return False


def _walk_dependents(task, dead_chain):
    """This member's dependents, plus — on a dead chain — the finalize steps of
    knot children that will now never be built.

    ``dead_chain`` is the status the chain died with (``CANCELED`` / ``FAILED``)
    or ``None`` while it is still succeeding, so the steps behind a child that
    will never exist report the right reason rather than just "not finished".

    A knot child is created when its finalize step runs, and only while the
    chain is still succeeding. On a failed or cancelled chain it is never
    created, so everything the chain declared below it is unreachable as a job
    and reachable only as the metadata it already is. See
    ``CoreStep.unbuilt_knot_steps``.
    """
    dependents = list(task.dependents)
    if dead_chain and isinstance(task, CoreStep):
        dependents.extend(task.unbuilt_knot_steps(dead_chain))
    return dependents


def _walk_core_dependents(
    task, include_canceled_storage=False, dead_chain=False, _visited=None
):
    """Yield every dependent (recursively) whose RQ queue starts with
    ``core``. Dependents on storage queues are skipped — the storage
    worker will publish its own stream event when each finishes, which
    drives a separate dispatch.

    ``include_canceled_storage`` lifts that boundary for CANCELLED storage
    members only: a cancelled job never publishes a result, so the core
    finalizers sitting behind it are reachable only by recursing through it.
    The member itself is still not yielded — there is no handler for a
    storage task.

    ``dead_chain`` lifts it for any SETTLED storage member. A chain cancelled
    half way has finished members between the root and the cancelled one, and
    refusing to walk past them leaves everything below the cancel unreachable —
    a cancelled template creation is then announced and nothing settles its
    rows. Walking THROUGH a finished member does not touch its history: it is
    not yielded, so no handler runs for it and no status of its is rewritten.
    Traversal and mutation are different things, and only traversal happens
    here.

    ``_visited`` guards against a malformed/cyclic ``meta`` graph, which would
    otherwise recurse until the stack blows.
    """
    if _visited is None:
        _visited = set()
    for dep in _walk_dependents(task, dead_chain):
        try:
            queue = dep.queue
        except Exception:
            continue
        dep_id = getattr(dep, "id", None)
        if dep_id is not None:
            if dep_id in _visited:
                continue
            _visited.add(dep_id)
        if queue and queue.startswith("core"):
            yield dep
            yield from _walk_core_dependents(
                dep, include_canceled_storage, dead_chain, _visited
            )
        elif (include_canceled_storage and _is_canceled(dep)) or (
            dead_chain and _is_settled(dep)
        ):
            yield from _walk_core_dependents(
                dep, include_canceled_storage, dead_chain, _visited
            )


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
    after a real worker finished a job. Metadata dispatch enqueues its knot
    children fresh instead; this now serves only the reconcile heal of a
    residual legacy ``core`` orphan (:func:`reconcile._heal_core_orphan`).

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


async def _enqueue_metadata_storage_dependents(step):
    """Metadata-mode :func:`_release_storage_dependents`: a storage-under-core
    knot has no DEFERRED rq job to promote, so enqueue each storage child carried
    on the finalize step as a fresh ``Task``. The job id is deterministic and
    guarded by an existence check, so a redelivery does not duplicate the disk op
    (the one non-idempotent effect here).

    Returns ``False`` if any child failed to enqueue, so the caller leaves the
    entry unACKed for an idempotent redelivery (the exists-guard dedups) instead
    of silently stranding the knot — a stranded storage sits at ``non_existing``,
    which the transitional reconcile does not scan.
    """
    children = getattr(step, "storage_dependents", []) or []
    child_ids = step.knot_child_ids
    anchor = step.anchor
    ok = True
    for index, child in enumerate(children):
        child = dict(child)
        # The id the chain already declared for this child when it was built —
        # never recomputed here, so the creator and every reader of the graph
        # cannot drift into two names for one member.
        child_id = child_ids[index]
        job_kwargs = dict(child.get("job_kwargs") or {})
        job_kwargs["id"] = child_id
        # The other half of the edge. Without it the child has no dependency
        # inside the closure, so it reads as a second ROOT of its own chain:
        # ``Task.cancel`` would announce the cancel twice and the whole finalize
        # chain would be dispatched twice. It also gives the child a
        # ``depending_status`` and lets the orphan rule in ``Task.pending``
        # retire it once the anchor has settled.
        if anchor is not None:
            meta = dict(job_kwargs.get("meta") or {})
            meta.setdefault("dependency_ids", [anchor.id])
            job_kwargs["meta"] = meta
        child["job_kwargs"] = job_kwargs
        try:
            if await asyncio.to_thread(Task.exists, child_id):
                continue
            await asyncio.to_thread(lambda c=child: Task(**c))
        except Exception:
            ok = False
            log.exception(
                "task_results: failed to enqueue metadata storage dependent %s of %s",
                child_id,
                getattr(step, "id", "?"),
            )
    return ok


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

    Cancellation is terminal and wins over everything: a late worker event, a
    redelivery or a reconcile heal must never flip a CANCELED job to
    FINISHED, or the handlers deeper in the chain would read
    ``depending_status == "finished"`` and run their success bodies for an
    operation the user cancelled.
    """
    try:
        if await asyncio.to_thread(dep_task.job.get_status, refresh=True) == (
            JobStatus.CANCELED
        ):
            log.debug(
                "task_results: %s is canceled, not marking it %s",
                getattr(dep_task, "id", "?"),
                status,
            )
            return
    except Exception:
        # Unreadable status: fall through to the write, as before.
        pass
    try:
        await asyncio.to_thread(dep_task.job.set_status, status)
        # ``set_status`` writes one hash field, so a step settled here has no
        # ``ended_at`` - and the reconcile ages a chain from exactly that. Any
        # storage job stranded behind such a step was invisible to the orphan
        # pass for ever. Safe now that the pass no longer hydrates the queued
        # backlog and no longer deletes replay state on a failed heal.
        await asyncio.to_thread(_stamp_ended_at, dep_task._redis, dep_task.id)
    except Exception:
        log.exception(
            "task_results: could not mark %s as %s",
            getattr(dep_task, "id", "?"),
            status,
        )


def _record_service_time(task):
    """Fold the finished root task's wall-clock into the per-(tier, action)
    service-time EWMA (queue_estimate) that powers ETA. Best-effort; a failure
    here must never disrupt result processing."""
    try:
        from isardvdi_common.lib import queue_estimate, queue_tiers

        parsed = queue_tiers.parse_storage_queue(task.queue)
        if not parsed:
            return
        job = task.job
        started = getattr(job, "started_at", None)
        ended = getattr(job, "ended_at", None)
        if started is None or ended is None:
            return
        queue_estimate.record_service_time(
            task._redis, parsed[2], task.task, (ended - started).total_seconds()
        )
    except Exception:
        return


async def _process_entry(redis_manager, fields):
    """Dispatch one ``stream:task-results`` entry.

    Returns ``True`` when the entry was fully handled (so the caller may
    ACK it) and ``False`` when it must be retried — a handler raised or the
    Task could not be hydrated. Malformed / non-``result`` entries return
    ``True``: there is nothing to retry, so they are ACKed and dropped.
    """
    kind = fields.get("kind") or fields.get(b"kind")
    task_id = fields.get("task_id") or fields.get(b"task_id")
    job_status = fields.get("job_status") or fields.get(b"job_status")
    if isinstance(kind, bytes):
        kind = kind.decode()
    if isinstance(task_id, bytes):
        task_id = task_id.decode()
    if isinstance(job_status, bytes):
        job_status = job_status.decode()

    # Migration progress events carry a migration_id (no task_id): the
    # reconciler XADDs them so the admin storage-pools view live-updates.
    if kind == "migration":
        migration_id = fields.get("migration_id") or fields.get(b"migration_id")
        if isinstance(migration_id, bytes):
            migration_id = migration_id.decode()
        if migration_id:
            await send_migration_socket(redis_manager, migration_id)
        else:
            log.warning(
                "task_results: migration entry missing migration_id: %r", fields
            )
        return True

    if not task_id:
        log.warning("task_results: entry missing task_id: %r", fields)
        return True
    if kind not in ("result", "progress", CANCELED_KIND):
        log.warning("task_results: unknown kind=%r for task=%s", kind, task_id)
        return True

    # Every kind emits the task SocketIO event (chain dict) — including a
    # cancel, so the frontend stops showing the operation as running. Only
    # ``result`` and ``canceled`` advance the chain by running core dependents.
    await emit_task_feedback(redis_manager, task_id)
    if kind == "progress":
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
    # the Job. Marking it ourselves here closes that race so the first
    # direct dependent reads the right ``depending_status``.
    #
    # HONOUR the event's ``job_status``: the worker decorator publishes
    # ``job_status="failed"`` when the task body raised (a real error OR a
    # running-cancel, which surfaces as a raise) and ``"finished"`` when it
    # returned. A root-terminal chain — convert / delete / virt_win_reg,
    # whose trailing ``update_status`` keys off THIS root's status — must see
    # ``failed`` on a failed/cancelled op so it takes the cleanup branch
    # instead of the success branch (which would mark a half-written disk
    # ready or drop a storage row whose delete never completed). A missing
    # field defaults to FINISHED, preserving the legacy race-closing
    # behaviour for finished chains.
    # A cancelled chain is announced by ``Task.cancel`` itself, not by a
    # worker: every member is already CANCELED (or legitimately terminal for a
    # mid-chain cancel), so the root's status must be left exactly as it is.
    canceled = kind == CANCELED_KIND or job_status == "canceled"
    # A member a worker had already dequeued runs to completion even once it is
    # cancelled, and the worker's success handler rewrites its status — so this
    # event can say "finished" for work the user cancelled, and nothing in the
    # job itself contradicts it. Consult the record the cancel left instead.
    # Absence means not cancelled, so a chain from before the record existed
    # takes exactly the path it takes today.
    if not canceled and await asyncio.to_thread(was_canceled, task._redis, task_id):
        log.warning(
            "task_results: %s completed after being cancelled; "
            "settling the chain as cancelled rather than advancing it",
            task_id,
        )
        canceled = True
    # A chain that failed or was cancelled did not produce its work. Its
    # finalize handlers still run - that is how the row is released - but
    # nothing downstream of them may be advanced.
    chain_failed = canceled or job_status == "failed"

    if not canceled:
        root_status = JobStatus.FAILED if job_status == "failed" else JobStatus.FINISHED
        await _set_job_status(task, root_status)

        # Feed a finished op's wall-clock into the per-(tier, action)
        # service-time EWMA that turns a queue position into an ETA. Only
        # finished tasks are a useful sample; a failed/cancelled one's
        # duration is noise.
        if root_status == JobStatus.FINISHED:
            await asyncio.to_thread(_record_service_time, task)

    # The status the chain died with, or None while it is still succeeding.
    dead_chain = None
    if chain_failed:
        dead_chain = JobStatus.CANCELED if canceled else JobStatus.FAILED
    dependents = await asyncio.to_thread(
        lambda: list(
            _walk_core_dependents(
                task, include_canceled_storage=canceled, dead_chain=dead_chain
            )
        )
    )
    # Finalize is always carried as ``meta["core_finalize"]``; ``_walk_core_dependents``
    # yields those as CoreStep views. A CoreStep is stamped via ``mark`` (not
    # ``Job.set_status``), its knot children are enqueued fresh, and it has no rq
    # job to drop.
    all_ok = True
    # Every anchor a mark was written to during this dispatch. A finalize tree
    # hangs off the job that carries it, and one dispatch walks several of
    # them, so collecting the anchors is what makes the marks durable — see the
    # save loop below.
    anchors = {}
    # ``dedup_status_emits`` collapses repeated identical ``(storage_id,
    # status)`` socket fan-outs within this one dispatch pass (a chain often
    # lands the same status via two handlers). Every finalize handler is an
    # idempotent ``init_document`` upsert or a guarded delete, so at-least-once
    # redelivery/replay is safe for the DB writes; only the fire-and-forget
    # socket is non-idempotent, and this scope removes the intra-pass repeats.
    with dedup_status_emits():
        for dep_task in dependents:
            # Finalize is always metadata. A non-CoreStep here can only be a
            # pre-upgrade legacy rq ``core`` job replayed during migration — the
            # startup drain heals those, so skip rather than mishandle it.
            if not isinstance(dep_task, CoreStep):
                continue
            # Reaching what is behind a completed step means passing THROUGH
            # it, not running it again. On a dead chain the walk yields those
            # steps after the failure branch has already run, so re-executing
            # one re-applies a success body over what the failure branch just
            # wrote — a template marked Failed gets promoted back to ready by a
            # step redoing work it had already done. Its mark stands as it is.
            #
            # Only on a dead chain: a redelivered RESULT event must still
            # re-run its handlers, which is the at-least-once contract that
            # recovers a knot child whose enqueue failed.
            if dead_chain and dep_task.job_status in _TERMINAL_STATUSES:
                continue
            ok = await _run_handler(redis_manager, dep_task)
            all_ok = all_ok and ok
            # Propagate the outcome onto this dep before the next sibling/child
            # runs, so handlers that gate on ``task.depending_status`` see the
            # right value (was "deferred" otherwise — no worker on the core
            # queue ever marks it). A handler gated on ``depending_status``
            # no-ops when the chain failed and reports success for having done
            # nothing. Marking that FINISHED tells the NEXT step its dependency
            # succeeded, so a nested step runs its success body for an operation
            # that never happened.
            # A step's outcome is ITS OWN, not the chain's. A chain cancelled
            # half way still contains steps whose dependency genuinely
            # succeeded; marking those FAILED because the chain as a whole did
            # not succeed rewrites history that happened, and tells the step
            # below them that a dependency failed when it did not. Every
            # handler already decides this way — it gates on
            # ``task.depending_status`` — so the mark has to agree with it, or
            # a step reports an outcome its own handler did not take.
            dependency_succeeded = dep_task.depending_status == JobStatus.FINISHED
            step_status = (
                JobStatus.FINISHED if ok and dependency_succeeded else JobStatus.FAILED
            )
            # Stamp the shared meta node in place. A nested
            # child's ``depending_status`` reads this parent, so the mark
            # must land before the child runs (the walk yields parent first).
            dep_task.mark(step_status == JobStatus.FINISHED)
            anchor = dep_task.anchor
            if anchor is not None:
                anchors[anchor.id] = anchor
            # Advance this dep's storage children so the worker picks them up.
            # Skipped when the handler failed — failure must NOT advance the
            # chain — and when the member is cancelled, since running its
            # children would do work for an operation the user cancelled.
            #
            # This one stays keyed on the WHOLE chain, deliberately, while the
            # mark above is per step: creating work is mutation, not traversal.
            # A step whose own dependency succeeded may still not start a disk
            # operation once the chain it belongs to is dead — that is the
            # operation the user cancelled.
            if ok and not chain_failed and not _is_canceled(dep_task):
                enqueued = await _enqueue_metadata_storage_dependents(dep_task)
                all_ok = all_ok and enqueued

    # Persist the finalize status marks so ``Task.pending`` stops gating the
    # storage and the reconcile self-heal can tell a done chain from a stuck
    # one. Best-effort: a redelivery re-runs the idempotent handlers and
    # re-stamps. Metadata finalize steps are not rq jobs, so there is nothing to
    # drop from a queue — the persisted ``status`` mark is what retires each step
    # and leaving the node in meta is the forensic record of what ran.
    #
    # Save EVERY anchor the dispatch marked, not just the job the event was
    # keyed on. One event walks several finalize trees — in a template chain
    # the tree hangs off the third storage job while the event names the root —
    # and a mark written to an unsaved job is lost the moment this pass ends,
    # leaving a step that ran looking like a step that never did.
    for anchor in anchors.values():
        try:
            await asyncio.to_thread(anchor.job.save_meta)
        except Exception:
            all_ok = False
            log.exception(
                "task_results: failed to persist core_finalize marks on %s (event %s)",
                anchor.id,
                task_id,
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
                await redis.xadd(
                    DEAD_STREAM,
                    fields,
                    maxlen=DEAD_STREAM_MAXLEN,
                    approximate=True,
                )
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


async def _trim_to_frontier(redis):
    """Consumer-driven ``XTRIM ... MINID`` of the result stream (#2084 stopgap ①).

    Computes the safe floor from the group's ``last-delivered-id`` (read frontier)
    and the oldest un-ACKed PEL entry, then trims everything strictly below it.
    Because only read+ACKed entries fall below the floor, an unread completion can
    never be trimmed — the trim-before-read loss becomes structurally impossible.
    Best-effort: any error is logged and the loop continues (the producer's hard
    MAXLEN floor still bounds memory if this ever stops running).
    """
    try:
        last_delivered = None
        for g in await redis.xinfo_groups(RESULT_STREAM):
            if g.get("name") == CONSUMER_GROUP:
                last_delivered = g.get("last-delivered-id")
                break
        summary = await redis.xpending(RESULT_STREAM, CONSUMER_GROUP)
        # redis-py summary form: {"pending", "min", "max", "consumers"}
        min_pending = summary.get("min") if isinstance(summary, dict) else None
        floor = compute_trim_floor(last_delivered, min_pending)
        if floor:
            # Approximate (redis-py default) is intentional: it only ever retains
            # ~one macro-node of already-read+ACKed entries BEYOND the floor, never
            # removes an entry at/after it — conservative, memory-negligible, and it
            # strengthens (never weakens) the "no unread/un-ACKed result trimmed"
            # guarantee. Do not switch to approximate=False.
            await redis.xtrim(RESULT_STREAM, minid=floor)
    except Exception:
        log.exception("task_results: trim_to_frontier failed")


async def _run_progress(redis, redis_manager, consumer_name):
    """Drain the split-off ``stream:progress`` (#2084 stopgap ①).

    Progress heartbeats moved to their own stream so their high volume can never
    evict an unread ``kind=result`` from the shared budget. Progress is fire-and-
    forget — each entry only emits the ``task`` SocketIO event and is ACKed
    immediately (no chain, no PEL retention, no reclaim).
    """
    while True:
        try:
            response = await redis.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={PROGRESS_STREAM: ">"},
                count=READ_COUNT,
                block=BLOCK_MS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("task_results: progress read failed")
            await asyncio.sleep(1)
            continue
        if not response:
            continue
        for _stream, entries in response:
            for entry_id, fields in entries:
                try:
                    await _process_entry(redis_manager, fields)
                except Exception:
                    log.exception(
                        "task_results: progress entry raised for %s", entry_id
                    )
                await _ack_stream(redis, PROGRESS_STREAM, entry_id)


async def _ack_stream(redis, stream, entry_id):
    try:
        await redis.xack(stream, CONSUMER_GROUP, entry_id)
    except Exception:
        log.exception("task_results: XACK failed for %s on %s", entry_id, stream)


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
        progress_task = None
        try:
            redis = aioredis.from_url(rq_url(), decode_responses=True)
            await redis.ping()
            await _ensure_consumer_group(redis, RESULT_STREAM)
            await _ensure_consumer_group(redis, PROGRESS_STREAM)
            log.warning(
                "task_results: connected to %s (+progress %s); reading group=%s",
                STREAM_KEY,
                PROGRESS_STREAM,
                CONSUMER_GROUP,
            )
            progress_task = asyncio.create_task(
                _run_progress(redis, redis_manager, consumer_name)
            )
            last_reclaim = last_trim = time.monotonic()
            while True:
                await _read_and_dispatch(redis, redis_manager, consumer_name)
                now = time.monotonic()
                # Periodically sweep the PEL so an entry whose handler failed
                # (and was therefore not ACKed) gets retried, and a poison
                # entry is dead-lettered rather than retried forever.
                if now - last_reclaim >= RECLAIM_EVERY_S:
                    await _reclaim_pending(redis, redis_manager, consumer_name)
                    last_reclaim = now
                # Consumer-driven MINID trim so an unread result can't be evicted.
                if now - last_trim >= TRIM_EVERY_S:
                    await _trim_to_frontier(redis)
                    last_trim = now
        except Exception as e:
            log.warning("task_results: stream consumer error: %s", e)
        finally:
            if progress_task is not None:
                progress_task.cancel()
                try:
                    await progress_task
                except (asyncio.CancelledError, Exception):
                    pass
            if redis is not None:
                try:
                    await redis.aclose()
                except Exception:
                    pass
        log.warning("task_results: reconnecting in %ss", RECONNECT_DELAY_S)
        await asyncio.sleep(RECONNECT_DELAY_S)
