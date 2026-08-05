#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

import logging as log
import os
from time import sleep
from types import SimpleNamespace

from cachetools import cached
from isardvdi_common.connections.redis_base import RedisBase
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.helpers.task_streams import (
    publish_canceled_event,
    result_stream_backpressured,
)
from isardvdi_common.helpers.task_timeouts import job_timeout_for
from rq import Queue, Retry
from rq.exceptions import InvalidJobOperation, NoSuchJobError
from rq.job import Job, JobStatus
from rq.utils import now as rq_now
from rq.utils import utcformat


def tasks_from_ids(task_ids):
    """
    Get tasks from task IDs

    :param task_ids: task IDs
    :type task_ids: list
    :return: tasks
    :rtype: list
    """

    tasks = []
    for task_id in task_ids:
        if not Task.exists(task_id):
            continue
        try:
            tasks.append(Task(task_id))
        except NoSuchJobError:
            # ``exists`` only checks the hash is there. A hash left with just
            # a status field (a job deleted while something was still writing
            # its status) passes that check but cannot be loaded, and letting
            # it raise here would break every chain walk that happens to meet
            # it. Reconcile owns removing those.
            log.warning("task listing: skipping unreadable job %s", task_id)
    return tasks


def global_status(tasks):
    """
    Get global status of provided tasks.

    :param tasks: Tasks
    :type tasks: list
    :return: Status
    :rtype: str
    """
    status_priority = [
        JobStatus.CANCELED,
        JobStatus.FAILED,
        JobStatus.STARTED,
        JobStatus.SCHEDULED,
        JobStatus.STOPPED,
        JobStatus.QUEUED,
        JobStatus.DEFERRED,
        JobStatus.FINISHED,
    ]
    for status in status_priority:
        for task in tasks:
            if task.job_status == status:
                return status
    return "unknown"


_TERMINAL_STATUSES = (
    JobStatus.FINISHED,
    JobStatus.FAILED,
    JobStatus.STOPPED,
    JobStatus.CANCELED,
)

# Stamp ``ended_at`` only on a job hash that is still there (never resurrect a
# concurrently-deleted job as a status-only ghost) and never overwrite a
# timestamp RQ itself wrote.
#
# ``HSETNX`` is NOT enough: RQ serialises an unset ``ended_at`` as an EMPTY
# field rather than omitting it, so the field always exists and ``HSETNX``
# silently writes nothing. Verified on a live redis — an empty value has to be
# treated as absent.
_ENDED_AT_STAMP = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  local current = redis.call('HGET', KEYS[1], 'ended_at')
  if not current or current == '' then
    return redis.call('HSET', KEYS[1], 'ended_at', ARGV[1])
  end
end
return 0
"""


# A cancel has to outlive the job's own status. rq runs a job a worker had
# already dequeued even after it is cancelled, and the worker's success handler
# then rewrites the status to ``finished`` — so by the time the completion is
# published there is nothing left in the job to say it was ever cancelled, and
# the chain is dispatched as if it were alive.
#
# The record lives as a field on the JOB'S OWN hash, deliberately. It is not a
# second thing to expire: it shares the job's key, the job's expiry and the
# job's deletion, so it can never outlive what it refers to and there is no
# retention clock of its own to get wrong. rq's ``Job.save`` writes its own
# fields with ``HSET mapping=...``, which leaves unrelated fields alone, so the
# worker's success write does not clear it — verified against rq 2.3.2.
CANCELED_FIELD = "isard_canceled_at"

# Guarded by EXISTS so a cancel racing a delete can never recreate the hash as a
# status-less ghost — the same trap ``_stamp_ended_at`` documents. Absence of
# the field is therefore always readable as "not cancelled".
_CANCELED_STAMP = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
end
return 0
"""


def mark_canceled(connection, job_id):
    """Record durably that this member was cancelled.

    Written once, where the cancel is decided (:meth:`Task.cancel`), never by
    the producers of result events — they only read it.
    """
    try:
        connection.eval(
            _CANCELED_STAMP,
            1,
            Job.key_for(job_id),
            CANCELED_FIELD,
            utcformat(rq_now()),
        )
    except Exception:
        log.debug("task cancel: could not record the cancel of %s", job_id)


def was_canceled(connection, job_id):
    """True only when this member carries the cancel record.

    Absence means "not cancelled" — an unreadable job, a job from before this
    existed, and a job nobody ever cancelled all answer False, so a chain that
    predates the record behaves exactly as it did. Failing this open is
    deliberate: the cost of missing a cancel is the behaviour we have today,
    while the cost of inventing one is running a chain's failure branch over
    work that succeeded.
    """
    try:
        return connection.hget(Job.key_for(job_id), CANCELED_FIELD) is not None
    except Exception:
        return False


def _stamp_ended_at(connection, job_id):
    """Give a cancelled job an ``ended_at``.

    RQ's ``Job.cancel`` never writes one, and the change-handler's reconcile
    ages a settled chain from exactly that field — without it a cancelled
    dependency reads as "not yet settled" forever and its orphaned dependents
    are never healed.
    """
    try:
        connection.eval(_ENDED_AT_STAMP, 1, Job.key_for(job_id), utcformat(rq_now()))
    except Exception:
        log.debug("task cancel: could not stamp ended_at on %s", job_id)


def _chain_closure(job, connection):
    """Every job reachable from ``job`` through dependency/dependent links.

    Walks the raw ``meta`` id lists instead of the ``Task.dependencies`` /
    ``Task.dependents`` properties: those hydrate a full Task per id and skip
    ids whose hash has gone, which would silently drop chain members from the
    sweep. Dangling and malformed ids are skipped; the visited set makes a
    cyclic ``meta`` impossible to loop on.
    """
    closure = {job.id: job}
    frontier = [job]
    while frontier:
        current = frontier.pop()
        meta = getattr(current, "meta", None) or {}
        for key in ("dependency_ids", "dependent_ids"):
            for job_id in meta.get(key) or []:
                if job_id in closure:
                    continue
                try:
                    member = Job.fetch(job_id, connection=connection)
                except Exception:
                    # Gone or unreadable (a status-only ghost hash raises too):
                    # nothing to cancel, and the rest of the chain still must be.
                    continue
                closure[job_id] = member
                frontier.append(member)
    return closure


def _closure_leaves_first(closure):
    """Order closure members so a job comes after every dependent of its own.

    Cancelling leaves-first means a dependency is never settled while one of
    its dependents is still cancellable, so RQ can never observe a releasable
    parent mid-sweep.
    """
    pending = {
        job_id: {
            dependent_id
            for dependent_id in (
                (getattr(job, "meta", None) or {}).get("dependent_ids") or []
            )
            if dependent_id in closure
        }
        for job_id, job in closure.items()
    }
    remaining = dict(closure)
    ordered = []
    while remaining:
        ready = sorted(job_id for job_id in remaining if not pending[job_id])
        if not ready:
            # Cyclic meta: order stops being meaningful, but every member must
            # still be cancelled.
            log.warning("task cancel: cyclic chain meta, cancelling in scan order")
            ordered.extend(remaining.values())
            break
        for job_id in ready:
            ordered.append(remaining.pop(job_id))
            for dependents in pending.values():
                dependents.discard(job_id)
    return ordered


def _closure_roots(closure):
    """Members with no dependency inside the closure — the chain's entry
    points, and what a result-stream event is keyed on."""
    return [
        job
        for job_id, job in closure.items()
        if not [
            dependency_id
            for dependency_id in (
                (getattr(job, "meta", None) or {}).get("dependency_ids") or []
            )
            if dependency_id in closure
        ]
    ]


def register_dependencies(job_kwargs, dependencies):
    """
    Register dependencies in job_kwargs

    :param job_kwargs: kwargs for a job
    :type job_kwargs: dict
    :param dependencies: List of a depencency jobs
    :type dependencies: list
    """
    job_kwargs.setdefault("depends_on", []).extend(
        [dependency.job for dependency in dependencies]
    )
    job_kwargs.setdefault("meta", {}).setdefault("dependency_ids", []).extend(
        [dependency.id for dependency in dependencies]
    )


# Enqueue admission backpressure (stopgap ①). When the change-handler consumer is
# far behind (result stream near its 100k floor), briefly throttle the INFLOW of
# new result-producing storage work at enqueue. The caller (API / engine creating
# the task) waits here instead of a storage worker sleeping mid-job, so the worker
# fleet stays free to DRAIN the backlog. Bounded + non-fatal: only storage.* queues,
# never longer than the cap, never raises (a redis blip must not fail task creation).
TASK_ADMISSION_MAX_WAIT_S = int(os.environ.get("TASK_RESULTS_ADMISSION_MAX_WAIT_S", 10))


def _await_result_stream_admission(connection, queue):
    """Throttle enqueue of a result-producing storage task while the consumer is behind."""
    if not str(queue).startswith("storage."):
        return
    waited = 0.0
    while result_stream_backpressured(connection):
        if waited >= TASK_ADMISSION_MAX_WAIT_S:
            log.warning(
                "task admission: result stream at floor after %ss; enqueuing %r anyway",
                waited,
                queue,
            )
            break
        sleep(1.0)
        waited += 1.0


def knot_child_id(step_id, index):
    """The rq job id of the ``index``-th storage child of finalize step
    ``step_id`` — the storage-under-core knot.

    Deterministic, so the id is known when the chain is BUILT even though the
    job is created when the step runs: that is what lets the edge to the child
    be declared up front instead of being patched in afterwards, and what makes
    a redelivery address the same child instead of starting a second disk
    operation. rq job ids forbid ``:`` and the metadata step ids carry it, so
    the whole thing is flattened.

    The single definition is load-bearing: whoever creates the child and
    whoever looks for it must compute the same id, or the graph acquires two
    names for one member.
    """
    return f"{step_id}:sd:{index}".replace(":", "-")


def _serialize_finalize(dep, parent_id, index, user_id, category_id):
    """One ``core`` dependent (and its subtree) as a finalize metadata node.

    A ``core`` child becomes a nested finalize node; a storage child becomes a
    ``storage_dependents`` entry the consumer enqueues fresh when this step runs
    (the storage-under-core knot). Ids are deterministic, never uuid4, so a
    redelivery addresses the same step.

    Each knot child's future id is recorded on the node as
    ``storage_dependent_ids`` at the same time. The child does not exist yet,
    but its id does, so the graph can carry the edge to it from the moment the
    chain is built rather than acquiring it later — if ever.
    """
    step_user_id = dep.get("user_id", user_id)
    step_category_id = dep.get("category_id", category_id)
    node = {
        "id": f"{parent_id}:cf:{index}",
        "task": dep.get("task"),
        "queue": dep.get("queue", "core"),
        "user_id": step_user_id,
        "category_id": step_category_id,
        "kwargs": (dep.get("job_kwargs") or {}).get("kwargs", {}) or {},
        "args": (dep.get("job_kwargs") or {}).get("args", []) or [],
        "core_finalize": [],
        "storage_dependents": [],
        "storage_dependent_ids": [],
        "status": None,
    }
    for child_index, child in enumerate(dep.get("dependents", []) or []):
        if str(child.get("queue", "")).startswith("core"):
            node["core_finalize"].append(
                _serialize_finalize(
                    child, node["id"], child_index, step_user_id, step_category_id
                )
            )
        else:
            child.setdefault("user_id", step_user_id)
            child.setdefault("category_id", step_category_id)
            node["storage_dependent_ids"].append(
                knot_child_id(node["id"], len(node["storage_dependents"]))
            )
            node["storage_dependents"].append(child)
    return node


def _knot_child_ids(node):
    """Every knot child id declared anywhere in a finalize tree.

    They all belong on the ANCHOR's ``dependent_ids``: the anchor is the only
    real rq job in the tree, so it is the only place an id-based walk can pick
    the edge up from.
    """
    ids = list(node.get("storage_dependent_ids") or [])
    for child in node.get("core_finalize") or []:
        ids.extend(_knot_child_ids(child))
    return ids


class CoreStep:
    """A ``meta["core_finalize"]`` node that quacks like a :class:`Task` for the
    finalize consumer and the ``to_dict`` / ``pending`` contract.

    No rq job. ``job_status`` is derived: ``FINISHED``/``FAILED`` once the
    consumer stamps ``node["status"]``, else ``QUEUED`` when what it waits on has
    settled (mirrors rq's DEFERRED->QUEUED promotion) and ``DEFERRED`` otherwise
    — which gates ``Task.pending`` exactly as a real ``core`` dependent did,
    without a leakable job. ``_parent`` is the member it waits on, read by
    ``depending_status`` (the gate the handlers check).
    """

    # Only weights ``Task.progress``'s time-average; a finalize step has no
    # partial progress, so any positive constant is fine.
    _STEP_TIMEOUT = 30

    def __init__(self, node, parent, redis):
        self._node = node
        self._parent = parent
        self._redis = redis

    @property
    def job(self):
        """Stand-in for the rq ``Job`` that ``Task.progress`` reads (``timeout``
        + ``meta["progress"]``). No ``set_status`` / ``delete`` on purpose — the
        metadata path uses :meth:`mark`; a stray legacy call must fail loudly."""
        return SimpleNamespace(
            timeout=self._STEP_TIMEOUT,
            meta={"progress": 1.0 if self.job_status == JobStatus.FINISHED else 0},
        )

    @property
    def id(self):
        return self._node.get("id")

    @property
    def task(self):
        return self._node.get("task")

    @property
    def queue(self):
        return self._node.get("queue", "core")

    @property
    def user_id(self):
        return self._node.get("user_id")

    @property
    def category_id(self):
        return self._node.get("category_id")

    @property
    def kwargs(self):
        return self._node.get("kwargs", {}) or {}

    @property
    def args(self):
        return self._node.get("args", []) or []

    @property
    def result(self):
        return None

    @property
    def exc_info(self):
        return None

    @property
    def position(self):
        return None

    @property
    def storage_dependents(self):
        """Raw dependent dicts to enqueue as rq Tasks when this step runs."""
        return self._node.get("storage_dependents", []) or []

    @property
    def knot_child_ids(self):
        """The rq job ids of this step's storage children, in the same order.

        Declared when the chain was built, so they name the children whether or
        not they exist yet. A chain built before this existed has none, and the
        ids are re-derived from the step id so such a chain still resolves.
        """
        declared = self._node.get("storage_dependent_ids")
        if declared:
            return list(declared)
        children = self.storage_dependents
        if children:
            # Only a chain built before the edge existed reaches here, i.e. one
            # that was already in flight when this version was deployed. The
            # ids re-derive, so it still runs and settles — but its ROOT never
            # recorded them, so a cancel of that chain cannot reach its knot
            # child, exactly as it could not before the upgrade. Said out loud
            # because it is invisible otherwise: the operator sees a cancel
            # that appears to do nothing, on that chain only, once.
            log.warning(
                "task: chain step %s predates the knot edge (built before this "
                "version); its knot children are reachable by derivation but "
                "not from the chain root, so a cancel cannot reach them. "
                "Pre-existing chains drain with the old behaviour; chains "
                "started after this deploy are unaffected.",
                self.id,
            )
        return [knot_child_id(self.id, index) for index in range(len(children))]

    @property
    def anchor(self):
        """The rq job whose ``meta`` carries this step — where :meth:`mark`
        becomes durable.

        A finalize tree hangs off ONE real job and can be several levels deep,
        so the anchor is the first non-``CoreStep`` ancestor, not the immediate
        parent. It is also not necessarily the job an incoming result event is
        keyed on: in the template chain the tree hangs off the third storage
        job while the event names the root.

        ``None`` when the step has no parent at all — the reconcile builds such
        a step in its own heal path — which callers must read as "there is
        nothing to save", never as an error.
        """
        node = self._parent
        while isinstance(node, CoreStep):
            node = node._parent
        return node

    def unbuilt_knot_steps(self, unbuilt_status=JobStatus.FAILED):
        """This step's knot children's finalize steps, for children that will
        never be built.

        A knot child is created when this step runs — but only on a chain that
        is still succeeding. On one that failed or was cancelled the child is
        never created, and everything the chain declared BELOW it stays a raw
        dict that no walk can reach: in a template creation that includes the
        terminal ``update_status``, the one step that maps FAILED/CANCELED onto
        ``Failed`` for the desktop, the template and both storage rows.

        The subtree is already carried here in full — the raw child dict keeps
        its own ``dependents`` — so nothing needs materialising in Redis to
        reach it. It is serialised with the same deterministic ids the real
        child would have produced, so a step has ONE identity whether it was
        reached as metadata or as a job.

        Only children that do not exist are returned, using the same existence
        check that decides whether to create one, so the two can never both
        claim the same member. Callers must ask only when the chain is dead: on
        a live chain a missing child means "not created YET", and running its
        finalizers would settle rows for work that is about to happen.

        The nodes are kept ON this node the first time they are built, so a
        step reached this way can be marked like any other and the mark lands
        in the anchor's meta with the rest. Without that a step would run and
        still read as never having run, which is the state the reconcile treats
        as work in progress.

        ``unbuilt_status`` is what the child's non-execution reports as. These
        steps hang off the CHILD, not off this step, and every handler decides
        what to do from its own dependency's status — so a step here must see
        the child that will never run, not the step that carried it. Reporting
        this step instead would answer "finished" whenever the first half of
        the chain succeeded, and the step would run its success body for a disk
        operation that never happened.
        """
        # Stands in for the knot child that will never exist: ``job_status``
        # says "this member did not run", which is what the steps behind it
        # read. It also carries this tree's anchor identity, because the child
        # has no meta of its own — these nodes live in the anchor's, and that
        # is where their marks have to be saved.
        anchor = self.anchor
        never_ran = SimpleNamespace(
            job_status=unbuilt_status,
            id=getattr(anchor, "id", None),
            job=getattr(anchor, "job", None),
        )
        steps = []
        child_ids = self.knot_child_ids
        materialized = self._node.setdefault("unbuilt_knot_finalize", {})
        for index, child in enumerate(self.storage_dependents):
            child_id = child_ids[index]
            try:
                if Job.exists(child_id, connection=self._redis):
                    # It is a real member with its own finalize tree; whoever
                    # walks jobs reaches it. Drop any view built while it did
                    # not exist so one member never has two representations.
                    materialized.pop(child_id, None)
                    continue
            except Exception:
                # Unreadable is not "absent": leave the child to the reader that
                # can see it rather than inventing a second copy of it here.
                continue
            nodes = materialized.get(child_id)
            if nodes is None:
                nodes = []
                for dependent in child.get("dependents") or []:
                    if not str(dependent.get("queue", "")).startswith("core"):
                        continue
                    nodes.append(
                        _serialize_finalize(
                            dependent,
                            child_id,
                            len(nodes),
                            child.get("user_id", self.user_id),
                            child.get("category_id", self.category_id),
                        )
                    )
                materialized[child_id] = nodes
            steps.extend(CoreStep(node, never_ran, self._redis) for node in nodes)
        return steps

    def mark(self, ok):
        """Record this step's outcome so a later sibling/child reads the right
        ``depending_status`` and ``Task.pending`` stops counting it as active."""
        self._node["status"] = "finished" if ok else "failed"

    @property
    def dependencies(self):
        return [self._parent] if self._parent is not None else []

    @property
    def dependents(self):
        return [
            CoreStep(child, self, self._redis)
            for child in self._node.get("core_finalize", []) or []
        ]

    @property
    def job_status(self):
        status = self._node.get("status")
        if status == "finished":
            return JobStatus.FINISHED
        if status == "failed":
            return JobStatus.FAILED
        if self._parent is not None and self._parent.job_status in _TERMINAL_STATUSES:
            return JobStatus.QUEUED
        return JobStatus.DEFERRED

    @property
    def depending_status(self):
        return global_status(self.dependencies)

    @property
    def status(self):
        return global_status([self._parent, self] if self._parent else [self])

    @property
    def pending(self):
        return self.job_status in (
            JobStatus.STARTED,
            JobStatus.SCHEDULED,
            JobStatus.QUEUED,
            JobStatus.DEFERRED,
        )

    @property
    def progress(self):
        return 1.0 if self.job_status == JobStatus.FINISHED else 0.0

    def to_dict(self, filter=None):
        """Mirror :meth:`Task.to_dict` for a finalize step so the admin Tasks
        view renders a metadata chain identically to a legacy rq one."""
        if not filter:
            filter = []
        filter.append(self.id)
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category_id": self.category_id,
            "queue": self.queue,
            "position": self.position,
            "task": self.task,
            "kwargs": self.kwargs,
            "result": self.result,
            "exc_info": self.exc_info,
            "depending_status": self.depending_status,
            "status": self.status,
            "pending": self.pending,
            "job_status": self.job_status,
            "progress": self.progress,
            "args": list(self.args),
            "dependencies": [],
            "dependents": [
                dependent.to_dict(filter=filter)
                for dependent in self.dependents
                if dependent.id not in filter
            ],
        }


class Task(RedisBase):
    """
    Manage tasks with RQ backend.

    Use constructor with keyword arguments to create new Task or update an
    existing one using id keyword. Use constructor with id as first argument
    to create an object representing an existing Task.
    """

    def __init__(self, *args, **kwargs):
        if args:
            kwargs["id"] = args[0]
        if "id" in kwargs:
            self.job = Job.fetch(kwargs["id"], connection=self._redis)
            # An existing task is, by definition, already on (or past) its
            # queue. Record that so a stray ``.enqueue()`` is a safe no-op.
            self._queue_name = self.job.origin
            self._enqueued = True
        else:
            if "task" not in kwargs:
                raise TypeError(
                    "Provide task to create a new task or id keyword to get an existing one"
                )
            kwargs.setdefault("job_kwargs", {}).setdefault("connection", self._redis)
            kwargs["job_kwargs"].setdefault(
                "result_ttl",
                os.environ.get(
                    "REDIS_TASK_RESULT_TTL",
                    2592000,  # 30 days
                ),
            )
            meta = kwargs["job_kwargs"].setdefault("meta", {})
            meta.setdefault("user_id", kwargs.get("user_id"))
            # Owner category, threaded so the storage worker can fair-schedule
            # bulk/background throughput per category (Phase 2). None for a task
            # with no resolvable owner (system maintenance / deleted owner).
            meta.setdefault("category_id", kwargs.get("category_id"))
            # Give every task an explicit, action-appropriate job_timeout so a
            # long-running op (download / convert / sparsify / move) is not
            # killed by RQ's 180 s Queue.DEFAULT_TIMEOUT mid-flight. A callsite
            # that knows the disk/file size can still pass its own size-derived
            # ``timeout`` in job_kwargs -- setdefault keeps it.
            kwargs["job_kwargs"].setdefault(
                "timeout", job_timeout_for(kwargs.get("task"))
            )
            dependencies = []
            for dependency in kwargs.get("dependencies", []):
                task = Task(**dependency)
                dependencies.append(task)
            register_dependencies(kwargs["job_kwargs"], dependencies)
            self.job = Job.create(
                f"task.{kwargs.get('task')}",
                *kwargs.get("job_args", []),
                **kwargs.get("job_kwargs", {}),
            )
            if kwargs.get("queue", "").startswith("core."):
                kwargs.setdefault("retry", 3)
                kwargs.setdefault("retry_intervals", 15)
            if isinstance(kwargs.get("retry"), int) and kwargs["retry"] > 0:
                retry = Retry(
                    max=int(kwargs["retry"]),
                    interval=kwargs.get("retry_intervals", 0),
                )
                self.job.retries_left = retry.max
                self.job.retry_intervals = retry.intervals

            self.job.save()
            for dependent in kwargs.get("dependents", []):
                dependent.setdefault("user_id", kwargs.get("user_id"))
                dependent.setdefault("category_id", kwargs.get("category_id"))
                # A ``core`` finalize dependent is ALWAYS metadata, never a rq job
                # on the consumerless ``core`` queue; storage dependents keep the rq
                # path. The change-handler runs it off ``meta["core_finalize"]``.
                if str(dependent.get("queue", "")).startswith("core"):
                    finalize = self.job.meta.setdefault("core_finalize", [])
                    node = _serialize_finalize(
                        dependent,
                        self.job.id,
                        len(finalize),
                        kwargs.get("user_id"),
                        kwargs.get("category_id"),
                    )
                    finalize.append(node)
                    # Declare the edge to every knot child the tree carries, now,
                    # while this job is the only real one that can hold it. The
                    # children are created later (when their step runs) or never
                    # (on a chain that fails or is cancelled), so linking them at
                    # creation time would leave them unreachable in exactly the
                    # states where reaching them matters most. A declared id that
                    # cannot be fetched is skipped by every reader, so declaring
                    # early costs nothing.
                    self.job.meta.setdefault("dependent_ids", []).extend(
                        _knot_child_ids(node)
                    )
                    continue
                dependent.setdefault("retry", kwargs.get("retry", 0))
                dependent.setdefault(
                    "retry_intervals", kwargs.get("retry_intervals", 0)
                )
                register_dependencies(dependent.setdefault("job_kwargs", {}), [self])
                task = Task(**dependent)
                # A dependent must NOT run when its dependency failed (e.g.
                # qemu_img_info after a failed create — nothing to inspect);
                # finalize dependents are run by the change-handler stream
                # consumer regardless of RQ state. So do not set
                # allow_dependency_failures here — the plural is the real
                # attribute, and setting it True would wrongly run storage
                # dependents after a failure.
                task.job.save()
                self.job.meta.setdefault("dependent_ids", []).append(task.id)
            self.job.save_meta()
            # The legacy auto-feedback enqueue on ``core.feedback`` (one
            # follow-up job per root Task) was retired in MR-2 of the
            # core_worker retirement. The storage worker now XADDs the
            # equivalent ``kind=result`` event to ``stream:task-results``
            # when each RQ task completes, and isard-change-handler is
            # the canonical consumer that fans the SocketIO ``task``
            # event out (and runs the chain-handler bodies that used to
            # live on core_worker). See change-handler's
            # ``task_results.feedback.emit_task_feedback``.
            #
            # The root job is created + saved (id known, dependents created
            # and DEFERRED on it) but enqueuing it is what lets a worker pick
            # it up. Callers that must register the task somewhere BEFORE it
            # can run (see ``RecycleBin.delete_storage``) pass
            # ``enqueue=False`` and call ``.enqueue()`` after registering, so
            # the worker can never complete the task before it is registered.
            self._queue_name = kwargs.get("queue", "default")
            self._enqueued = False
            if kwargs.get("enqueue", True):
                self.enqueue()

    def enqueue(self):
        """Place the (already created + saved) root job on its queue.

        Split out of ``__init__`` so a caller can do
        ``create -> register -> enqueue`` and close the enqueue-before-register
        race that left recycle-bin entries stuck in ``deleting``: the storage
        worker cannot run — and change-handler cannot run the completion chain
        — before the task is registered.

        Idempotent: a second call (or a call on a task built the default,
        already-enqueued way, or hydrated from an id) is a no-op.

        :return: self, so callers can chain ``Task(..., enqueue=False).enqueue()``
        :rtype: Task
        """
        if getattr(self, "_enqueued", True):
            return self
        _await_result_stream_admission(self._redis, self._queue_name)
        self.job = Queue(self._queue_name, connection=self._redis).enqueue_job(self.job)
        self._enqueued = True
        return self

    @property
    def id(self):
        return self.job.id

    @property
    def user_id(self):
        return self.job.meta.get("user_id")

    @property
    def category_id(self):
        return self.job.meta.get("category_id")

    @property
    def queue(self):
        return self.job.origin

    @property
    def position(self):
        return self.job.get_position()

    @property
    def task(self):
        return self.job.func_name.rsplit(".", 1)[-1]

    @property
    def args(self):
        return self.job.args

    @property
    def kwargs(self):
        return self.job.kwargs

    @property
    def result(self):
        return self.job.result

    @property
    def exc_info(self):
        return self.job.exc_info

    @property
    @cached(SynchronizedTTLCache(maxsize=10, ttl=0.01))
    def dependencies(self):
        """
        Get a list of tasks that should be done before this Task.

        :return: Tasks that this Task depends
        :rtype: list
        """
        return tasks_from_ids(self.job.meta.get("dependency_ids", []))

    @property
    @cached(SynchronizedTTLCache(maxsize=10, ttl=0.01))
    def dependents(self):
        """
        List of tasks that should be done after this Task.

        Storage dependents are real rq jobs (``meta["dependent_ids"]``, e.g.
        ``qemu_img_info_backing_chain``); ``core`` finalize steps are
        :class:`CoreStep` views over ``meta["core_finalize"]`` — never rq jobs on
        the consumerless ``core`` queue. The two coexist in a chain and never
        overlap; returning both is the full dependent set.

        :return: Tasks that depends of this Task
        :rtype: list
        """
        storage_dependents = tasks_from_ids(self.job.meta.get("dependent_ids", []))
        core_finalize = [
            CoreStep(node, self, self._redis)
            for node in (self.job.meta.get("core_finalize") or [])
        ]
        return storage_dependents + core_finalize

    @property
    def _chain(self):
        """
        Get the Task and related tasks by dependencies.

        :return: the Task and related by dependencies
        :rtype: list
        """
        return self.dependencies + [self] + self.dependents

    @property
    def depending_status(self):
        """
        Get global status of depending tasks.

        :return: Status
        :rtype: str
        """
        return global_status(self.dependencies)

    @property
    def status(self):
        """
        Get global status of Task including the status of tasks that are related by dependencies.

        :return: Status
        :rtype: str
        """
        return global_status(self._chain)

    @property
    def pending(self):
        """
        Get True if the task (or anything in its chain) is still actively
        running, otherwise return False.

        Walks the chain (dependencies + self + dependents) and treats a job
        as pending only if real work remains:

        * ``STARTED`` / ``SCHEDULED`` / ``QUEUED`` -> a worker has it or will
          pick it up imminently -> pending.
        * ``DEFERRED`` -> only pending while it is *legitimately waiting* on a
          dependency that has not finished yet. A ``DEFERRED`` job whose
          dependencies have all settled (finished/failed/etc.) was never
          re-enqueued -- e.g. its finalize crashed -- and would stay
          ``DEFERRED`` forever. That is an orphan, not active work, so it must
          NOT block the storage indefinitely (false-positive 428
          ``storage_pending_task``).

        :return: True if pending otherwise False
        :rtype: bool
        """
        active = (
            JobStatus.STARTED,
            JobStatus.SCHEDULED,
            JobStatus.QUEUED,
        )
        for task in self._chain:
            job_status = task.job_status
            if job_status in active:
                return True
            if job_status == JobStatus.DEFERRED and task.depending_status in (
                JobStatus.STARTED,
                JobStatus.SCHEDULED,
                JobStatus.QUEUED,
                JobStatus.DEFERRED,
            ):
                return True
        return False

    @property
    @cached(SynchronizedTTLCache(maxsize=10, ttl=0.01))
    def job_status(self):
        """Cached Job status."""
        return self.job.get_status()

    @property
    def progress(self):
        """
        Get progress of task including the progress of jobs related by dependencies.

        :return: Progress percentage as decimal
        :rtype: float
        """
        if self.status == JobStatus.CANCELED:
            return 0
        done = 0
        todo = 0
        for task in self._chain:
            timeout = task.job.timeout if task.job.timeout else Queue.DEFAULT_TIMEOUT
            done += (
                1
                if task.job_status == JobStatus.FINISHED
                else task.job.meta.get("progress", 0)
            ) * timeout
            todo += timeout
        return done / todo

    def cancel(self):
        """Settle this Task's whole chain as cancelled.

        Cancelling any member cancels the entire chain — every job linked to
        it through dependencies or dependents, leaves first — and promotes
        nothing. For each member still running this:

        * publishes a ``task:cancel:<id>`` pub/sub signal so a long-running
          body using
          :class:`isardvdi_common.helpers.task_cancel.TaskCancelWatcher`
          shuts itself down cooperatively (RQ can only drop *queued* jobs),
        * cancels the RQ job **without enqueuing dependents**, and
        * stamps ``ended_at`` so the chain can later be aged out.

        ``enqueue_dependents=True`` is what this method used to pass, and it
        is the defect this shape exists to prevent: RQ moved every finalize
        dependent DEFERRED → QUEUED onto the ``core`` queue, which no worker
        consumes since the core_worker retirement. Those jobs stay QUEUED
        forever, ``Task.pending`` counts them as active work, and
        ``Storage.create_task`` then rejects every later operation on that
        storage with ``storage_pending_task`` — permanently. It also
        contradicted the chain contract in :func:`register_dependencies`: a
        dependent must not run when its dependency did not succeed.

        Members already in a terminal state keep their history (a finished
        step is not rewritten to cancelled), and a chain cancelled twice is a
        no-op rather than an error.
        """
        from isardvdi_common.helpers.task_cancel import request_task_cancel

        closure = _chain_closure(self.job, self._redis)
        for job in _closure_leaves_first(closure):
            try:
                if job.get_status(refresh=True) in _TERMINAL_STATUSES:
                    continue
            except Exception:
                # Unreadable status: fall through and try to cancel anyway.
                pass
            try:
                request_task_cancel(job.id)
            except Exception:
                # Pub/sub is best-effort — the RQ-level cancel below still
                # handles queued jobs; persistent row flags remain the
                # back-up signal.
                pass
            try:
                job.cancel(enqueue_dependents=False)
            except InvalidJobOperation:
                # Already cancelled, or cancelled concurrently between our
                # status read and here. Nothing to do.
                continue
            except NoSuchJobError:
                continue
            except Exception:
                log.exception("task cancel: could not cancel %s", job.id)
                continue
            _stamp_ended_at(self._redis, job.id)
            # Record the cancel where it is decided, on the member itself. rq
            # may still run this job if a worker had already dequeued it, and
            # the worker will then rewrite its status to finished; the record
            # is what lets the completion it publishes be recognised as a
            # cancelled member's rather than a healthy one's.
            mark_canceled(self._redis, job.id)

        # The change-handler runs the finalize handlers, and a cancelled job
        # publishes no result of its own — announce the chain so its cancelled
        # finalize runs now instead of waiting for a reconcile pass.
        for root in _closure_roots(closure):
            try:
                publish_canceled_event(
                    self._redis,
                    task_id=root.id,
                    task_name=(root.func_name or "").rsplit(".", 1)[-1],
                    queue=root.origin,
                )
            except Exception:
                log.debug("task cancel: could not announce cancel of %s", root.id)

    def to_dict(self, filter=None):
        """
        Returns Task and related ones as a dictionary.

        :param filter: List of Task ids to hide
        :type filter: list
        :return: Task as dictionary
        :rtype: dict
        """

        if not filter:
            filter = []
        filter.append(self.id)
        return {
            **{
                name: getattr(self, name)
                for name in dir(self)
                if name
                not in [
                    "dict",
                    "args",
                    "job",
                    "_chain",
                    "dependencies",
                    "dependents",
                    "storage_id",
                ]
                # getattr with a default: instance-only attributes (e.g.
                # _enqueued / _queue_name set in __init__) appear in dir(self)
                # but are NOT class attributes, so a bare getattr(self.__class__,
                # name) raises AttributeError and breaks the whole dict. None is
                # not a property, so they are simply skipped.
                and isinstance(getattr(self.__class__, name, None), property)
            },
            "args": [
                arg.to_dict() if hasattr(arg, "to_dict") else arg for arg in self.args
            ],
            "dependencies": [
                dependency.to_dict(filter=filter)
                for dependency in self.dependencies
                if dependency.id not in filter
            ],
            "dependents": [
                dependent.to_dict(filter=filter)
                for dependent in self.dependents
                if dependent.id not in filter
            ],
        }

    @classmethod
    def exists(cls, task_id):
        """
        Check if a task ID exists.

        :param task_id: Document ID
        :type task_id: str
        :return: True if exists, False otherwise.
        :rtype: bool
        """
        return Job.exists(task_id, connection=cls._redis)

    @classmethod
    def _purge_dangling_ids(cls, job_ids, source):
        """Drop ids whose RQ job hash is gone, without materialising the rest.

        Same self-clearing purpose as :meth:`_tasks_from_source_ids`, for the
        case where the caller does not want these tasks back: an existence
        check per id instead of fetching, deserialising and wrapping every live
        job just to throw it away.
        """
        for job_id in job_ids:
            if cls.exists(job_id):
                continue
            log.warning(
                "task: purging dangling job id %s from %s (no RQ job)",
                job_id,
                type(source).__name__,
            )
            try:
                source.remove(job_id)
            except NotImplementedError:
                continue
            except Exception:
                log.exception("task: could not purge dangling job id %s", job_id)

    @classmethod
    def _tasks_from_source_ids(cls, job_ids, source):
        """Materialize ``Task`` objects from job ids belonging to one source (an
        RQ ``Queue`` list or a ``*_job_registry``), tolerating dangling refs.

        A queue list or registry zset can keep an id whose underlying RQ job
        hash has already been evicted from Redis (e.g. a worker/redis restart
        mid-chain during an upgrade). ``Task(id=...)`` then raises
        ``NoSuchJobError`` and, in a plain comprehension, aborts the *entire*
        listing — which breaks every caller (the change-handler reconcile
        self-heal, :meth:`get_failed_storage_tasks`, ...) and never recovers,
        because the dangling reference is exactly what those passes exist to
        clear. Skip the orphan and purge it from ``source`` so it self-clears
        instead of re-raising every cycle.

        Only ``NoSuchJobError`` (a provably missing job) is treated as an
        orphan; any other error (e.g. a transient redis ``ConnectionError``)
        propagates so the caller fails the whole pass rather than purge live
        work on a hiccup.
        """
        tasks = []
        for job_id in job_ids:
            try:
                tasks.append(cls(id=job_id))
            except NoSuchJobError:
                log.warning(
                    "task: purging dangling job id %s from %s (no RQ job)",
                    job_id,
                    type(source).__name__,
                )
                try:
                    source.remove(job_id)
                except NotImplementedError:
                    # A few RQ registries — e.g. ``StartedJobRegistry``, whose
                    # members are composite ``{job_id}:{execution_id}`` — don't
                    # support bare-id removal. Their own ``get_job_ids()``
                    # cleanup sweeps expired entries, so leave the orphan for RQ
                    # rather than spam an exception traceback every pass.
                    log.debug(
                        "task: %s does not support removing %s; leaving it for "
                        "RQ's own registry cleanup",
                        type(source).__name__,
                        job_id,
                    )
                except Exception:
                    log.exception("task: could not purge dangling job id %s", job_id)
        return tasks

    @classmethod
    def get_all(cls):
        """
        Get all tasks.

        :return: Task objects
        :rtype: list
        """
        tasks = []
        for queue in Queue.all(connection=cls._redis):
            tasks.extend(cls._tasks_from_source_ids(queue.job_ids, queue))
            for status in (
                "failed",
                "started",
                "finished",
                "deferred",
                "scheduled",
                "canceled",
            ):
                registry = getattr(queue, f"{status}_job_registry")
                tasks.extend(
                    cls._tasks_from_source_ids(registry.get_job_ids(), registry)
                )
        return tasks

    @classmethod
    def get_by_status(cls, *statuses):
        """
        Get tasks by status.

        :param statuses: Task status
        :type statuses: str
        :return: Task objects
        :rtype: list
        """
        for status in statuses:
            if status not in JobStatus:
                raise ValueError(f"Invalid status: {status}")

        # QUEUED jobs live on the queue list itself, not in a registry, so they
        # are only read when they were actually asked for. Reading them
        # unconditionally returned the ENTIRE queued backlog of every queue on
        # every call - one hydration per id - which on a busy install turned a
        # periodic scan for a handful of orphans into tens of thousands of
        # fetches, and pushed the work that scan drives minutes late.
        wants_queued = JobStatus.QUEUED.value in [str(s) for s in statuses]
        tasks = []
        for queue in Queue.all(connection=cls._redis):
            if wants_queued:
                tasks.extend(cls._tasks_from_source_ids(queue.job_ids, queue))
            else:
                # Still clear dangling ids off the list — that is what stops an
                # evicted job from breaking every later pass — but without
                # materialising the live ones nobody asked for.
                cls._purge_dangling_ids(queue.job_ids, queue)
            for status in statuses:
                if status == JobStatus.QUEUED.value:
                    continue
                registry = getattr(queue, f"{status}_job_registry")
                tasks.extend(
                    cls._tasks_from_source_ids(registry.get_job_ids(), registry)
                )
        return tasks

    @classmethod
    def get_by_user(cls, user_id):
        """
        Get user tasks.

        :param user_id: User ID
        :type user_id: str
        :return: User Task objects
        :rtype: list
        """
        return [task for task in cls.get_all() if task.user_id == user_id]

    def retry(self) -> None:
        """Re-enqueue this task's own job on the lane it came from.

        Retrying is a producer action, so it takes the same mandatory consumer
        gate as ``create_task``: rq re-enqueues on ``job.origin`` unconditionally,
        so a job whose pool lost its workers would move from ``failed`` (listed,
        retryable) to ``queued`` on a lane nothing serves and disappear. The lane
        is NOT re-resolved — the job's arguments are paths on its own pool, so
        another pool's worker could not run it.

        ``Job.requeue`` is ``FailedJobRegistry``-driven and raises
        ``InvalidJobOperation`` when its ``ZREM`` removes nothing. A chain step
        marked FAILED with ``Job.set_status`` (the change-handler's in-process
        finalize path) only ever got the status hash field, never registry
        membership, so requeueing it always raised. Fall back to enqueuing the
        job directly, clearing the previous run's outcome exactly as rq's own
        registry does after its ZREM.
        """
        from isardvdi_common.lib import queue_coverage

        queue = self.job.origin
        queue_coverage.check_no_consumer(self._redis, queue)
        try:
            self.job.requeue()
        except InvalidJobOperation:
            job = self.job
            job.started_at = None
            job.ended_at = None
            job.save()
            Queue(queue, connection=self._redis)._enqueue_job(job)

    @property
    def storage_id(self):
        """
        Check if any storage has this task.

        :return: True if the storage has any task, False otherwise
        :rtype: bool
        """
        try:
            from .storage import Storage  # To avoid circular import

            return Storage.get_from_task_id(self.id)
        except Exception:
            return None

    @classmethod
    def filter_last_tasks(cls, task_ids: list[str]) -> list["Task"]:
        """
        Get the tasks that are the last task of a storage from a list of task IDs.

        :param task_ids: List of task IDs to filter
        """
        try:
            from .storage import Storage  # To avoid circular import

            tasks = []
            for task in Storage.get_storage_ids_from_task_ids(task_ids):
                tasks.append(cls(task["task_id"]))

            return tasks
        except Exception:
            return []

    @classmethod
    def get_failed_storage_tasks(cls) -> list["Task"]:
        """
        Get failed tasks that are the last task of a storage.
        """
        task_ids = [task.id for task in cls.get_by_status(JobStatus.FAILED.value)]

        return cls.filter_last_tasks(task_ids)
