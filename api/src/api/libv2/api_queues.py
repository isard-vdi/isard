#
#   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import time

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest
from isardvdi_common.storage_node import StorageNode
from redis import Redis
from rethinkdb import RethinkDB
from rq import Queue
from rq.job import Job

from api import app

from .flask_rethink import RDB

r = RethinkDB()

db = RDB(app)
db.init_app(app)


def _connect_redis():
    return Redis(
        host=os.environ.get("REDIS_HOST", "isard-redis"),
        port=int(os.environ.get("REDIS_PORT", 6379)),
        password=os.environ.get("REDIS_PASSWORD", ""),
    )


@cached(TTLCache(maxsize=1, ttl=5))
def get_queues():
    with _connect_redis() as r:
        return Queue.all(connection=r)


@cached(TTLCache(maxsize=1, ttl=5))
def get_queue_jobs(queue_name):
    with _connect_redis() as r:
        queue = Queue(queue_name, connection=r)
    return {
        "queued": queue.count,
        "started": queue.started_job_registry.count,
        "finished": queue.finished_job_registry.count,
        "failed": queue.failed_job_registry.count,
        "deferred": queue.deferred_job_registry.count,
        "scheduled": queue.scheduled_job_registry.count,
        "canceled": queue.canceled_job_registry.count,
    }


@cached(TTLCache(maxsize=1, ttl=5))
def subscribers():
    with _connect_redis() as r:
        subscribers = r.pubsub_channels()
    s = []
    for subscriber in subscribers:
        s.append(
            {
                "id": str(subscriber).split(":")[3].split("'")[0],
                "queue": str(subscriber).split(":")[2],
            }
        )
    return s


@cached(TTLCache(maxsize=1, ttl=5))
def workers():
    with _connect_redis() as r:
        workers = r.keys("rq:workers:*")
    w = []
    for worker in workers:
        try:
            if str(worker).split(":")[2].split(".")[0].split("'")[0] not in [
                "core",
                "storage",
            ]:
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
        except:
            app.logger.error(f"Error parsing worker {worker}, skipping...")
    for worker in w:
        if worker["priority_id"] == None:
            worker["priority"] = None
        if worker["priority_id"] == "high":
            worker["priority"] = 3
        if worker["priority_id"] == "default":
            worker["priority"] = 2
        if worker["priority_id"] == "low":
            worker["priority"] = 1
    return w


@cached(TTLCache(maxsize=1, ttl=5))
def workers_with_subscribers():
    w = workers()
    s = subscribers()
    for worker in w:
        worker["subscribers"] = [
            subs["id"] for subs in s if subs["queue"] == worker["queue"]
        ]
        if not len(worker["subscribers"]):
            worker["status"] = "error"
        else:
            worker["status"] = "ok"
    return w


@cached(TTLCache(maxsize=1, ttl=5))
def subscribers_with_workers():
    s = subscribers()
    w = workers()
    for subscriber in s:
        subscriber["workers"] = [
            worker["id"] for worker in w if subscriber["queue"] == worker["queue"]
        ]
    return s


QUEUE_REGISTRIES = [
    "queued",
    "started",
    "finished",
    "failed",
    "deferred",
    "scheduled",
    "canceled",
]


def get_all_queue_job_ids(
    queue_name: str,
    registries: list[str] = QUEUE_REGISTRIES,
):
    with _connect_redis() as r:
        queue = Queue(queue_name, connection=r)

    registry_mapping = {
        "queued": queue,
        "started": queue.started_job_registry,
        "finished": queue.finished_job_registry,
        "failed": queue.failed_job_registry,
        "deferred": queue.deferred_job_registry,
        "scheduled": queue.scheduled_job_registry,
        "canceled": queue.canceled_job_registry,
    }
    if registries is None:
        registries = QUEUE_REGISTRIES

    registry_objects = [registry_mapping[reg] for reg in registries]

    job_ids = []
    for registry in registry_objects:
        job_ids.extend(registry.get_job_ids())

    return job_ids


def get_old_jobs(
    older_than: int,
    batch_size: int = 5000,
    rtype: str = "key",
    registries: list[str] = ["finished"],
):
    """
    All jobs have a TTL of -1, so they never expire automatically.
    This function returns the list of finished jobs where their ended_at is older than `older_than`

    :param older_than: The time in seconds since epoch to compare the ended_at time of the jobs
    :param batch_size: The number of jobs to fetch at once from Redis
    :param rtype: The type of data to return. Can be "key", "id" or "job"
    :param registries: The registries to search for old jobs. By default it only searches for finished jobs.
    """
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

    with _connect_redis() as r:
        queue = Queue.all(connection=r)

    finished_jobs = []
    for q in queue:
        finished_jobs.extend(get_all_queue_job_ids(q.name, registries))

    old_keys = []
    for i in range(0, len(finished_jobs), batch_size):
        batch_ids = finished_jobs[i : i + batch_size]

        with _connect_redis() as r:
            jobs = Job.fetch_many(batch_ids, connection=r)

        for job in jobs:
            if job is None:
                app.logger.warning(f"Job is none: {job}")
                continue

            if job.ended_at is None or job.ended_at.timestamp() < time_cutoff:
                match rtype:
                    case "key":
                        old_keys.append(job.key.decode())
                    case "id":
                        old_keys.append(job.id)
                    case "job":
                        old_keys.append(job)

    return old_keys


def delete_jobs(jobs: list[Job]):
    """
    Deletes the jobs with the given keys from Redis.
    This function uses rq to delete the jobs.

    :param jobs: A list of rq Job objects to delete.
    """
    ok = []
    errors = []

    for job in jobs:
        try:
            job.delete(delete_dependents=True)
        except Exception as e:
            errors.append(job.id)
        else:
            ok.append(job.id)

    return ok, errors


def set_auto_delete_enabled(enabled: bool):
    """
    Sets the auto delete enabled in the db.
    """
    with app.app_context():
        r.table("config").update({"old_tasks": {"enabled": enabled}}).run(db.conn)


def set_auto_delete_max_time(max_time: int):
    """
    Sets the auto delete max time in the db.
    """
    if max_time < 86400:  # 1 day
        raise Error(
            "bad_request",
            "Max time must be at least 24 hours to avoid data loss.",
        )

    with app.app_context():
        r.table("config").update({"old_tasks": {"older_than": max_time}}).run(db.conn)


def set_auto_delete_queue_registries(registries: list[str]):
    """
    Sets the auto delete queue registries in the db.
    """
    for reg in registries:
        if reg not in QUEUE_REGISTRIES:
            raise Error(
                "bad_request",
                f"Invalid registry: {reg}. Valid registries are: {QUEUE_REGISTRIES}",
            )

    with app.app_context():
        r.table("config").update({"old_tasks": {"queue_registries": registries}}).run(
            db.conn
        )


def get_auto_delete_kwargs():
    """
    Returns the auto delete kwargs from the db.
    """
    try:
        with app.app_context():
            kwargs = r.table("config")[0]["old_tasks"].run(db.conn)
    except r.ReqlNonExistenceError:
        kwargs = {}

    return {
        "older_than": kwargs.get("older_than", None),
        "queue_registries": kwargs.get("queue_registries", []),
        "enabled": kwargs.get("enabled", False),
    }
