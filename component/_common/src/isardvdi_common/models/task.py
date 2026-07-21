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

from cachetools import cached
from isardvdi_common.connections.redis_base import RedisBase
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.helpers.task_timeouts import job_timeout_for
from rq import Queue, Retry
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus


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
        if Task.exists(task_id):
            tasks.append(Task(task_id))
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
            kwargs["job_kwargs"].setdefault("meta", {}).setdefault(
                "user_id", kwargs.get("user_id")
            )
            # Owner category, threaded so the storage worker can fair-schedule
            # bulk/background throughput per category (Phase 2). None for a task
            # with no resolvable owner (system maintenance / deleted owner).
            kwargs["job_kwargs"].setdefault("meta", {}).setdefault(
                "category_id", kwargs.get("category_id")
            )
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
                dependent.setdefault("retry", kwargs.get("retry", 0))
                dependent.setdefault(
                    "retry_intervals", kwargs.get("retry_intervals", 0)
                )
                register_dependencies(dependent.setdefault("job_kwargs", {}), [self])
                task = Task(**dependent)
                task.job.allow_dependency_failure = True
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

        :return: Tasks that depends of this Task
        :rtype: list
        """
        return tasks_from_ids(self.job.meta.get("dependent_ids", []))

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
        """Cancel this Task and the dependencies of this Task.

        This both:

        * tells RQ to drop the queued jobs (no effect on already-running
          ones — that's the engine's limitation), and
        * publishes a ``task:cancel:<id>`` pub/sub signal so any
          long-running task body using
          :class:`isardvdi_common.helpers.task_cancel.TaskCancelWatcher`
          can shut itself down cooperatively.
        """
        from isardvdi_common.helpers.task_cancel import request_task_cancel

        for dependency in self.dependencies:
            dependency.cancel()
        try:
            request_task_cancel(self.id)
        except Exception:
            # Pub/sub is best-effort — RQ-level cancel below still
            # handles queued jobs; persistent row flags remain the
            # back-up signal.
            pass
        self.job.cancel(enqueue_dependents=True)

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

        tasks = []
        for queue in Queue.all(connection=cls._redis):
            tasks.extend(cls._tasks_from_source_ids(queue.job_ids, queue))
            for status in statuses:
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
        """
        Retry task.

        :return: Task object
        :rtype: Task
        """
        self.job.requeue()

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
