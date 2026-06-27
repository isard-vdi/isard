#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import os
import time
import traceback
from typing import Optional

from api.services.error import Error
from cachetools import cached
from isardvdi_common.connections.redis_base import RedisBase
from isardvdi_common.connections.redis_urls import RQ_DB
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.models.config import Config
from redis import Redis
from rq import Queue
from rq.job import Job

QUEUE_REGISTRIES = [
    "queued",
    "started",
    "finished",
    "failed",
    "deferred",
    "scheduled",
    "canceled",
]

queues_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
queue_jobs_cache = SynchronizedTTLCache(maxsize=20, ttl=5)
consumers_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
subscribers_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
workers_cache = SynchronizedTTLCache(maxsize=1, ttl=5)


def clear_queue_data_caches() -> None:
    """Invalidate queue-data caches after admin mutations that change job counts."""
    queues_cache.clear()
    queue_jobs_cache.clear()


def _connect_redis() -> Redis:
    return Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        password=os.environ.get("REDIS_PASSWORD", ""),
        db=RQ_DB,
    )


class AdminQueuesService:
    """Service for admin queue management operations."""

    @staticmethod
    @cached(queues_cache)
    def get_queues() -> list[dict]:
        """Get all queues with job counts."""
        with _connect_redis() as redis_conn:
            queues = Queue.all(connection=redis_conn)
        data = []
        for queue in queues:
            q = AdminQueuesService._get_queue_jobs(queue.name)
            q["id"] = queue.name
            data.append(q)
        return data

    @staticmethod
    @cached(queue_jobs_cache)
    def _get_queue_jobs(queue_name: str) -> dict:
        """Get job counts for a specific queue."""
        with _connect_redis() as redis_conn:
            queue = Queue(queue_name, connection=redis_conn)
        return {
            "queued": queue.count,
            "started": queue.started_job_registry.count,
            "finished": queue.finished_job_registry.count,
            "failed": queue.failed_job_registry.count,
            "deferred": queue.deferred_job_registry.count,
            "scheduled": queue.scheduled_job_registry.count,
            "canceled": queue.canceled_job_registry.count,
        }

    @staticmethod
    @cached(consumers_cache)
    def get_consumers() -> list[dict]:
        """Get workers with their subscribers."""
        return AdminQueuesService._workers_with_subscribers()

    @staticmethod
    @cached(subscribers_cache)
    def _subscribers() -> list[dict]:
        with _connect_redis() as redis_conn:
            subscribers = redis_conn.pubsub_channels()
        s = []
        for subscriber in subscribers:
            if ":" not in str(subscriber):
                continue
            s.append(
                {
                    "id": str(subscriber).split(":")[3].split("'")[0],
                    "queue": str(subscriber).split(":")[2],
                }
            )
        return s

    @staticmethod
    @cached(workers_cache)
    def _workers() -> list[dict]:
        with _connect_redis() as redis_conn:
            workers = redis_conn.keys("rq:workers:*")
        w = []
        for worker in workers:
            try:
                if str(worker).split(":")[2].split(".")[0].split("'")[0] != "storage":
                    continue
                w.append(
                    {
                        "id": str(worker).split(":")[2].split("'")[0],
                        "queue": str(worker).split(":")[2].split(".")[0].split("'")[0],
                        "queue_id": (
                            str(worker).split(":")[2].split(".")[1]
                            if len(str(worker).split(":")[2].split(".")) > 1
                            else None
                        ),
                        "priority_id": (
                            str(worker).split(":")[2].split(".")[2].split("'")[0]
                            if len(str(worker).split(":")[2].split(".")) > 2
                            else None
                        ),
                    }
                )
            except Exception:
                pass
        for worker in w:
            if worker["priority_id"] is None:
                worker["priority"] = None
            if worker["priority_id"] == "high":
                worker["priority"] = 3
            if worker["priority_id"] == "default":
                worker["priority"] = 2
            if worker["priority_id"] == "low":
                worker["priority"] = 1
        return w

    @staticmethod
    def _workers_with_subscribers() -> list[dict]:
        w = AdminQueuesService._workers()
        s = AdminQueuesService._subscribers()
        for worker in w:
            worker["subscribers"] = [
                subs["id"] for subs in s if subs["queue"] == worker["queue"]
            ]
            if not len(worker["subscribers"]):
                worker["status"] = "error"
            else:
                worker["status"] = "ok"
        return w

    @staticmethod
    def get_old_tasks(older_than: int) -> list:
        """Get old task keys."""
        return AdminQueuesService._get_old_jobs(older_than)

    @staticmethod
    def _get_all_queue_job_ids(
        queue_name: str, registries: Optional[list[str]] = None
    ) -> list[str]:
        if registries is None:
            registries = QUEUE_REGISTRIES
        with _connect_redis() as redis_conn:
            queue = Queue(queue_name, connection=redis_conn)
        registry_mapping = {
            "queued": queue,
            "started": queue.started_job_registry,
            "finished": queue.finished_job_registry,
            "failed": queue.failed_job_registry,
            "deferred": queue.deferred_job_registry,
            "scheduled": queue.scheduled_job_registry,
            "canceled": queue.canceled_job_registry,
        }
        registry_objects = [registry_mapping[reg] for reg in registries]
        job_ids = []
        for registry in registry_objects:
            job_ids.extend(registry.get_job_ids())
        return job_ids

    @staticmethod
    def _get_old_jobs(
        older_than: int,
        batch_size: int = 5000,
        rtype: str = "key",
        registries: Optional[list[str]] = None,
    ) -> list:
        if registries is None:
            registries = ["finished"]
        for reg in registries:
            if reg not in QUEUE_REGISTRIES:
                raise Error(
                    "bad_request",
                    f"Invalid registry: {reg}. Valid registries are: {QUEUE_REGISTRIES}",
                )
            if reg in ["queued", "started", "scheduled"]:
                raise Error(
                    "bad_request",
                    f"Registry {reg} is not valid for this operation.",
                )
        time_cutoff = time.time() - older_than
        with _connect_redis() as redis_conn:
            queues = Queue.all(connection=redis_conn)
        finished_jobs = []
        for q in queues:
            finished_jobs.extend(
                AdminQueuesService._get_all_queue_job_ids(q.name, registries)
            )
        old_keys = []
        for i in range(0, len(finished_jobs), batch_size):
            batch_ids = finished_jobs[i : i + batch_size]
            with _connect_redis() as redis_conn:
                jobs = Job.fetch_many(batch_ids, connection=redis_conn)
            for job in jobs:
                if job is None:
                    continue
                if job.ended_at is None or job.ended_at.timestamp() < time_cutoff:
                    if rtype == "key":
                        old_keys.append(job.key.decode())
                    elif rtype == "id":
                        old_keys.append(job.id)
                    elif rtype == "job":
                        old_keys.append(job)
        return old_keys

    @staticmethod
    def _delete_jobs(jobs: list) -> tuple[list[str], list[str]]:
        ok = []
        errors = []
        for job in jobs:
            try:
                job.delete(delete_dependents=True)
            except Exception:
                errors.append(job.id)
            else:
                ok.append(job.id)
        return ok, errors

    @staticmethod
    def delete_old_tasks(older_than: int) -> dict:
        """Delete old tasks older than given seconds."""
        old_jobs = AdminQueuesService._get_old_jobs(older_than, rtype="job")
        delete_ok, delete_errors = AdminQueuesService._delete_jobs(old_jobs)
        clear_queue_data_caches()
        return {"ok": delete_ok, "errors": delete_errors}

    @staticmethod
    def set_max_time(max_time: int) -> dict:
        """Set auto delete max time config."""
        max_time = 86400 if int(max_time) < 86400 else int(max_time)
        AdminQueuesService._set_auto_delete_enabled(True)
        Config.update_old_tasks({"older_than": max_time})
        return {"older_than": max_time}

    @staticmethod
    def _set_auto_delete_enabled(enabled: bool) -> None:
        Config.update_old_tasks({"enabled": enabled})

    @staticmethod
    def set_queue_registries(queue_registries: list) -> dict:
        """Set auto delete queue registries config."""
        for reg in queue_registries:
            if reg not in QUEUE_REGISTRIES:
                raise Error(
                    "bad_request",
                    f"Invalid registry: {reg}. Valid registries are: {QUEUE_REGISTRIES}",
                )
        Config.update_old_tasks({"queue_registries": queue_registries})
        return {"queue_registries": queue_registries}

    @staticmethod
    def set_auto_delete_enabled(enabled: bool) -> dict:
        """Set auto delete enabled/disabled."""
        AdminQueuesService._set_auto_delete_enabled(enabled)
        return {"enabled": enabled}

    @staticmethod
    def get_auto_delete_config() -> dict:
        """Get auto delete configuration."""
        kwargs = Config.get_old_tasks_config()
        return {
            "older_than": kwargs.get("older_than", None),
            "queue_registries": kwargs.get("queue_registries", []),
            "enabled": kwargs.get("enabled", False),
        }

    @staticmethod
    def delete_old_tasks_auto() -> dict:
        """Delete old tasks based on auto-delete config."""
        kwargs = AdminQueuesService.get_auto_delete_config()
        if not kwargs.get("enabled", False):
            return {"ok": [], "errors": []}
        if kwargs.get("older_than") is None:
            raise Error("bad_request", "No max_time set in the db.")
        if kwargs.get("queue_registries") is None:
            raise Error("bad_request", "No queue_registries set in the db.")
        old_jobs = AdminQueuesService._get_old_jobs(
            kwargs["older_than"],
            rtype="job",
            registries=kwargs["queue_registries"],
        )
        delete_ok, delete_errors = AdminQueuesService._delete_jobs(old_jobs)
        clear_queue_data_caches()
        return {"ok": delete_ok, "errors": delete_errors}
