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

import os

from api.libv2.redis_base import RedisBase
from rq import Queue
from rq.job import Dependency, Job, JobStatus


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
            if task.job.get_status() == status:
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
        else:
            if "task" not in kwargs:
                raise TypeError(
                    "Provide task to create a new task or id keyword to get an existing one"
                )
            kwargs.setdefault("job_kwargs", {}).setdefault("connection", self._redis)
            kwargs["job_kwargs"].setdefault("result_ttl", -1)
            kwargs["job_kwargs"].setdefault("meta", {}).setdefault(
                "user_id", kwargs.get("user_id")
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
            self.job.save()
            for dependent in kwargs.get("dependents", []):
                register_dependencies(dependent.setdefault("job_kwargs", {}), [self])
                task = Task(**dependent)
                task.job.allow_dependency_failure = True
                task.job.save()
                self.job.meta.setdefault("dependent_ids", []).append(task.id)
            self.job.save_meta()
            if "user_id" in kwargs:
                for task in self._chain:
                    Queue("api", connection=self._redis).enqueue(
                        "task.feedback",
                        result_ttl=0,
                        depends_on=Dependency(jobs=[task.job], allow_failure=True),
                        kwargs={"task_id": self.id},
                    )
            self.job = Queue(
                kwargs.get("queue", "default"), connection=self._redis
            ).enqueue_job(self.job)

    @property
    def id(self):
        return self.job.id

    @property
    def user_id(self):
        return self.job.meta.get("user_id")

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
    def dependencies(self):
        """
        Get a list of tasks that should be done before this Task.

        :return: Tasks that this Task depends
        :rtype: list
        """
        return tasks_from_ids(self.job.meta.get("dependency_ids", []))

    @property
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
    def progress(self):
        """
        Get progress of task including the progress of jobs related by dependencies.

        :return: Progress percentage as decimal
        :rtype: float
        """
        done = 0
        todo = 0
        for task in self._chain:
            timeout = task.job.timeout if task.job.timeout else Queue.DEFAULT_TIMEOUT
            done += (
                1
                if task.job.get_status() == JobStatus.FINISHED
                else task.job.meta.get("progress", 0)
            ) * timeout
            todo += timeout
        return done / todo

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
                not in ["dict", "args", "job", "_chain", "dependencies", "dependents"]
                and isinstance(getattr(self.__class__, name), property)
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
    def get_all(cls):
        """
        Get all tasks.

        :return: Task objects
        :rtype: list
        """
        job_ids = []
        for queue in Queue.all(connection=cls._redis):
            job_ids.extend(queue.job_ids)
            for status in (
                "failed",
                "started",
                "finished",
                "deferred",
                "scheduled",
                "canceled",
            ):
                job_ids.extend(getattr(queue, f"{status}_job_registry").get_job_ids())
        return [Task(id=job_id) for job_id in job_ids]

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
