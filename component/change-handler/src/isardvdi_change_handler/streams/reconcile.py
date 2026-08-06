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

Finalize is carried as ``meta["core_finalize"]`` and run by the change-handler
stream consumer (see :mod:`task_results_consumer`). The **primary** recovery
from a change-handler crash/restart is that consumer's at-least-once stream
replay: the buffered ``kind=result`` events are re-delivered on reconnect and
the chain simply RESUMES where it left off (nested knot storage-dependents are
re-enqueued fresh). This module is the **backstop** for the cases replay cannot
cover — a result event that was never published or was trimmed before the group
read it — plus a one-shot legacy drain on upgrade.

Recovery principle (per task): reconcile every transitional item from **on-disk
reality** to a stable status the user can re-trigger from, and **never destroy a
present disk**. Reality means *asking the worker*, never reading a status or a
size off the row: those are caches, written by whichever branch last succeeded,
and they outlive what they described. So a stuck item is re-observed and its own
transition decides — an intact disk returns to ``ready``, a create that never
produced one settles ``deleted``, a delete whose file is gone completes and one
whose file is still there resets to a re-triggerable state. Data is never lost
because the reconcile only reads disks and sets statuses.

**Startup drain (one-shot).** :func:`_drain_core_once` clears any residual legacy
``core`` tombstones left by a system upgraded FROM rq-dependent finalize. Post
upgrade the ``core`` queue stays empty, so it is a no-op on every later boot.

**Pass 1 — orphaned DEFERRED jobs.** A DEFERRED job whose dependencies are all
terminal (and have been longer than a grace window, so the pass never races the
consumer's own release) is an orphan no worker will run: a storage-queue orphan
is released if its parents finished, cancelled if a parent failed/canceled; a
residual legacy ``core``-queue orphan (the DEFERRED counterpart to the QUEUED
tombstones ``_drain_core_once`` sweeps) is healed via :func:`_heal_core_orphan`.

**Pass 2 — storages stuck in a transitional status** (``maintenance``/``creating``)
whose backing chain is dead. Re-issues ``check_backing_chain`` and lets the
worker's answer drive the row through the normal path (which only promotes the
safe pre-ready set, so a running VM is never yanked). A storage whose chain is
still alive is left untouched.

**Pass 3 — domains parked in a storage-lock status** (``Maintenance``/
``CreatingTemplate``/``CreatingDisk``) whose storage settled but never promoted
them. Re-observes the backing storages and lets their own transition drive the
domain; → ``Failed`` directly only when a backing storage row is gone, since
there is then nothing left to observe.
"""

import asyncio
import logging as log
from datetime import datetime, timezone

from isardvdi_common.lib.task_index import current_task_id
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.task import Task, _chain_closure, finalize_has_unstamped
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import JobStatus

# Imported, never called: the pass no longer writes a storage row itself, and
# the tests patch these to assert it stays that way. Deleting them as "unused"
# breaks those tests with AttributeError, not at the deletion site.
from ..task_results.storage import (  # noqa: F401
    _apply_storage_update,
    send_status_socket,
)
from .task_results_consumer import (
    _release_storage_dependents,
    _run_handler,
    _set_job_status,
    _walk_core_dependents,
)

GRACE_S = 120
RECONCILE_EVERY_S = 90

# Metadata finalize never enqueues on ``core``, so post-migration the queue
# stays empty. It can only hold residual legacy tombstones from before the
# upgrade, drained once at startup by ``_drain_core_once``.
_CORE_QUEUE_KEY = "rq:queue:core"
# Batch size + pass cap for the one-shot startup drain.
_DRAIN_SCAN = 100
_DRAIN_MAX_BATCHES = 200
# The finalize-orphan reconcile must not flag a just-settled chain the consumer
# is about to finalize: treat a metadata finalize as orphaned only once it is
# older than the consumer's redelivery envelope (5 reclaims of 60s → 15 min).
FINALIZE_ORPHAN_MIN_AGE_S = 900

_TERMINAL = (
    JobStatus.FINISHED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
    JobStatus.STOPPED,
)


# A DEFERRED chain can outlive its parents' RQ job data: RQ evicts a
# finished/failed job's hash after its result TTL, after which reading the
# dependency's status raises ``InvalidJobOperation`` (the hash is there but its
# status field is gone) or ``NoSuchJobError`` (the hash itself is gone). Either
# way the job is necessarily terminal and long settled. Left unguarded these
# crash a whole reconcile pass and, via the per-task ``except`` in
# ``_reconcile_orphan_deferred``, ABANDON the very orphan the pass exists to heal.
_JOB_GONE = (InvalidJobOperation, NoSuchJobError)


def _dep_job_status(dep):
    """RQ status of a dependency, or ``None`` when its job data is gone
    (evicted after result TTL) — a gone job counts as terminal-and-settled."""
    try:
        return dep.job_status
    except _JOB_GONE:
        return None


# Domain statuses whose work is EXECUTED by a storage task chain, so this
# component owns reconciling them; engine keeps the statuses it drives itself
# (``CreatingDomain`` onwards, and the libvirt runtime states). They are pure
# storage locks, never runtime states, so re-observing them cannot race the VM
# lifecycle.
#
# ``CreatingDisk`` is covered for the case that actually strands desktops: the
# chain died before producing the disk, and the re-observation settles the row
# ``deleted`` so the domain fails instead of hanging. A ``CreatingDisk`` domain
# whose disk IS present is re-observed but not advanced — handing it to engine
# needs a transition that survives the chain's later storage updates, since
# ``CreatingDomain`` is itself in the promote-to-``Stopped`` set.
_DOMAIN_LOCK_STATUSES = ("Maintenance", "CreatingTemplate", "CreatingDisk")


def _as_aware_utc(dt):
    """Normalise an RQ ``ended_at`` (naive or aware) to aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _settled_at(dep):
    """When a terminal dependency settled, or ``None`` if we cannot tell.

    RQ writes no ``ended_at`` when a job is cancelled, so a cancelled
    dependency is aged from its creation instead — otherwise a chain settled
    by a cancel could never age out and its orphans stayed invisible to this
    pass for ever.

    A FINISHED/FAILED dependency without ``ended_at`` deliberately stays
    unreadable: that is a job the consumer marked mid-flight, and it may still
    be the replay state of an entry being redelivered. Ageing it here would
    let the heal delete that state before the redelivery arrives.
    """
    ended = _as_aware_utc(getattr(dep.job, "ended_at", None))
    if ended is not None:
        return ended
    if dep.job_status == JobStatus.CANCELED:
        return _as_aware_utc(getattr(dep.job, "created_at", None))
    return None


def _deps_terminal_and_aged(task, now, grace_s):
    """True if every dependency is terminal AND the most recent one settled
    longer than ``grace_s`` ago.

    A DEFERRED job with no dependencies, a non-terminal dependency, or a
    dependency whose settle time we cannot read is treated as NOT an orphan —
    we only ever act on chains we can prove are dead and settled, never on one
    the consumer might still be about to release.
    """
    deps = task.dependencies
    if not deps:
        return False
    newest = None
    for dep in deps:
        status = _dep_job_status(dep)
        if status is None:
            # Vanished dependency job: terminal and long settled. It can neither
            # block healing nor contribute a settle time to the age check.
            continue
        if status not in _TERMINAL:
            return False
        try:
            settled = _settled_at(dep)
        except _JOB_GONE:
            # Job evicted between the status read and here — treat as gone.
            continue
        if settled is None:
            return False
        if newest is None or settled > newest:
            newest = settled
    if newest is None:
        # Every dependency's job is gone: the chain is definitively dead and
        # long settled, so heal it rather than leave the orphan stranded.
        return True
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
    # A chain whose parent failed or was cancelled is dead: run its finalize
    # handlers (they take their failure branch) but never release its deferred
    # storage children, which would run work for an operation that is over.
    doomed = any(
        getattr(dep, "job_status", None) in (JobStatus.FAILED, JobStatus.CANCELED)
        for dep in task.dependencies
    )
    chain = [task] + list(_walk_core_dependents(task))
    all_ok = True
    for dep_task in chain:
        ok = await _run_handler(redis_manager, dep_task)
        all_ok = all_ok and ok
        await _set_job_status(dep_task, JobStatus.FINISHED if ok else JobStatus.FAILED)
        if ok and not doomed:
            await _release_storage_dependents(dep_task)
    # Same rule as the consumer: the Jobs ARE the replay state, so they are
    # only dropped once the whole heal succeeded. Deleting them after a failed
    # handler would make a later redelivery a no-op and wedge the chain.
    if all_ok:
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
    # Release ONLY when every parent is provably FINISHED. A parent that
    # failed, was cancelled, or whose job data is gone cannot be shown to have
    # succeeded, and advancing on it runs the next stage of an operation that
    # may well have failed — a backing-chain read over a disk whose create
    # never completed, say. Unknown is not success.
    all_finished = True
    for dep in task.dependencies:
        try:
            status = dep.job_status
        except Exception:
            status = None
        if status != JobStatus.FINISHED:
            all_finished = False
            break
    if not all_finished:
        try:
            # ``Task.cancel`` settles the whole chain and promotes nothing.
            # Cancelling the raw RQ job with ``enqueue_dependents=True`` is
            # what used to push this chain's finalize dependents onto the
            # ``core`` queue, where nothing consumes them: they stayed QUEUED
            # for ever, ``Task.pending`` read them as active work and the
            # storage was rejected with ``storage_pending_task`` from then on.
            await asyncio.to_thread(task.cancel)
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


def _drain_connection():
    """Plain redis connection for the tombstone sweep (raw list surgery)."""
    import redis
    from isardvdi_common.connections.redis_urls import rq_url

    return redis.from_url(rq_url())


async def _drain_core_once(redis_manager):
    """One-shot upgrade drain, run on the eager startup pass only.

    Metadata finalize never enqueues on ``core``, so once migrated the queue
    stays empty and this is a no-op on every subsequent boot. It exists solely
    to clear the debt of a system upgraded FROM the legacy rq-dependent finalize:
    any job left QUEUED on ``core`` there is a tombstone that ``Task.pending``
    counts as active work, wedging every later operation on that storage.

    Each residual job is HEALED (its finalize re-run via :func:`_heal_core_orphan`)
    before its queue entry is removed, so a delivery lost across the upgrade still
    finalizes from reality; a dangling id (task already gone) is just dropped.
    Upgrades run on a stable, no-in-flight system, so nothing races this drain —
    hence no age gate. A non-empty ``core`` here is a migration remnant (or, once
    migrated, a regression) and is logged loudly.

    Redis connectivity failures PROPAGATE (the ``lrange`` is unguarded): the
    caller runs this once behind a flag and retries on the next tick until it
    succeeds, so a change-handler that outraced redis still drains. Only per-job
    errors are swallowed, so one bad job never aborts the whole sweep.
    """
    conn = _drain_connection()
    drained = 0
    for _ in range(_DRAIN_MAX_BATCHES):
        ids = await asyncio.to_thread(conn.lrange, _CORE_QUEUE_KEY, 0, _DRAIN_SCAN - 1)
        if not ids:
            break
        progressed = 0
        for raw_id in ids:
            job_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
            try:
                if not Task.exists(job_id):
                    await asyncio.to_thread(conn.lrem, _CORE_QUEUE_KEY, 0, raw_id)
                    log.warning("reconcile: dropped dangling core queue id %s", job_id)
                    drained += 1
                    progressed += 1
                    continue
                task = await asyncio.to_thread(Task, job_id)
                if task.job.get_status() != JobStatus.QUEUED:
                    await asyncio.to_thread(conn.lrem, _CORE_QUEUE_KEY, 0, raw_id)
                    progressed += 1
                    continue
                if not all(
                    getattr(dep, "job_status", None) in _TERMINAL
                    for dep in task.dependencies
                ):
                    # Upstream not settled — a quiesced upgrade never hits this;
                    # leave it rather than heal a chain whose inputs are pending.
                    continue
                log.warning(
                    "reconcile: draining core tombstone %s (%s, user=%s)",
                    job_id,
                    getattr(task, "task", "?"),
                    getattr(task, "user_id", "?"),
                )
                drained += await _heal_core_orphan(redis_manager, task)
                await asyncio.to_thread(conn.lrem, _CORE_QUEUE_KEY, 0, raw_id)
                progressed += 1
            except Exception:
                log.exception("reconcile: core drain failed for %s", job_id)
        if progressed == 0:
            break
    if drained:
        log.warning(
            "reconcile: core drain healed/removed %s residual tombstone(s) on "
            "startup — expected only on a legacy→metadata upgrade",
            drained,
        )
    return drained


# The same predicate ``chain_pending`` uses, deliberately shared rather than
# reimplemented: the hatch and the pending check must agree about what "this
# finalize step has not run" means, or the hatch opens for chains the predicate
# still calls busy (or worse, never opens for ones it does).
_finalize_has_unstamped = finalize_has_unstamped


def _job_settled_at(job, status):
    """:func:`_settled_at` for a raw rq job rather than a :class:`Task`.

    Same rule, and the same deliberate blind spot: a FINISHED/FAILED job with
    no ``ended_at`` reads as unknown, because that is a job the consumer marked
    mid-flight and it may still be the replay state of an entry being
    redelivered.
    """
    ended = _as_aware_utc(getattr(job, "ended_at", None))
    if ended is not None:
        return ended
    if status == JobStatus.CANCELED:
        return _as_aware_utc(getattr(job, "created_at", None))
    return None


def _metadata_finalize_orphaned(task, now, min_age_s):
    """A metadata chain whose real (storage) work all settled but whose finalize
    never applied and is older than the redelivery envelope: the result event
    was lost (worker died before publishing). Not live work — Pass 2 heals it
    from the storage's own reality.

    Asked over the whole CLOSURE, not the task it was handed. ``_task_alive``
    resolves a row's chain through ``storage.task``, which holds the id of the
    chain's ROOT — but the job carrying ``core_finalize`` is not the root. In
    the real template chain the anchor is the third storage job
    (``move → create → qemu_img_info_backing_chain``), so a hatch that reads
    ``core_finalize`` off the root alone can never open for the one chain shape
    that has a knot. Measured on this base: from the root it answered False,
    from the anchor True, for the very same settled chain.

    That is only latent while ``chain_pending`` is blind to finalize steps and
    answers False here anyway. The moment an unstamped step counts as pending,
    a lost result event pins the chain pending for ever and the reconcile can
    never heal that row again — the "428 forever" class this stack exists to
    kill, re-entered backwards. Hence closure-wide first, stricter predicate
    after.

    Conservative in both directions: a member that cannot be read, or that is
    terminal without a readable settle time, means we cannot prove the chain is
    dead, so the hatch stays shut.
    """
    try:
        closure = _chain_closure(task.job, task._redis)
    except Exception:
        return False

    if not any(
        _finalize_has_unstamped((getattr(job, "meta", None) or {}).get("core_finalize"))
        for job in closure.values()
    ):
        return False

    settled = []
    for job in closure.values():
        try:
            status = job.get_status(refresh=True)
        except _JOB_GONE:
            # Hash evicted after its result TTL: necessarily terminal and long
            # settled, so it neither blocks the hatch nor dates it.
            continue
        except Exception:
            return False
        if status not in _TERMINAL:
            return False
        when = _job_settled_at(job, status)
        if when is None:
            return False
        settled.append(when)

    if not settled:
        return False
    # The chain settled when its LAST member did.
    return (now - max(settled)).total_seconds() >= min_age_s


def _task_alive(storage, now=None, min_age_s=FINALIZE_ORPHAN_MIN_AGE_S):
    """True if the storage's backing task is still live work — Pass 1 / the
    consumer will finalize it and Pass 2 must not interfere. A metadata chain
    with an orphaned finalize is pending but NOT live, so Pass 2 may heal it."""
    task_id = current_task_id(Task._redis, getattr(storage, "id", None))
    if not task_id:
        # A ``creating`` target (a convert destination) carries no task of its
        # own and is not named as an owner of the chain either — the producing
        # task lives on the origin (``converted_from``). It is live until that
        # origin task settles, so a still-running convert's half-written disk is
        # never finalized ``ready``. With nothing resolvable a ``creating`` row
        # cannot be proven dead, so leave it to its parent op.
        #
        # A parked row needs no such fallback: the chain that parks it names it
        # as an owner of its tasks, so the row answers for itself. That also
        # retires the "consult the marker only while parked" rule the
        # back-reference needed — the index names THAT chain's task, never
        # whatever the parker happens to be doing months later.
        origin_id = getattr(storage, "converted_from", None)
        if origin_id:
            task_id = current_task_id(Task._redis, origin_id)
        if not task_id:
            return getattr(storage, "status", None) == "creating"
    if not Task.exists(task_id):
        return False
    try:
        task = Task(task_id)
        # The WHOLE chain, not its neighbours: a deeper chain reads as settled
        # from its root while later levels are still writing the disk.
        if not task.chain_pending:
            return False
        return not _metadata_finalize_orphaned(
            task, now or datetime.now(timezone.utc), min_age_s
        )
    except Exception:
        return False


async def _finalize_stuck_storage(redis_manager, storage):
    """Finalize one stuck transitional storage by re-observing the disk.

    Always re-issues ``check_backing_chain`` and lets the storage worker say
    what is really there: the row is driven to ``ready`` (a present disk), or
    ``deleted`` (a create that never produced one, or a delete whose file is
    already gone). The recheck reads the disk and never removes a present
    file, so a not-yet-run delete resets to a re-triggerable state rather
    than losing data.

    It used to short-circuit to ``ready`` whenever the row's stored
    ``qemu-img-info`` showed a positive ``virtual-size``. That field is
    written only when an info task SUCCEEDS, and the branch that concludes
    ``deleted`` does not write it at all — and the row update merges rather
    than replaces, so the size of a file that has since been deleted survives
    on the row. A delete whose chain died therefore matched the shortcut
    exactly, and the pass asserted a disk that was gone: a ``ready`` storage
    and a bootable-looking desktop that fails at libvirt. Reading the row was
    never an observation; only the worker can make one.

    Returns 0: nothing is finalized in place any more.
    """
    prev = getattr(storage, "status", "?")
    try:
        # A self-heal recheck of a STUCK storage: recover it soon rather than on
        # the idle ``background`` lane (the method default), but off the reserved
        # pool — no user desktop is blocked on it. Trigger-driven, like the admin
        # datatable "check" click.
        storage.check_backing_chain(
            user_id=getattr(storage, "user_id", None), priority="standard"
        )
        log.warning(
            "reconcile: stuck storage %s (%s); re-issued check_backing_chain to "
            "observe the disk",
            storage.id,
            prev,
        )
    except Exception:
        log.exception(
            "reconcile: could not re-issue check_backing_chain for %s",
            storage.id,
        )
    return 0


# Transitional storage statuses whose backing task can die mid-op and leave the
# row stuck: an in-place op (``maintenance``) or a fresh disk being built
# (``creating``, e.g. a convert target). Both recover from disk reality above.
_TRANSITIONAL_STORAGE_STATUSES = ["maintenance", "creating"]


async def _reconcile_stuck_storage(redis_manager):
    """Pass 2: finalize storages stuck in a transitional status
    (``maintenance``/``creating``) whose backing task is dead. The primary
    mid-op recovery is the consumer's at-least-once stream replay (the chain
    simply resumes); this is the backstop for a genuinely lost result event.
    Returns the count finalized."""
    try:
        stuck = await asyncio.to_thread(
            Storage.get_index, _TRANSITIONAL_STORAGE_STATUSES, "status"
        )
    except Exception:
        log.exception("reconcile: could not list transitional storages")
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


def _finalize_stuck_domain(domain):
    """Finalise one domain parked in a storage-lock status from its storage
    reality. Returns 1 if finalised in place, else 0.

    - it declares disks but none of their storage rows still exist -> ``Failed``
      (the disk is gone; there is nothing left to observe).
    - otherwise the backing storages are re-observed and the storage's own
      ready/deleted transition drives the domain, exactly as the original chain
      would have. ``ready`` promotes the domain (to ``Stopped``, or to
      ``CreatingDomain`` for a ``CreatingDisk`` hand-off); ``deleted`` fails it.

    It used to promote to ``Stopped`` itself whenever every storage read
    ``ready`` with no live task. That is an inference from two row fields, and
    a status is a cache: it says what some earlier write concluded, not what is
    on disk now. Asking the worker costs one task and cannot be wrong.

    A domain whose storage is still in flight (a live chain) is left alone —
    Pass 2 and the consumer own it.
    """
    declared_ids = [
        disk["storage_id"]
        for disk in domain.create_dict.get("hardware", {}).get("disks", [])
        if disk.get("storage_id")
    ]
    storages = domain.storages
    # ``Domain.storages`` drops ids whose row no longer exists, so a domain that
    # declares two disks and resolves one is PARTIALLY gone. Comparing counts
    # (rather than "resolved nothing") keeps that case on the Failed branch: a
    # desktop promoted to Stopped with a missing disk looks bootable and fails
    # at the next start instead.
    if declared_ids and len(storages) < len(declared_ids):
        domain.status = "Failed"
        domain.current_action = None
        log.warning(
            "reconcile: finalized orphaned domain %s (backing storage gone -> Failed)",
            domain.id,
        )
        return 1
    if not storages:
        return 0
    if any(_task_alive(storage) for storage in storages):
        return 0
    for storage in storages:
        try:
            # ``find`` is the observation that converges a DOMAIN: the disk is
            # there -> storage ``ready`` -> the promote advances the domain; it
            # is gone -> ``deleted`` -> the domain fails. Non-blocking and no
            # retries, so a storage that is busy again by now is simply skipped
            # rather than queued behind itself.
            storage.find(user_id=getattr(domain, "user", None), blocking=False, retry=0)
        except Exception:
            log.exception(
                "reconcile: could not re-observe storage %s of stuck domain %s",
                getattr(storage, "id", "?"),
                domain.id,
            )
    log.warning(
        "reconcile: stuck domain %s (%s); re-observing %s backing storage(s)",
        domain.id,
        getattr(domain, "status", "?"),
        len(storages),
    )
    return 0


async def _reconcile_stuck_domains(redis_manager):
    """Pass 3: finalise domains parked in a storage-lock status
    (``Maintenance`` / ``CreatingTemplate``) whose storage has already settled
    but never promoted them. The storage-keyed passes above are blind to a
    domain whose storage is already ``ready`` or whose storage row is gone.
    Returns the count finalised."""
    try:
        stuck = await asyncio.to_thread(
            Domain.get_index,
            [["desktop", status] for status in _DOMAIN_LOCK_STATUSES]
            + [["template", status] for status in _DOMAIN_LOCK_STATUSES],
            "kind_status",
        )
    except Exception:
        log.exception("reconcile: could not list storage-lock domains")
        return 0
    healed = 0
    for domain in stuck:
        try:
            healed += await asyncio.to_thread(_finalize_stuck_domain, domain)
        except Exception:
            log.exception(
                "reconcile: finalize failed for domain %s", getattr(domain, "id", "?")
            )
    return healed


async def run(redis_manager, interval_s=RECONCILE_EVERY_S, grace_s=GRACE_S):
    """Long-running reconcile loop: an eager pass on startup, then all passes
    every ``interval_s`` seconds. Started alongside the changefeed listener and
    the task-results consumer in :func:`__main__.main`.

    Each pass swallows its own errors, so a transient Redis/DB hiccup never
    kills the loop — the next tick simply retries.
    """
    log.warning(
        "reconcile: self-heal starting (every %ss, grace %ss)", interval_s, grace_s
    )
    # One-shot legacy-tombstone drain, gated by ``drained`` so a redis hiccup
    # retries next tick instead of silently skipping. No-op post-migration.
    drained = False
    while True:
        try:
            if not drained:
                await _drain_core_once(redis_manager)
                drained = True
            await _reconcile_orphan_deferred(redis_manager, grace_s=grace_s)
            await _reconcile_stuck_storage(redis_manager)
            await _reconcile_stuck_domains(redis_manager)
            await _assert_core_empty()
        except Exception:
            log.exception("reconcile: pass raised")
        await asyncio.sleep(interval_s)


async def _assert_core_empty():
    """Tripwire: metadata finalize never enqueues on ``core``, so post-migration
    the queue must stay empty. If the "impossible" ever happens it is a real
    regression — surface it loudly so alerting (``ConsumerlessQueueBacklog``)
    fires off the change-handler logs. Best-effort; a transient redis hiccup is
    swallowed by the caller's except."""
    depth = await asyncio.to_thread(_drain_connection().llen, _CORE_QUEUE_KEY)
    if depth:
        log.warning(
            "ConsumerlessQueueBacklog: rq:queue:core depth=%s — metadata finalize "
            "must never enqueue on core; this is a regression",
            depth,
        )
