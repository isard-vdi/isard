import asyncio
import logging as log
import os
import time
import traceback
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.bookings import Bookings
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers as CommonHelpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.user_storage import UserStorage
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.targets import Targets
from isardvdi_common.models.task import Task
from isardvdi_common.schemas.migrations import MigrationsStatusEnum
from isardvdi_common.schemas.recycle_bin import RecycleBinStatusEnum
from isardvdi_common.schemas.storage import StorageStatusEnum
from rethinkdb import r

_get_status_cache: TTLCache = TTLCache(maxsize=10, ttl=30)
_get_category_data_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
_get_group_data_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
_get_user_data_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
_get_cache: TTLCache = TTLCache(maxsize=50, ttl=30)
_get_recycle_bin_entries_cutoff_time_surpassed_cache: TTLCache = TTLCache(
    maxsize=50, ttl=10
)
_get_user_recycle_bin_ids_cache: TTLCache = TTLCache(maxsize=50, ttl=60)
_get_count_cache: TTLCache = TTLCache(maxsize=50, ttl=60)
_get_item_count_cache: TTLCache = TTLCache(maxsize=50, ttl=60)
_get_user_amount_cache: TTLCache = TTLCache(maxsize=50, ttl=60)
_get_old_entries_config_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_get_default_delete_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_get_delete_action_cache: TTLCache = TTLCache(maxsize=1, ttl=60)
_get_user_recycle_bin_cutoff_time_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_get_categories_recycle_bin_cutoff_time_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_get_category_recycle_bin_cuttoff_time_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_get_recycle_bin_cuttoff_time_cache: TTLCache = TTLCache(maxsize=1, ttl=10)


class RecycleBinDeleteQueue(RethinkSharedConnection):
    _instance = None
    _lock = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "queue"):
            self.queue = None
            self.recycle_bin_ids = set()
            self.stop_event = None
            self._task = None

    async def initialize(self):
        """Call this once during application startup"""
        if RecycleBinDeleteQueue._lock is None:
            RecycleBinDeleteQueue._lock = asyncio.Lock()

        async with RecycleBinDeleteQueue._lock:
            if self._initialized:
                return

            self.queue = asyncio.Queue()
            self.recycle_bin_ids = set()
            self.stop_event = asyncio.Event()
            self._task = None
            self._initialized = True

            # Add all recycle bin that are in status queued to the queue to be processed
            with self._rdb_context():
                recycle_bins = list(
                    r.table("recycle_bin")
                    .get_all(RecycleBinStatusEnum.queued.value, index="status")
                    .pluck("id", "agent_id")
                    .run(self._rdb_connection)
                )

            for recycle_bin in recycle_bins:
                await self.enqueue(
                    {
                        "recycle_bin_id": recycle_bin["id"],
                        "user_id": recycle_bin["agent_id"],
                    }
                )

    async def start(self):
        """Start the background worker - call during startup"""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._background_worker())

    async def enqueue(self, item):
        recycle_bin_id = item.get("recycle_bin_id")
        if recycle_bin_id not in self.recycle_bin_ids:
            # Both helpers are sync RethinkDB writes. Offload them so
            # callers awaiting ``enqueue`` from inside an asyncio
            # request handler don't block the event loop on every
            # bulk-delete iteration.
            await asyncio.to_thread(
                Helpers.update_status,
                recycle_bin_id,
                item.get("user_id"),
                RecycleBinStatusEnum.queued.value,
            )
            await asyncio.to_thread(
                Helpers.add_log,
                "queued",
                recycle_bin_id,
                "system",
                "isard-scheduler",
                "isard-scheduler",
                None,
                None,
                None,
            )
            await self.queue.put(item)
            self.recycle_bin_ids.add(recycle_bin_id)
            log.debug(f"Item with recycle_bin_id {recycle_bin_id} added to the queue.")
        else:
            log.debug(
                f"Item with recycle_bin_id {recycle_bin_id} is already in the queue."
            )

    def enqueue_sync(self, item):
        """
        Synchronous wrapper for enqueue. Use this from non-async contexts.
        This will schedule the enqueue operation on the event loop.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule the coroutine
                asyncio.create_task(self.enqueue(item))
            else:
                # If no loop is running, run it synchronously
                loop.run_until_complete(self.enqueue(item))
        except RuntimeError:
            # No event loop in current thread, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.enqueue(item))
            loop.close()

    async def dequeue(self):
        try:
            item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            self.recycle_bin_ids.remove(item.get("recycle_bin_id"))
            return item
        except asyncio.TimeoutError:
            return None

    async def perform_operation(self, recycle_bin_id, user_id):
        # Example operation using user_id
        log.debug(f"Performing operation with user_id {user_id}")
        try:
            rb = RecycleBin(id=recycle_bin_id)
            rb.delete_storage(user_id)
            if rb.item_type in ["user", "group", "category"]:
                dependants_rb_ids = []
                for user in rb.users:
                    with self._rdb_context():
                        dependants_rb_ids += set(
                            r.table("recycle_bin")
                            .get_all(
                                [user["id"], RecycleBinStatusEnum.recycled.value],
                                index=f"owner_status",
                            )
                            .filter(lambda rb: rb["id"] != recycle_bin_id)
                            .pluck("id")["id"]
                            .run(self._rdb_connection)
                        )
                if rb.item_type == "group":
                    for group in rb.groups:
                        with self._rdb_context():
                            dependants_rb_ids += set(
                                r.table("recycle_bin")
                                .get_all(
                                    [group["id"], RecycleBinStatusEnum.recycled.value],
                                    index=f"owner_group_status",
                                )
                                .filter(lambda rb: rb["id"] != recycle_bin_id)
                                .pluck("id")["id"]
                                .run(self._rdb_connection)
                            )
                elif rb.item_type == "category":
                    for category in rb.categories:
                        with self._rdb_context():
                            dependants_rb_ids += set(
                                r.table("recycle_bin")
                                .get_all(
                                    [
                                        category["id"],
                                        RecycleBinStatusEnum.recycled.value,
                                    ],
                                    index=f"owner_category_status",
                                )
                                .filter(lambda rb: rb["id"] != recycle_bin_id)
                                .pluck("id")["id"]
                                .run(self._rdb_connection)
                            )
                for d_rb_id in dependants_rb_ids:
                    await self.enqueue({"recycle_bin_id": d_rb_id, "user_id": user_id})
        except Exception as e:
            log.error(
                f"Error processing recycle bin {recycle_bin_id}: {str(e)}",
                exc_info=True,
            )
            # Update status back to recycled so it can be retried or manually handled
            try:
                Helpers.update_status(
                    recycle_bin_id, user_id, RecycleBinStatusEnum.recycled.value
                )
            except Exception as status_error:
                log.error(
                    f"Failed to update status for recycle bin {recycle_bin_id}: {str(status_error)}"
                )

    async def process_next_item(self):
        item = await self.dequeue()
        if item:
            user_id = item.get("user_id")
            recycle_bin_id = item.get("recycle_bin_id")
            try:
                await self.perform_operation(recycle_bin_id, user_id)
            except Exception as e:
                log.error(
                    f"Uncaught error in process_next_item for recycle bin {recycle_bin_id}: {str(e)}",
                    exc_info=True,
                )
            finally:
                self.queue.task_done()

    async def _background_worker(self):
        """Background task that processes queue items"""
        while not self.stop_event.is_set():
            try:
                await self.process_next_item()
            except Exception as e:
                log.error(
                    f"Critical error in recycle bin background worker: {str(e)}",
                    exc_info=True,
                )
            await asyncio.sleep(0.1)  # Add a small sleep to prevent a tight loop

    async def stop(self):
        """Stop the background worker - call during shutdown"""
        self.stop_event.set()
        if self._task:
            await self._task


class Helpers(RethinkSharedConnection):

    @classmethod
    def owns_recycle_bin_id(cls, payload, recycle_bin_id):
        if payload.get("role_id", "") == "admin":
            return recycle_bin_id
        recycle_bin_user_id = Caches.get_document(
            "recycle_bin", recycle_bin_id, ["owner_id"]
        )
        if recycle_bin_user_id is None:
            raise Error(
                "not_found",
                f"Recycle bin {recycle_bin_id} not found",
                traceback.format_exc(),
            )
        if recycle_bin_user_id == payload["user_id"]:
            return recycle_bin_id

        if payload["role_id"] == "manager":
            recycle_bin_category_id = Caches.get_document(
                "recycle_bin", recycle_bin_id, ["owner_category_id"]
            )
            if recycle_bin_category_id is None:
                raise Error(
                    "not_found",
                    f"Recycle bin user {recycle_bin_user_id} not found",
                    traceback.format_exc(),
                )
            if recycle_bin_category_id == payload["category_id"]:
                return recycle_bin_id

        raise Error(
            "forbidden",
            "Not enough access rights for this user_id " + payload["user_id"],
            traceback.format_exc(),
        )

    @classmethod
    @cached(cache=_get_status_cache)
    def get_status(cls, category_id=None):

        query = r.table("recycle_bin")
        if category_id:
            query = query.get_all(category_id, index="owner_category")
        query = (
            query.group("status")
            .count()
            .ungroup()
            .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
        )
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def clear_get_status_cache(cls):
        _get_status_cache.clear()

    @classmethod
    @cached(cache=_get_category_data_cache)
    def get_category_data(cls, category_id):
        with cls._rdb_context():
            return (
                r.table("categories")
                .get(category_id)
                .pluck("id", "name")
                .default({"id": category_id, "name": "[Deleted]"})
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_category_data_cache(cls):
        _get_category_data_cache.clear()

    @classmethod
    @cached(cache=_get_group_data_cache)
    def get_group_data(cls, group_id):
        with cls._rdb_context():
            return (
                r.table("groups")
                .get(group_id)
                .pluck("id", "name")
                .default({"id": group_id, "name": "[Deleted]"})
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_group_data_cache(cls):
        _get_group_data_cache.clear()

    @classmethod
    @cached(cache=_get_user_data_cache)
    def get_user_data(cls, user_id):
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "category", "group", "name", "role")
                .default(
                    {
                        "id": user_id,
                        "category": "[Deleted]",
                        "group": "[Deleted]",
                        "name": "[Deleted]",
                        "role": "[Deleted]",
                    }
                )
                .run(cls._rdb_connection)
            )
        category = cls.get_category_data(user["category"])
        group = cls.get_group_data(user["group"])
        return {
            "user_id": user["id"],
            "user_name": user["name"],
            "category_name": category["name"],
            "category_id": category["id"],
            "group_name": group["name"],
            "group_id": group["id"],
            "role": user["role"],
        }

    @classmethod
    def clear_get_user_data_cache(cls):
        _get_user_data_cache.clear()

    @classmethod
    @cached(cache=_get_cache)
    # TODO
    def get(cls, recycle_bin_id=None, all_data=None):
        """
        Get one recycle bin entry.

        :param recycle_bin_id: RecycleBin ID
        :param all_data: Get specific data about domains and storages
        :type all_data: bool
        :type recycle_bin_id: str
        :return: Recycle bin entry
        :rtype: dict
        """
        with cls._rdb_context():
            result = r.table("recycle_bin").get(recycle_bin_id).run(cls._rdb_connection)

        if all_data:
            from collections import defaultdict

            all_domains = result.get("desktops", []) + result.get("templates", [])

            # Batch-fetch all unique categories and groups in 2 queries
            category_ids = set()
            group_ids = set()
            for domain in all_domains:
                if isinstance(domain.get("category"), str):
                    category_ids.add(domain["category"])
                if isinstance(domain.get("group"), str):
                    group_ids.add(domain["group"])
            for user in result.get("users", []):
                if isinstance(user.get("category"), str):
                    category_ids.add(user["category"])
                if isinstance(user.get("group"), str):
                    group_ids.add(user["group"])

            deleted_cat = {"id": None, "name": "[Deleted]"}
            deleted_grp = {"id": None, "name": "[Deleted]"}
            with cls._rdb_context():
                categories = (
                    {
                        c["id"]: c
                        for c in r.table("categories")
                        .get_all(r.args(list(category_ids)))
                        .pluck("id", "name")
                        .run(cls._rdb_connection)
                    }
                    if category_ids
                    else {}
                )
                groups = (
                    {
                        g["id"]: g
                        for g in r.table("groups")
                        .get_all(r.args(list(group_ids)))
                        .pluck("id", "name")
                        .run(cls._rdb_connection)
                    }
                    if group_ids
                    else {}
                )

            # Build storage→domain mapping in O(D×disks) instead of O(S×D×disks)
            storage_to_domains = defaultdict(list)
            for domain in all_domains:
                # Drop the libvirt xml blob
                domain.pop("xml", None)
                cat_id = domain.get("category")
                grp_id = domain.get("group")
                domain["category"] = categories.get(cat_id, deleted_cat)
                domain["group"] = groups.get(grp_id, deleted_grp)
                for disk in (
                    domain.get("create_dict", {}).get("hardware", {}).get("disks", [])
                ):
                    if "storage_id" in disk:
                        storage_to_domains[disk["storage_id"]].append(domain)

            # Assign domains to storages in O(S)
            for storage in result.get("storages", []):
                matches = storage_to_domains.get(storage["id"], [])
                storage["domains"] = [m["name"] for m in matches]
                if matches:
                    storage["category"] = matches[0]["category"]
                    storage["user"] = matches[0].get("username")

            # Batch-fetch deployment users in 1 query
            result["deployments"] = [
                d for d in result.get("deployments", []) if d is not None
            ]
            dep_user_ids = list(
                set(
                    d["user"]
                    for d in result["deployments"]
                    if isinstance(d.get("user"), str)
                )
            )
            if dep_user_ids:
                with cls._rdb_context():
                    dep_users = {
                        u["id"]: u
                        for u in r.table("users")
                        .get_all(r.args(dep_user_ids))
                        .pluck("id", "username", "category", "group")
                        .run(cls._rdb_connection)
                    }
                # Fetch any deployment-user categories/groups not already loaded
                for u in dep_users.values():
                    if u.get("category") and u["category"] not in categories:
                        category_ids.add(u["category"])
                    if u.get("group") and u["group"] not in groups:
                        group_ids.add(u["group"])
                if category_ids - set(categories.keys()):
                    with cls._rdb_context():
                        extra_cats = {
                            c["id"]: c
                            for c in r.table("categories")
                            .get_all(
                                r.args(list(category_ids - set(categories.keys())))
                            )
                            .pluck("id", "name")
                            .run(cls._rdb_connection)
                        }
                    categories.update(extra_cats)
                if group_ids - set(groups.keys()):
                    with cls._rdb_context():
                        extra_grps = {
                            g["id"]: g
                            for g in r.table("groups")
                            .get_all(r.args(list(group_ids - set(groups.keys()))))
                            .pluck("id", "name")
                            .run(cls._rdb_connection)
                        }
                    groups.update(extra_grps)
            else:
                dep_users = {}

            for deployment in result["deployments"]:
                u = dep_users.get(deployment.get("user"), {})
                deployment["user"] = u.get("username", "[Deleted]")
                deployment["category"] = categories.get(u.get("category"), deleted_cat)
                deployment["group"] = groups.get(u.get("group"), deleted_grp)

            for user in result.get("users", []):
                cat_id = user.get("category")
                grp_id = user.get("group")
                user["category"] = categories.get(cat_id, deleted_cat).get(
                    "name", "[Deleted]"
                )
                user["group"] = groups.get(grp_id, deleted_grp).get("name", "[Deleted]")
        return result

    @classmethod
    def clear_get_cache(cls):
        _get_cache.clear()

    @classmethod
    @cached(cache=_get_recycle_bin_entries_cutoff_time_surpassed_cache)
    def get_recycle_bin_entries_cutoff_time_surpassed(cls):
        """
        Retrieve all recycle bin entries that have surpassed the cutoff time. It will consider the global
        cutoff time or the category cutoff time.

        :return: Recycle bin entries that have surpassed the cutoff time
        :rtype: list
        """
        recycle_bin_entries = []
        recycle_bin_cuttoff_time = cls.get_recycle_bin_cuttoff_time()
        recycle_bin_categories_cuttoff_time = (
            cls.get_categories_recycle_bin_cutoff_time()
        )

        if not recycle_bin_categories_cuttoff_time:
            # Single query using status_accessed compound index
            cutoff_ts = (
                datetime.now(timezone.utc) - timedelta(hours=recycle_bin_cuttoff_time)
            ).timestamp()
            with cls._rdb_context():
                recycle_bin_entries = list(
                    r.table("recycle_bin")
                    .between(
                        [RecycleBinStatusEnum.recycled.value, r.minval],
                        [RecycleBinStatusEnum.recycled.value, cutoff_ts],
                        index="status_accessed",
                    )
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
        else:
            # Batch query: union per-category range scans instead of N+1 loop
            with cls._rdb_context():
                queries = []
                for category in recycle_bin_categories_cuttoff_time:
                    cutoff_ts = (
                        datetime.now(timezone.utc)
                        - timedelta(hours=category["recycle_bin_cutoff_time"])
                    ).timestamp()
                    queries.append(
                        r.table("recycle_bin")
                        .between(
                            [
                                category["id"],
                                RecycleBinStatusEnum.recycled.value,
                                r.minval,
                            ],
                            [
                                category["id"],
                                RecycleBinStatusEnum.recycled.value,
                                cutoff_ts,
                            ],
                            index="owner_category_status_accessed",
                        )
                        .pluck("id")["id"]
                    )
                if queries:
                    combined = queries[0]
                    for q in queries[1:]:
                        combined = combined.union(q)
                    recycle_bin_entries = list(combined.run(cls._rdb_connection))

            categories_to_exclude_ids = [
                category["id"] for category in recycle_bin_categories_cuttoff_time
            ]

            with cls._rdb_context():
                recycle_bin_entries += list(
                    r.table("recycle_bin")
                    .get_all(RecycleBinStatusEnum.recycled.value, index="status")
                    .filter(
                        lambda rb: r.expr(categories_to_exclude_ids)
                        .contains(rb["owner_category_id"])
                        .not_()
                    )
                    .filter(
                        r.row["accessed"]
                        < (
                            datetime.now(timezone.utc)
                            - timedelta(hours=recycle_bin_cuttoff_time)
                        ).timestamp()
                    )
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )

        return set(recycle_bin_entries)

    @classmethod
    def clear_get_recycle_bin_entries_cutoff_time_surpassed_cache(cls):
        _get_recycle_bin_entries_cutoff_time_surpassed_cache.clear()

    @classmethod
    def update_status(cls, rb_id, owner_id, status):
        with cls._rdb_context():
            r.table("recycle_bin").get(rb_id).update({"status": status}).run(
                cls._rdb_connection
            )
        # The list endpoint (``get_item_count``) caches its results for
        # 60 s scoped to ``status="recycled"``. Without this invalidation
        # a status flip to ``restored`` / ``deleting`` / ``deleted``
        # leaves the now-irrelevant row in the cache, so the next
        # ``GET /items/recycle-bin`` re-renders the entry the user just
        # restored or deleted.
        cls.clear_get_item_count_cache()
        cls.clear_get_count_cache()
        cls.clear_get_user_amount_cache()
        cls.clear_get_user_recycle_bin_ids_cache()

    @classmethod
    def update_task_status(cls, task):

        # First, atomically update the task status and get the updated document
        start = absolute_start = time.time()
        with cls._rdb_context():
            update_result = (
                r.table("recycle_bin")
                .get(task["recycle_bin_id"])
                .update(
                    {
                        "tasks": r.row["tasks"].map(
                            lambda rb_task: r.branch(
                                rb_task["id"] == task["id"],
                                rb_task.merge({"status": task["status"]}),
                                rb_task,
                            )
                        )
                    },
                    return_changes=True,
                )
                .run(cls._rdb_connection)
            )
        log.debug(
            "RecycleBin %s update_task_status: Updated task status in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )

        # If no document was updated, return early
        if not update_result.get("changes"):
            log.warning(
                "RecycleBin %s update_task_status: No document found or updated",
                task["recycle_bin_id"],
            )
            return

        # Get the updated document to check if all tasks are finished
        updated_rb = update_result["changes"][0]["new_val"]

        # Check if all the recycle bin tasks are finished then update the recycle bin status to deleted
        start = time.time()
        finished_tasks = list(
            filter(lambda t: (t["status"] == "finished"), updated_rb["tasks"])
        )

        log.debug(
            "RecycleBin %s update_task_status: Filtered finished tasks in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )

        # Only proceed if all tasks are finished and status is not already "deleted"
        if (
            len(finished_tasks) == len(updated_rb["storages"])
            and updated_rb.get("status") != "deleted"
        ):
            start = time.time()
            with cls._rdb_context():
                # Atomically update status to deleted, but only if it's not already deleted
                # This prevents race conditions where multiple tasks try to set status to deleted
                final_update_result = (
                    r.table("recycle_bin")
                    .get(task["recycle_bin_id"])
                    .update(
                        lambda doc: r.branch(
                            doc["status"] != "deleted",
                            {"status": "deleted"},
                            {},  # No update if already deleted
                        ),
                        return_changes=True,
                    )
                    .run(cls._rdb_connection)
                )

            log.debug(
                "RecycleBin %s update_task_status: Updated recycle bin status to deleted in %s seconds",
                task["recycle_bin_id"],
                time.time() - start,
            )

            # Only add log if we actually changed the status; the socket
            # emit is handled by the change-handler watching the recycle_bin
            # table for the status flip to "deleted".
            if final_update_result.get("changes"):
                start = time.time()
                Helpers.add_log(
                    "deleted",
                    task["recycle_bin_id"],
                    updated_rb["agent_type"],
                    updated_rb["agent_id"],
                    updated_rb["agent_name"],
                    updated_rb["agent_category_id"],
                    updated_rb["agent_category_name"],
                    updated_rb["agent_role"],
                )
                log.debug(
                    "RecycleBin %s update_task_status: Added log entry in %s seconds",
                    task["recycle_bin_id"],
                    time.time() - start,
                )

        log.debug(
            "RecycleBin %s update_task_status: Finished in %s seconds",
            task["recycle_bin_id"],
            time.time() - absolute_start,
        )

    @classmethod
    @cached(cache=_get_user_recycle_bin_ids_cache)
    def get_user_recycle_bin_ids(cls, user_id, status):
        """
        Get all the users recycle_bins ids

        :param user_id: User ID
        :type user_id: str
        :return: IDs of the user recycle bins
        :rtype: array
        """
        with cls._rdb_context():
            return list(
                r.table("recycle_bin")
                .get_all([user_id, status], index="owner_status")
                .filter({"agent_id": user_id})["id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_user_recycle_bin_ids_cache(cls):
        _get_user_recycle_bin_ids_cache.clear()

    @classmethod
    @cached(cache=_get_count_cache)
    def get_count(cls, recycle_bin_id):
        with cls._rdb_context():
            return (
                r.table("recycle_bin")
                .get(recycle_bin_id)
                .merge(
                    {
                        "desktops": r.row["desktops_count"].default(
                            r.row["desktops"].count()
                        ),
                        "templates": r.row["templates_count"].default(
                            r.row["templates"].count()
                        ),
                        "storages": r.row["storages_count"].default(
                            r.row["storages"].count()
                        ),
                        "deployments": r.row["deployments_count"].default(
                            r.row["deployments"].count()
                        ),
                        "categories": r.row["categories_count"].default(
                            r.row["categories"].count()
                        ),
                        "groups": r.row["groups_count"].default(
                            r.row["groups"].count()
                        ),
                        "users": r.row["users_count"].default(r.row["users"].count()),
                        "last": r.row["last_log"].default(r.row["logs"][-1]),
                    }
                )
                .without("logs", "tasks")
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_count_cache(cls):
        _get_count_cache.clear()

    @classmethod
    def clear_get_count_for(cls, recycle_bin_id):
        # Per-key invalidation. cachetools' ``@cached`` builds the key
        # via ``hashkey(*args, **kwargs)`` from the *bound* call site —
        # for a classmethod that means ``hashkey(cls, recycle_bin_id)``.
        # Mirror that here so a single rcb update doesn't blow the
        # cache for every other rcb (the change-handler pre-fix path
        # called ``cache_clear()`` on every per-row event, leaving the
        # 60s TTL effectively useless under any concurrency).
        _get_count_cache.pop(hashkey(cls, recycle_bin_id), None)

    @classmethod
    @cached(cache=_get_item_count_cache)
    def get_item_count(cls, user_id=None, category_id=None, status=None):
        query = r.table("recycle_bin")
        if user_id:
            query = query.get_all(
                [user_id, RecycleBinStatusEnum.recycled.value], index="owner_status"
            )
        elif category_id:
            if status:
                query = query.get_all(
                    [category_id, status], index="owner_category_status"
                )
            else:
                query = query.get_all(
                    [category_id, RecycleBinStatusEnum.recycled.value],
                    index="owner_category_status",
                )
        elif status:
            query = query.get_all(status, index="status")
        else:
            query = query.get_all(
                r.args(
                    [
                        RecycleBinStatusEnum.recycled.value,
                        RecycleBinStatusEnum.deleting.value,
                    ]
                ),
                index="status",
            )
        count_query = {
            "desktops": r.row["desktops_count"].default(r.row["desktops"].count()),
            "templates": r.row["templates_count"].default(r.row["templates"].count()),
            "storages": r.row["storages_count"].default(r.row["storages"].count()),
            "deployments": r.row["deployments_count"].default(
                r.row["deployments"].count()
            ),
            "categories": r.row["categories_count"].default(
                r.row["categories"].count()
            ),
            "groups": r.row["groups_count"].default(r.row["groups"].count()),
            "users": r.row["users_count"].default(r.row["users"].count()),
            "last": r.row["last_log"].default(
                r.row["logs"].default([]).nth(-1).default(None)
            ),
        }
        query = query.without("logs", "tasks").merge(count_query)
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def clear_get_item_count_cache(cls):
        _get_item_count_cache.clear()

    @classmethod
    @cached(cache=_get_user_amount_cache)
    def get_user_amount(cls, user_id):
        with cls._rdb_context():
            return (
                r.table("recycle_bin")
                .get_all(
                    [user_id, RecycleBinStatusEnum.recycled.value], index="owner_status"
                )
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_user_amount_cache(cls):
        _get_user_amount_cache.clear()

    @classmethod
    def clear_get_user_amount_for(cls, user_id):
        # Per-key invalidation; see ``clear_get_count_for``.
        _get_user_amount_cache.pop(hashkey(cls, user_id), None)

    @classmethod
    @cached(cache=_get_old_entries_config_cache)
    def get_old_entries_config(cls):
        with cls._rdb_context():
            try:
                return r.table("config")[0]["recycle_bin"]["old_entries"].run(
                    cls._rdb_connection
                )
            except r.ReqlNonExistenceError:
                return {"max_time": None, "action": None}

    @classmethod
    def clear_get_old_entries_config_cache(cls):
        _get_old_entries_config_cache.clear()

    @classmethod
    def check_older_than_old_entry_max_time(cls, last):
        max_time_config = cls.get_old_entries_config()["max_time"]
        if max_time_config is None:
            return False
        else:
            max_time_hours = int(max_time_config)
            return (
                last
                < (
                    datetime.now(timezone.utc) - timedelta(hours=max_time_hours)
                ).timestamp()
            )

    @classmethod
    def get_old_deleted_entry_ids(cls):
        # Apiv3 parity: ``main:api/src/api/libv2/recycle_bin.py:779``.
        # Single indexed range scan returning only IDs, instead of
        # the apiv4 path that materialised every deleted-entry row
        # (with the full count merge) and Python-filtered them. Reads
        # ``max_time`` from ``get_old_entries_config()`` and yields
        # ids whose ``accessed`` timestamp is older than the cutoff.
        max_time_config = cls.get_old_entries_config()["max_time"]
        if max_time_config is None:
            return []
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=int(max_time_config))
        ).timestamp()
        with cls._rdb_context():
            return list(
                r.table("recycle_bin")
                .between(
                    ["deleted", r.minval],
                    ["deleted", cutoff],
                    index="status_accessed",
                )
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    @cached(cache=_get_default_delete_cache)
    def get_default_delete(cls):
        with cls._rdb_context():
            try:
                return r.table("config")[0]["recycle_bin"]["default_delete"].run(
                    cls._rdb_connection
                )
            except r.ReqlNonExistenceError:
                return False

    @classmethod
    def clear_get_default_delete_cache(cls):
        _get_default_delete_cache.clear()

    @classmethod
    @cached(cache=_get_delete_action_cache)
    def get_delete_action(cls):
        with cls._rdb_context():
            try:
                return r.table("config")[0]["recycle_bin"]["delete_action"].run(
                    cls._rdb_connection
                )
            except r.ReqlNonExistenceError:
                return "delete"

    @classmethod
    def clear_get_delete_action_cache(cls):
        _get_delete_action_cache.clear()

    @classmethod
    @cached(cache=_get_user_recycle_bin_cutoff_time_cache)
    def get_user_recycle_bin_cutoff_time(cls, user_id):
        """
        Retrieve the user recycle bin cutoff time.

        :param user_id: User ID
        :type user_id: str
        :return: User recycle bin cutoff time (in hours)
        :rtype: int
        """
        if user_id in ["isard-scheduler", "system"] or user_id.startswith("external_"):
            return cls.get_system_recycle_bin_cutoff_time()
        with cls._rdb_context():
            user_category = (
                r.table("users")
                .get(user_id)
                .pluck("category")["category"]
                .run(cls._rdb_connection)
            )
            cutoff_time = (
                r.table("categories")
                .get(user_category)
                .pluck("recycle_bin_cutoff_time")["recycle_bin_cutoff_time"]
                .run(cls._rdb_connection)
            )
        return (
            cutoff_time
            if cutoff_time is not None
            else cls.get_system_recycle_bin_cutoff_time()
        )

    @classmethod
    def clear_get_user_recycle_bin_cutoff_time_cache(cls):
        _get_user_recycle_bin_cutoff_time_cache.clear()

    @classmethod
    @cached(cache=_get_categories_recycle_bin_cutoff_time_cache)
    def get_categories_recycle_bin_cutoff_time(cls):
        """
        Retrieve all the categories cutoff time.

        :return: Categories ids with its cutoff time (in hours)
        :rtype: list
        """
        with cls._rdb_context():
            return list(
                r.table("categories")
                .pluck("id", "recycle_bin_cutoff_time")
                .filter(lambda category: category["recycle_bin_cutoff_time"].ne(None))
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_categories_recycle_bin_cutoff_time_cache(cls):
        _get_categories_recycle_bin_cutoff_time_cache.clear()

    @classmethod
    @cached(cache=_get_category_recycle_bin_cuttoff_time_cache)
    def get_category_recycle_bin_cuttoff_time(cls, category_id):
        """
        Get the recycle bin cutoff time applied to a category.

        :param category_id: Category ID
        :type category_id: str
        :return: Recycle bin cutoff time (in hours)
        :rtype: int
        """
        with cls._rdb_context():
            category = (
                r.table("categories")
                .get(category_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        recycle_bin_cutoff_time = (category or {}).get("recycle_bin_cutoff_time")
        return (
            recycle_bin_cutoff_time
            if recycle_bin_cutoff_time is not None
            else cls.get_system_recycle_bin_cutoff_time()
        )

    @classmethod
    def clear_get_category_recycle_bin_cuttoff_time_cache(cls):
        _get_category_recycle_bin_cuttoff_time_cache.clear()

    @classmethod
    @cached(cache=_get_recycle_bin_cuttoff_time_cache)
    def get_recycle_bin_cuttoff_time(cls, category_id=None):
        """
        Get the recycle bin cutoff time for a category or the global cutoff time.

        :param category_id: Category ID
        :type category_id: str
        :return: Recycle bin cutoff time (in hours)
        :rtype: int
        """
        if category_id:
            with cls._rdb_context():
                category = (
                    r.table("categories")
                    .get(category_id)
                    .default(None)
                    .run(cls._rdb_connection)
                )
            recycle_bin_cutoff_time = (category or {}).get("recycle_bin_cutoff_time")
            return {
                "category": (
                    recycle_bin_cutoff_time
                    if recycle_bin_cutoff_time is not None
                    else cls.get_system_recycle_bin_cutoff_time()
                ),
                "system": cls.get_system_recycle_bin_cutoff_time(),
            }
        return cls.get_system_recycle_bin_cutoff_time()

    @classmethod
    def clear_get_recycle_bin_cuttoff_time_cache(cls):
        _get_recycle_bin_cuttoff_time_cache.clear()

    @classmethod
    def get_system_recycle_bin_cutoff_time(cls):
        """
        Get the global recycle bin cutoff time

        :return: Recycle bin cutoff time (in hours)
        :rtype: int
        """
        config = Caches.get_config()
        return config["recycle_bin"]["recycle_bin_cutoff_time"]

    @classmethod
    def set_system_recycle_bin_cutoff_time(cls, cutoff_time, category_id=None):
        """

        Set the global recycle bin cutoff time or the category recycle bin cutoff time.

        :param cutoff_time: Recycle bin cutoff time (in hours)
        :type cutoff_time: int
        :param category_id: Category ID
        :type category_id: str

        """
        if category_id:
            with cls._rdb_context():
                r.table("categories").get(category_id).update(
                    {"recycle_bin_cutoff_time": cutoff_time}
                ).run(cls._rdb_connection)
        else:
            # Check if any category has a cutoff_time bigger than the one that is being set. If so, set to the system cutoff_time
            categories_cutoff_time = cls.get_categories_recycle_bin_cutoff_time()
            if categories_cutoff_time:
                for category in categories_cutoff_time:
                    if category["recycle_bin_cutoff_time"] > cutoff_time:
                        with cls._rdb_context():
                            r.table("categories").get(category["id"]).update(
                                {"recycle_bin_cutoff_time": cutoff_time}
                            ).run(cls._rdb_connection)
            with cls._rdb_context():
                r.table("config").get(1).update(
                    {"recycle_bin": {"recycle_bin_cutoff_time": cutoff_time}}
                ).run(cls._rdb_connection)
            Caches.clear_config_cache()

    @classmethod
    def add_log(
        cls,
        status,
        id,
        agent_type,
        agent_id,
        agent_name,
        agent_category_id,
        agent_category_name,
        agent_role,
    ):
        """
        Add a log entry for a status change with agent

        :param status: new status
        :type status: str
        """
        logs = {
            "time": int(time.time()),
            "action": status,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_category_id": agent_category_id,
            "agent_category_name": agent_category_name,
            "agent_role": agent_role,
        }
        with cls._rdb_context():
            r.table("recycle_bin").get(id).update(
                {"logs": r.row["logs"].append(logs)}
            ).run(cls._rdb_connection)

    @classmethod
    def get_template_dependant_recycle_bin_entries(cls, templates, index):
        with cls._rdb_context():
            return list(
                r.table("recycle_bin")
                .get_all(r.args(templates), index=index)
                .filter(lambda rb: rb["status"] == RecycleBinStatusEnum.recycled.value)
                .pluck({"id", "agent_id"})
                .distinct()
                .run(cls._rdb_connection)
            )

    @classmethod
    def delete_dependants_recycle_bin_from_templates(cls, templates):
        """
        Permanent delete the recycle bin entries that contain storages that are dependant on a list of templates
        """
        dependent_storages = cls.get_template_dependant_recycle_bin_entries(
            templates, "parents"
        ) + cls.get_template_dependant_recycle_bin_entries(
            templates, "duplicate_parent_template"
        )
        unique_rcb_templates = list(
            {rcb["id"]: rcb for rcb in dependent_storages}.values()
        )
        for rcb in unique_rcb_templates:
            RecycleBin(rcb["id"]).delete_storage(rcb["agent_id"])

    @classmethod
    def delete_items_from_migration_exceptions(cls, item_id, kind):
        with cls._rdb_context():
            # Delete exemption for this item
            r.table("users_migrations_exceptions").get_all(
                item_id, index="item_id"
            ).delete().run(cls._rdb_connection)
        if kind == "group":
            # Delete exemptions of users in groups
            with cls._rdb_context():
                user_ids = list(
                    r.table("users")
                    .get_all(item_id, index="group")
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
                r.table("users_migrations_exceptions").get_all(
                    r.args(user_ids), index="item_id"
                ).delete().run(cls._rdb_connection)
        if kind == "category":
            # Delete exemptions of users in categories
            with cls._rdb_context():
                user_ids = list(
                    r.table("users")
                    .get_all(item_id, index="category")
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
                r.table("users_migrations_exceptions").get_all(
                    r.args(user_ids), index="item_id"
                ).delete().run(cls._rdb_connection)
            # Delete exemptions of groups in categories
            with cls._rdb_context():
                group_ids = list(
                    r.table("groups")
                    .get_all(item_id, index="parent_category")
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
                r.table("users_migrations_exceptions").get_all(
                    r.args(group_ids), index="item_id"
                ).delete().run(cls._rdb_connection)


class RecycleBin(RethinkSharedConnection):
    id = None
    status = None
    is_new = True
    item_type = None
    item_name = None
    agent_type = None
    agent_id = None
    agent_name = None
    agent_category_id = None
    agent_category_name = None
    agent_group_id = None
    agent_group_name = None
    agent_role = None
    owner_id = None
    owner_name = None
    owner_category_id = None
    owner_category_name = None
    owner_group_id = None
    owner_group_name = None
    owner_role = None
    desktops = []
    targets = []
    templates = []
    deployments = []
    storages = []
    users = []
    groups = []
    categories = []
    size = 0

    def __init__(self, id=None, item_type=None, user_id=None):
        # Call it only with 'id' to operate in an existing recycle_bin entry
        # To create a new one call it
        if not id and not item_type:
            raise Error("bad_request", "id or item_type is required")
        # if id and item_type:
        #     raise Error("bad_request", "id or item_type is required")
        self._set_data(id=id, item_type=item_type, user_id=user_id)

    def _set_data(self, id=None, item_type=None, user_id=None):
        if not id:
            if user_id.startswith("external_"):
                self.agent_type = user_id
            elif user_id == "isard-scheduler":
                self.agent_type = "system"
            else:
                self.agent_type = "user"
            self.status = RecycleBinStatusEnum.recycled.value
            self.agent_id = user_id
            self.item_type = item_type
            if self.agent_type == "user":
                user = Helpers.get_user_data(user_id)
                self.agent_name = user["user_name"]
                self.agent_category_id = user["category_id"]
                self.agent_category_name = user["category_name"]
                self.agent_group_id = user["group_id"]
                self.agent_group_name = user["group_name"]
                self.agent_role = user["role"]
            elif self.agent_type in ["system", "external"]:
                self.agent_name = self.agent_type
                self.agent_category_id = None
                self.agent_category_name = None
                self.agent_group_id = None
                self.agent_group_name = None
                self.agent_role = None
            with self._rdb_context():
                self.id = (
                    r.table("recycle_bin")
                    .insert(
                        {
                            "status": self.status,
                            "accessed": int(time.time()),
                            "logs": [],
                            "tasks": [],
                            "agent_type": self.agent_type,
                            "agent_id": self.agent_id,
                            "agent_name": self.agent_name,
                            "agent_category_id": self.agent_category_id,
                            "agent_category_name": self.agent_category_name,
                            "agent_group_id": self.agent_group_id,
                            "agent_group_name": self.agent_group_name,
                            "agent_role": self.agent_role,
                            "item_type": self.item_type,
                            "item_name": self.item_name,
                            "owner_id": self.owner_id,
                            "owner_name": self.owner_name,
                            "owner_category_id": self.owner_category_id,
                            "owner_category_name": self.owner_category_name,
                            "owner_group_id": self.owner_group_id,
                            "owner_group_name": self.owner_group_name,
                            "owner_role": self.owner_role,
                            "desktops": self.desktops,
                            "targets": self.targets,
                            "templates": self.templates,
                            "deployments": self.deployments,
                            "storages": self.storages,
                            "users": self.users,
                            "groups": self.groups,
                            "categories": self.categories,
                            "size": self.size,
                        },
                        return_changes=True,
                    )
                    .run(self._rdb_connection)["changes"][0]["new_val"]["id"]
                )
            Helpers.add_log(
                "recycled",
                self.id,
                self.agent_type,
                self.agent_id,
                self.agent_name,
                self.agent_category_id,
                self.agent_category_name,
                self.agent_role,
            )

        else:
            with self._rdb_context():
                data = r.table("recycle_bin").get(id).run(self._rdb_connection)
            if not data:
                raise Error("not_found", f"recycle_bin not found: {id}")
            for key, value in data.items():
                self.__dict__[key] = value

    def _add_item_name(self, name):
        self.item_name = name
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update({"item_name": name}).run(
                self._rdb_connection
            )
        try:
            Helpers.get_count.cache_clear()
        except AttributeError:
            pass

    def _add_owner(self, user_id):
        user = Helpers.get_user_data(user_id)
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {
                    "owner_id": user_id,
                    "owner_name": user["user_name"],
                    "owner_category_id": user["category_id"],
                    "owner_category_name": user["category_name"],
                    "owner_group_id": user["group_id"],
                    "owner_group_name": user["group_name"],
                    "owner_role": user["role"],
                }
            ).run(self._rdb_connection)
        self.owner_id = user_id
        self.owner_name = user["user_name"]
        self.owner_category_id = user["category_id"]
        self.owner_category_name = user["category_name"]
        self.owner_group_id = user["group_id"]
        self.owner_group_name = user["group_name"]
        self.owner_role = user["role"]
        self.is_new = False
        try:
            Helpers.get_count.cache_clear()
        except AttributeError:
            pass

    def _update_agent(self, user_id=None):
        """
        Updates agent_name, agent_id, agent_role, agent_category, agent_category_name and agent_type=user. Call after doing an action

        :param user_id: ID of the user who makes the action. Leave None so agent_type is system
        :param user_id: str, None
        """

        if user_id and (user_id not in ["isard-scheduler", "system"]):
            user = Helpers.get_user_data(user_id)
            self.agent_id = user_id
            self.agent_name = user["user_name"]
            self.agent_category_id = user["category_id"]
            self.agent_category_name = user["category_name"]
            self.agent_role = user["role"]
        else:
            self.agent_type = "system"
            self.agent_name = "system"
            self.agent_category_id = None
            self.agent_category_name = None
            self.agent_role = None
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {
                    "agent_id": self.agent_id,
                    "agent_name": self.agent_name,
                    "agent_type": self.agent_type,
                    "agent_category_id": self.agent_category_id,
                    "agent_category_name": self.agent_category_name,
                    "agent_group_id": self.agent_group_id,
                    "agent_group_name": self.agent_group_name,
                    "agent_role": self.agent_role,
                }
            ).run(self._rdb_connection)

    def _add_task(self, task):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"tasks": r.row["tasks"].append(task)}
            ).run(self._rdb_connection)

    def _update_size(self):
        size = 0
        for s in self.storages:
            size += s.get("qemu-img-info", {}).get("actual-size", 0)
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {
                    "size": r.row["size"] + size,
                }
            ).run(self._rdb_connection)

    def check_can_restore(self):
        if self.item_type == "user":
            if self.owner_id == self.agent_id:
                raise Error(
                    "bad_request",
                    "Cannot restore user " + self.owner_name + " by itself",
                )

        ## Check if any item has as owner a deleted user
        users_to_check = set(
            [(desktop["user"], desktop["username"]) for desktop in self.desktops]
            + [(template["user"], template["username"]) for template in self.templates]
            + [
                (deployment["user"], deployment["user"])
                for deployment in self.deployments
            ]
        )
        users_in_entry = set([user["id"] for user in self.users])
        for user, username in users_to_check:
            if user not in users_in_entry:
                try:
                    CommonHelpers.itemExists("users", user)
                except Error as e:
                    if e.status_code == 404:
                        raise Error(
                            "not_found",
                            f'Can\'t restore. User "{str(username)}" has been deleted and owns items in this entry.',
                            description_code="unable_to_restore_user",
                            params={"user": username},
                        )

        ## Check if any item has associated deleted cateogry
        categories_to_check = set(
            [user["category"] for user in self.users]
            + [group["parent_category"] for group in self.groups]
        )
        categories_in_entry = set([category["id"] for category in self.categories])
        for category in categories_to_check:
            if category not in categories_in_entry:
                try:
                    CommonHelpers.itemExists("categories", category)
                except Error as e:
                    if e.status_code == 404:
                        raise Error(
                            "not_found",
                            f'Can\'t restore. Category "{str(category)}" has been deleted is associated to items in this entry.',
                            description_code="unable_to_restore_category",
                        )

        ## Check if any item has associated deleted group
        groups_to_check = set([user["group"] for user in self.users])
        groups_in_entry = set([group["id"] for group in self.groups])
        for group in groups_to_check:
            if group not in groups_in_entry:
                try:
                    CommonHelpers.itemExists("groups", group)
                except Error as e:
                    if e.status_code == 404:
                        raise Error(
                            "not_found",
                            f'Can\'t restore. Group "{str(group)}" has been deleted and is associated to items in this entry.',
                            description_code="unable_to_restore_group",
                        )

        if self.item_type not in ["user", "group", "category"]:
            ## Check quotas
            for desktop in self.desktops:
                if not desktop.get("tag"):
                    Quotas.desktop_create(desktop["user"])

            for template in self.templates:
                Quotas.template_create(template["user"])

            for deployment in self.deployments:
                users = [
                    {
                        "id": desktop["user"],
                        "username": desktop["username"],
                        "category": desktop["category"],
                        "group": desktop["group"],
                    }
                    for desktop in [
                        desktop
                        for desktop in self.desktops
                        if desktop.get("tag") == deployment["id"]
                    ]
                ]
                Quotas.deployment_create(
                    owner_id=deployment["user"],
                    quantity=1,
                    desktops_len=len(deployment["create_dict"]),
                    users=users,
                )

        ## Check if the recycled item has storage dependencies that are in the recycle bin or deleted
        if self.desktops:
            for desktop in self.desktops:
                if "parents" in desktop:
                    self.validate_parents(
                        desktop["parents"],
                        self.templates,
                        "Cannot restore desktop without parent template {}",
                    )

        if self.deployments:
            for deployment in self.deployments:
                # check if the templates of the deployment exist
                for create_dict_item in deployment["create_dict"]:
                    if create_dict_item["template"] not in [
                        t["id"] for t in self.templates
                    ]:
                        with self._rdb_context():
                            if (
                                not r.table("domains")
                                .get(create_dict_item["template"])
                                .run(self._rdb_connection)
                            ):
                                raise Error(
                                    "precondition_required",
                                    f"Cannot restore deployment without template {create_dict_item['template']}",
                                    description_code="template_not_found",
                                )

        if self.templates:
            for template in self.templates:
                with self._rdb_context():
                    parent_template = template.get("duplicate_parent_template")
                    if parent_template:
                        if not (
                            parent_template in [t["id"] for t in self.templates]
                            or r.table("domains")
                            .get(parent_template)
                            .run(self._rdb_connection)
                        ):
                            raise Error(
                                "precondition_required",
                                "Cannot restore duplicated template without parent template",
                                description_code="parent_template_not_found",
                            )
                    elif "parents" in template:
                        self.validate_parents(
                            template["parents"],
                            self.templates,
                            "Cannot restore template without parent template {}",
                        )

    def validate_parents(self, parents, templates, error_message):
        for parent in parents:
            # check if null in case of corrupted data caused by a convert template bug in previous versions
            if parent is not None:
                with self._rdb_context():
                    if not (
                        r.table("domains").get(parent).run(self._rdb_connection)
                        or any(t["id"] == parent for t in templates)
                    ):
                        raise Error(
                            "precondition_required",
                            error_message.format(parent),
                            description_code="parent_template_not_found",
                        )

    def restore(self):
        """
        Restore an entry including domains and storage. Call this function with RecycleBin object instanced with ID
        """
        if self.status in [
            RecycleBinStatusEnum.deleted.value,
            RecycleBinStatusEnum.restored.value,
        ]:
            raise Error(
                "precondition_required",
                "Cannot restore entry with status " + str(self.status),
            )
        if self.item_type != "user":
            try:
                CommonHelpers.itemExists("users", self.owner_id)
            except Exception:
                raise Error(
                    "not_found",
                    f"Can't restore entry. User "
                    + str(self.owner_name)
                    + " has been deleted.",
                    description_code="unable_to_restore_user",
                    params={"user": str(self.owner_name)},
                )
        self.check_can_restore()

        with self._rdb_context():
            r.table("users").insert(self.users).run(self._rdb_connection)
            r.table("groups").insert(self.groups).run(self._rdb_connection)
            r.table("categories").insert(self.categories).run(self._rdb_connection)

        storage_ids = [storage["id"] for storage in self.storages]
        try:
            with self._rdb_context():
                r.table("storage").get_all(*storage_ids).update(
                    {
                        "status": StorageStatusEnum.ready.value,
                        "status_logs": r.row["status_logs"].append(
                            {
                                "time": int(time.time()),
                                "status": StorageStatusEnum.ready.value,
                            }
                        ),
                    }
                ).run(self._rdb_connection)
        except Exception:
            raise Error("not found", "Invalid storage data")
        Helpers.update_status(
            self.id, self.owner_id, RecycleBinStatusEnum.restored.value
        )
        Helpers.add_log(
            RecycleBinStatusEnum.restored.value,
            self.id,
            self.agent_type,
            self.agent_id,
            self.agent_name,
            self.agent_category_id,
            self.agent_category_name,
            self.agent_role,
        )
        # Remove None entries from parents to avoid corrupted domains on restore
        with self._rdb_context():
            docs = self.desktops + self.templates
            r.table("domains").insert(
                r.expr(docs).map(
                    lambda d: d.without(
                        "hardware",
                        "xml_to_start",
                        "hardware_from_xml",
                        "force_update",
                        "last_hyp_id",
                    ).merge(
                        r.branch(
                            d.has_fields("parents")
                            & r.type_of(d["parents"]).eq("ARRAY"),
                            {"parents": d["parents"].filter(lambda p: p.ne(None))},
                            {},
                        )
                    )
                )
            ).run(self._rdb_connection)
        with self._rdb_context():
            r.table("targets").insert(self.targets).run(self._rdb_connection)
        with self._rdb_context():
            r.table("deployments").insert(self.deployments).run(self._rdb_connection)
        if self.categories:
            UserStorage.isard_user_storage_enable_categories(self.categories)
        elif self.groups:
            UserStorage.isard_user_storage_enable_groups(self.groups)
        elif self.users:
            UserStorage.isard_user_storage_enable_users(self.users)

    def delete_storage(self, user_id):
        """
        Permanently delete the storage disks associated with a recycle bin entry

        :param user_id: User ID of who is performing the action
        :type user_id: str
        :param move: True to move the disk file to deleted path instead of deleting it
        :type move: bool
        """
        if self.status in [
            RecycleBinStatusEnum.restored.value,
            RecycleBinStatusEnum.deleted.value,
        ]:
            raise Error(
                error="precondition_required",
                description="Cannot delete entry with status " + str(self.status),
            )

        # Delete the notifications_data user entries
        if self.users:
            users_ids = [user["id"] for user in self.users]
            NotificationsDataProcessed.delete_users_notifications_data(users_ids)

        start = absolute_start = time.time()
        tasks = []

        self._update_agent(user_id)
        log.debug(
            "RecycleBin %s delete_storage: Updated agent in %s seconds",
            self.id,
            time.time() - start,
        )

        if not self.storages:
            start = time.time()
            Helpers.update_status(
                self.id, self.owner_id, RecycleBinStatusEnum.deleted.value
            )
            log.debug(
                "RecycleBin %s delete_storage: No storages. Updated status to deleted in %s seconds and sent sockets",
                self.id,
                time.time() - start,
            )
        else:
            try:
                start = time.time()
                dependent_storages = self.dependent_storages()
                log.debug(
                    "RecycleBin %s delete_storage: Got dependent storages in %s seconds",
                    self.id,
                    time.time() - start,
                )

                entries_raw = [
                    {"id": self.id, "storages": self.storages}
                ] + dependent_storages
                # Remove entries duplicated with the same id in the list)
                unique_entries = {}
                for entry in entries_raw:
                    unique_entries[entry["id"]] = entry

                # Convert the dictionary values back to a list
                entries = list(unique_entries.values())
                if len(entries_raw) != len(entries):
                    log.warning(
                        "RecycleBin %s delete_storage: Found %s duplicated entries to delete in %s total",
                        self.id,
                        len(entries_raw) - len(entries),
                        len(entries_raw),
                    )
                else:
                    log.debug(
                        "RecycleBin %s delete_storage: No duplicated entries found in %s total",
                        self.id,
                        len(entries_raw),
                    )
                for entry in entries:
                    start = time.time()
                    rb = RecycleBin(entry["id"])
                    log.debug(
                        "RecycleBin %s delete_storage: RecycleBin %s loaded in %s seconds",
                        self.id,
                        rb.id,
                        time.time() - start,
                    )
                    start = time.time()
                    with self._rdb_context():
                        storages_status = list(
                            r.table("storage")
                            .get_all(r.args([storage["id"] for storage in rb.storages]))
                            .pluck("status")["status"]
                            .run(self._rdb_connection)
                        )
                    log.debug(
                        "RecycleBin %s delete_storage: Got storages status in %s seconds",
                        rb.id,
                        time.time() - start,
                    )
                    if all(x == "deleted" for x in storages_status):
                        start = time.time()
                        Helpers.update_status(
                            rb.id, self.owner_id, RecycleBinStatusEnum.deleted.value
                        )
                        log.debug(
                            "RecycleBin %s delete_storage: All storages status deleted. Updated status to deleted in %s seconds",
                            rb.id,
                            time.time() - start,
                        )
                    else:
                        start = time.time()
                        Helpers.update_status(
                            rb.id, self.owner_id, RecycleBinStatusEnum.deleting.value
                        )
                        log.debug(
                            "RecycleBin %s delete_storage: Not all storages status deleted. Updated status to deleting in %s seconds",
                            rb.id,
                            time.time() - start,
                        )
                        start = time.time()
                        Helpers.add_log(
                            "deleting",
                            entry["id"],
                            self.agent_type,
                            self.agent_id,
                            self.agent_name,
                            self.agent_category_id,
                            self.agent_category_name,
                            self.agent_role,
                        )
                        log.debug(
                            "RecycleBin %s delete_storage: Added log entry in %s seconds",
                            rb.id,
                            time.time() - start,
                        )
                        if not entry["storages"]:
                            start = time.time()
                            Helpers.update_status(
                                rb.id, RecycleBinStatusEnum.deleted.value
                            )
                            log.debug(
                                "RecycleBin %s delete_storage: No storages. Updated status to deleted in %s seconds",
                                rb.id,
                                time.time() - start,
                            )
                        for storage in rb.storages:
                            start = time.time()
                            exists = Storage.exists(storage["id"])
                            log.debug(
                                "RecycleBin %s delete_storage: Checked if storage %s exists in %s seconds",
                                rb.id,
                                storage["id"],
                                time.time() - start,
                            )
                            if not exists:
                                continue
                            start = time.time()
                            storage = Storage(storage["id"])
                            if storage.status == RecycleBinStatusEnum.deleted.value:
                                continue
                            if storage.status != RecycleBinStatusEnum.recycled.value:
                                storage.status = RecycleBinStatusEnum.recycled.value
                            move = Helpers.get_delete_action() == "move"
                            task_name = "move_delete" if move else "delete"
                            log.debug(
                                "RecycleBin %s delete_storage: Storage %s loaded in %s seconds",
                                rb.id,
                                storage.id,
                                time.time() - start,
                            )
                            start = time.time()
                            task = Task(
                                user_id=rb.owner_id,
                                queue=f"storage.{StoragePool.get_best_for_action('delete', path=storage.directory_path).id}.default",
                                task=task_name,
                                job_kwargs={
                                    "kwargs": {
                                        "path": storage.path,
                                    },
                                },
                                dependents=[
                                    {
                                        "queue": "core",
                                        "task": "update_status",
                                        "job_kwargs": {
                                            "kwargs": {
                                                "statuses": {
                                                    "finished": {
                                                        "deleted": {
                                                            "storage": [storage.id]
                                                        },
                                                    },
                                                    "failed": {
                                                        "recycled": {
                                                            "storage": [storage.id]
                                                        },
                                                    },
                                                    "canceled": {
                                                        "recycled": {
                                                            "storage": [storage.id]
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                        "dependents": [
                                            {
                                                "queue": "core",
                                                "task": "recycle_bin_update",
                                                "job_kwargs": {
                                                    "kwargs": {"recycle_bin_id": rb.id}
                                                },
                                            },
                                            {
                                                "queue": "core",
                                                "task": "storage_delete",
                                                "job_kwargs": {
                                                    "kwargs": {"storage_id": storage.id}
                                                },
                                            },
                                        ],
                                    }
                                ],
                            )
                            log.debug(
                                "RecycleBin %s delete_storage: Storage %s task %s created in %s seconds",
                                rb.id,
                                storage.id,
                                task_name,
                                time.time() - start,
                            )
                            # Throttle RQ submissions to avoid overwhelming workers
                            if len(tasks) % 10 == 0:
                                time.sleep(0.2)
                            start = time.time()
                            rb._add_task(
                                {
                                    "id": task.id,
                                    "item_id": storage.id,
                                    "item_type": "storage",
                                    "status": task.status,
                                }
                            )
                            log.debug(
                                "RecycleBin %s delete_storage: Added task %s to recycle bin in %s seconds",
                                rb.id,
                                task.id,
                                time.time() - start,
                            )
                            tasks.append(
                                {
                                    "id": task.id,
                                    "storage_id": storage.id,
                                    "status": task.status,
                                }
                            )

            except Exception as e:
                raise Error(
                    "internal_server",
                    "Error when deleting recycle bin entry",
                    traceback.format_exc(),
                )

        if self.categories:
            start = time.time()
            groups = [group["id"] for group in self.groups]
            UserStorage.isard_user_storage_remove_categories(self.categories, groups)
            log.debug(
                "RecycleBin %s delete_storage: Removed categories in %s seconds",
                self.id,
                time.time() - start,
            )
        elif self.groups:
            start = time.time()
            UserStorage.isard_user_storage_remove_groups(self.groups)
            log.debug(
                "RecycleBin %s delete_storage: Removed groups in %s seconds",
                self.id,
                time.time() - start,
            )
        elif self.users:
            start = time.time()
            UserStorage.isard_user_storage_remove_users(self.users)
            log.debug(
                "RecycleBin %s delete_storage: Removed users in %s seconds",
                self.id,
                time.time() - start,
            )

        log.debug(
            "RecycleBin %s delete_storage: Finished in %s seconds",
            self.id,
            time.time() - absolute_start,
        )
        return tasks

    # Get the recycle bin entries with storages that depend on the current recycle bin entry templates
    def dependent_storages(self):
        templates = [template["id"] for template in self.templates]
        dependent_rb = self.get_template_dependant_recycle_bin_entries(
            templates, "parents"
        ) + self.get_template_dependant_recycle_bin_entries(
            templates, "duplicate_parent_template"
        )
        return dependent_rb

    def get_template_dependant_recycle_bin_entries(self, templates, index):
        with self._rdb_context():
            return list(
                r.table("recycle_bin")
                .get_all(r.args(templates), index=index)
                .filter(lambda rb: rb["status"] == RecycleBinStatusEnum.recycled.value)
                .filter(lambda rb: rb["id"].ne(self.id))
                .pluck({"id": True, "storages": ["id"]})
                .distinct()
                .run(self._rdb_connection)
            )

    # @classmethod
    # def get_all(cls, category_id=None, user_id=None):
    #     """
    #     Get all recycle bin entries.

    #     :return: Recycle bin entries
    #     :rtype: list
    #     """
    #     query = r.table("recycle_bin")
    #     if user_id:
    #         query = query.filter({"owner_id": user_id, "status": RecycleBinStatusEnum.recycled.value})
    #     elif category_id:
    #         query = query.filter({"owner_category_id": category_id})

    #     with cls._rdb_context():
    #         query = list(query.run(cls._rdb_connection))

    #     # for storage in query
    #     # new key category in storage
    #     # category is category name of user_id in storage
    #     return query

    @classmethod
    def set_old_entries_max_time(cls, max_time):
        with cls._rdb_context():
            r.table("config").update(
                {"recycle_bin": {"old_entries": {"max_time": max_time}}}
            ).run(cls._rdb_connection)

    @classmethod
    def set_old_entries_action(cls, action):
        with cls._rdb_context():
            if action == "none":
                r.table("config").replace(
                    r.row.without({"recycle_bin": "old_entries"})
                ).run(cls._rdb_connection)
            else:
                r.table("config").update(
                    {"recycle_bin": {"old_entries": {"action": action}}}
                ).run(cls._rdb_connection)

    @classmethod
    def delete_old_entries(cls, rcb_list):
        with cls._rdb_context():
            results = (
                r.table("recycle_bin")
                .get_all(r.args(rcb_list))
                .delete()
                .run(cls._rdb_connection, array_limit=500000)
            )

    # @classmethod
    # def archive_old_entries(cls, rcb_list):
    #     with cls._rdb_context():
    #         results = (
    #             r.table("recycle_bin_archive")
    #             .insert(rcb_list, conflict="update")
    #             .run(cls._rdb_connection)
    #         )
    #         if results["inserted"]:
    #             ids = [rcb["id"] for rcb in rcb_list]
    #             cls.delete_old_entries(ids)

    @classmethod
    def set_default_delete(cls, set_default):
        with cls._rdb_context():
            r.table("config")[0].update(
                {"recycle_bin": {"default_delete": set_default}}
            ).run(cls._rdb_connection)

    @classmethod
    def set_delete_action(cls, action):
        with cls._rdb_context():
            r.table("config")[0].update({"recycle_bin": {"delete_action": action}}).run(
                cls._rdb_connection
            )

    @classmethod
    def get_all_unused_item_timeout(cls):
        with cls._rdb_context():
            return list(
                r.db("isard").table("unused_item_timeout").run(cls._rdb_connection)
            )

    @classmethod
    def get_unused_item_timeout(cls, rule_id):
        with cls._rdb_context():
            return r.table("unused_item_timeout").get(rule_id).run(cls._rdb_connection)

    @classmethod
    def update_unused_item_timeout(cls, rule_id, data):
        with cls._rdb_context():
            r.table("unused_item_timeout").get(rule_id).update(data).run(
                cls._rdb_connection
            )

    @classmethod
    def create_unused_item_timeout(cls, data):
        with cls._rdb_context():
            r.table("unused_item_timeout").insert(data).run(cls._rdb_connection)

    @classmethod
    def delete_unused_item_timeout(cls, rule_id):
        with cls._rdb_context():
            r.table("unused_item_timeout").get(rule_id).delete().run(
                cls._rdb_connection
            )


class RecycleBinDomain(RecycleBin):
    def __init__(self, id=None, item_type="desktop", user_id=None):
        super().__init__(id, item_type=item_type, user_id=user_id)

    def add(self, domain_id):
        CommonHelpers.desktops_stop([domain_id], 5)
        # Move desktop to recycle_bin
        with self._rdb_context():
            domain = r.table("domains").get(domain_id).run(self._rdb_connection)

        # Set item_name BEFORE add_domain to ensure it's set even if operations fail
        if not self.item_name and domain:
            domain_name = domain.get("name", f"Desktop {domain_id}")
            self._add_item_name(domain_name)

        self.add_domain(domain)
        try:
            self.add_target(Targets.get_domain_target(domain_id))
        except Exception:
            pass
        super()._add_owner(domain["user"])
        with self._rdb_context():
            r.table("domains").get(domain_id).delete().run(self._rdb_connection)
        Targets.delete_domain_target(domain_id)
        return self._set_data(self.id)

    def add_domain(self, domain):
        if domain["kind"] == "desktop":
            with self._rdb_context():
                r.table("recycle_bin").get(self.id).update(
                    {"desktops": r.row["desktops"].append(domain)}
                ).run(self._rdb_connection)
            Bookings.delete_item_bookings("desktop", domain["id"])
        if domain["kind"] == "template":
            with self._rdb_context():
                r.table("recycle_bin").get(self.id).update(
                    {"templates": r.row["templates"].append(domain)}
                ).run(self._rdb_connection)
        # Move its disk to recycle_bin
        if not (
            domain["kind"] == "template" and domain.get("duplicate_parent_template")
        ):

            for disk in domain["create_dict"]["hardware"]["disks"]:
                if "storage_id" in disk:
                    with self._rdb_context():
                        storage = (
                            r.table("storage")
                            .get(disk["storage_id"])
                            .run(self._rdb_connection)
                        )
                    if storage:
                        RecycleBinStorage(self.id).add(disk["storage_id"])

    def add_desktops(self, desktops):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"desktops": r.row["desktops"].add(desktops)}
            ).run(self._rdb_connection)

        rcb_storage = RecycleBinStorage(id=self.id, user_id=self.agent_id)
        storages_ids = []
        for desktop in desktops:
            Bookings.delete_item_bookings("desktop", desktop["id"])

            for disk in desktop["create_dict"]["hardware"]["disks"]:
                if "storage_id" in disk:
                    storages_ids.append(disk["storage_id"])
        storages = []
        for i in range(0, len(storages_ids), 200):
            batch_ids = storages_ids[i : i + 200]
            with self._rdb_context():
                storages += (
                    r.table("storage")
                    .get_all(r.args(batch_ids))
                    .run(self._rdb_connection)
                )
            with self._rdb_context():
                r.table("storage").get_all(r.args(batch_ids)).update(
                    {
                        "status": RecycleBinStatusEnum.recycled.value,
                        "status_logs": r.row["status_logs"].append(
                            {
                                "time": int(time.time()),
                                "status": RecycleBinStatusEnum.recycled.value,
                            }
                        ),
                    }
                ).run(self._rdb_connection)
        rcb_storage.add_storages(storages)

    def add_target(self, target):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"targets": r.row["targets"].append(target)}
            ).run(self._rdb_connection)


class RecycleBinDesktop(RecycleBinDomain):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="desktop", user_id=user_id)


class RecycleBinTemplate(RecycleBinDomain):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="template", user_id=user_id)

    def add(self, template_id=None):
        """
        Adds a recycle bin entry for templates.

        :param template_id: ID of the template to recycle. All derived templates and desktops will also be recycled
        :type template_id: str, None
        """

        # First recycle deployments to avoid overlapping desktops deletions
        deployments = CommonHelpers.get_template_derivated_deployments(template_id)
        failed_deployments = []
        for deployment in deployments:
            try:
                rcb_deployment = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
                rcb_deployment.add(deployment["id"])
            except Exception as e:
                log.error(
                    f"Failed to recycle deployment {deployment['id']} while deleting template {template_id}: {e}"
                )
                failed_deployments.append(deployment["id"])

        if failed_deployments:
            raise Error(
                "precondition_required",
                f"Failed to recycle some deployments: {failed_deployments}. Template deletion aborted.",
                traceback.format_exc(),
                description_code="deployment_recycle_failed",
            )

        if template_id:
            with self._rdb_context():
                template = r.table("domains").get(template_id).run(self._rdb_connection)
            if template is None:
                raise Error(
                    "not_found",
                    f"Template {template_id} not found",
                    description_code="template_not_found",
                )
            self._add_item_name(template["name"])
            # Get template ids tree
            data = CommonHelpers.get_template_with_all_derivatives(
                template_id, user_id=self.agent_id
            )

        domains = [
            {
                "id": t["id"],
                "kind": t["kind"],
                "user": t["user"],
                "category": t["category"],
                "group": t["group"],
            }
            for t in data
        ]

        # Move each desktop/template to recycle_bin
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        for domain in domains:
            if domain["kind"] == "template":
                super().add(domain["id"])
            else:
                rcb_desktop.add(domain["id"])
        super()._add_owner(template["user"])
        return self._set_data(self.id)


class RecycleBinStorage(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="storage", user_id=user_id)

    def add(self, storage_id):
        with self._rdb_context():
            storage = r.table("storage").get(storage_id).run(self._rdb_connection)
        self.add_storage(storage)
        super()._add_owner(storage["user_id"])
        with self._rdb_context():
            r.table("storage").get(storage_id).update(
                {
                    "status": RecycleBinStatusEnum.recycled.value,
                    "status_logs": r.row["status_logs"].append(
                        {
                            "time": int(time.time()),
                            "status": RecycleBinStatusEnum.recycled.value,
                        }
                    ),
                }
            ).run(self._rdb_connection)
        return self._set_data(self.id)

    def add_storage(self, storage):
        if storage:
            with self._rdb_context():
                r.table("recycle_bin").get(self.id).update(
                    {
                        "storages": r.row["storages"].append(storage),
                        "size": r.row["size"]
                        + storage.get("qemu-img-info", {}).get("actual-size", 0),
                    }
                ).run(self._rdb_connection)

    def add_storages(self, storages):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"storages": r.row["storages"].add(storages)}
            ).run(self._rdb_connection)


class RecycleBinDeployment(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="deployment", user_id=user_id)

    def add(self, deployment_id):
        with self._rdb_context():
            deployment = (
                r.table("deployments").get(deployment_id).run(self._rdb_connection)
            )
        if not deployment:
            raise Error(
                "not_found",
                f"Deployment {deployment_id} not found in database",
            )
        self.add_deployment(deployment)
        if not self.item_name:
            self._add_item_name(deployment["name"])
        super()._add_owner(deployment["user"])
        with self._rdb_context():
            r.table("deployments").get(deployment_id).delete().run(self._rdb_connection)
        return self._set_data(self.id)

    def add_deployment(self, deployment):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"deployments": r.row["deployments"].append(deployment)}
            ).run(self._rdb_connection)
            desktops_ids = list(
                r.table("domains")
                .get_all(deployment["id"], index="tag")
                .pluck("id")["id"]
                .run(self._rdb_connection)
            )
        CommonHelpers.desktops_stop(desktops_ids, 5)
        with self._rdb_context():
            # Move deployment desktops to recycle_bin
            desktops = list(
                r.table("domains")
                .get_all(deployment["id"], index="tag")
                .run(self._rdb_connection)
            )
        Bookings.delete_item_bookings("deployment", deployment["id"])
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with self._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(deployment["id"], index="tag")
                .delete()
                .run(self._rdb_connection)
            )

    def add_deployments(self, deployments):
        with self._rdb_context():
            r.table("recycle_bin").get(self.id).update(
                {"deployments": r.row["deployments"].add(deployments)}
            ).run(self._rdb_connection)
        deployments_ids = [deployment["id"] for deployment in deployments]
        with self._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .pluck("id")["id"]
                .run(self._rdb_connection)
            )
        CommonHelpers.desktops_stop(desktops_ids, 5)
        # Move deployment desktops to recycle_bin
        with self._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .run(self._rdb_connection)
            )
        for deployment in deployments:
            Bookings.delete_item_bookings("deployment", deployment["id"])
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with self._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .delete()
                .run(self._rdb_connection)
            )


class RecycleBinBulk(RecycleBin):
    def __init__(self, id=None, item_type="bulk", user_id=None):
        super().__init__(id, item_type=item_type, user_id=user_id)

    def add(self, desktops_ids, owner_id=None, name=None):
        super()._add_owner(owner_id or self.agent_id)
        if name:
            super()._add_item_name(name)
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        desktops = []

        for i in range(0, len(desktops_ids), 200):
            batch_ids = desktops_ids[i : i + 200]
            CommonHelpers.desktops_stop(batch_ids, 5)
            # Move desktops to recycle_bin
            with self._rdb_context():
                desktops += list(
                    r.table("domains")
                    .get_all(r.args(batch_ids))
                    .run(self._rdb_connection)
                )
            with self._rdb_context():
                r.table("domains").get_all(r.args(batch_ids)).delete().run(
                    self._rdb_connection
                )
        rcb_desktop.add_desktops(desktops)
        return self._set_data(self.id)


class RecycleBinDeploymentDesktops(RecycleBinBulk):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="deployment_users_delete", user_id=user_id)


class RecycleBinUser(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="user", user_id=user_id)

    # TODO: When removing a user check if there's any dependant recycle bin entry
    def add(self, user_id, delete_user=True):
        # Delete user
        with self._rdb_context():
            user = r.table("users").get(user_id).run(self._rdb_connection)
        self.add_user(user, delete_user)
        if not self.item_name:
            self._add_item_name(user["name"])
        super()._add_owner(user["id"])
        if delete_user:
            with self._rdb_context():
                r.table("users").get(user_id).delete().run(self._rdb_connection)
        return self._set_data(self.id)

    def add_user(self, user, delete_user=True):
        with self._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", user["id"]], index="kind_user")
                .pluck("id")["id"]
                .run(self._rdb_connection)
            )
        CommonHelpers.desktops_stop(desktops_ids, 5)
        # Delete desktops
        with self._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user["id"]], index="kind_user")
                .run(self._rdb_connection)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with self._rdb_context():
            r.table("domains").get_all(
                ["desktop", user["id"]], index="kind_user"
            ).delete().run(self._rdb_connection)
        # Delete templates
        with self._rdb_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", user["id"]], index="kind_user")["id"]
                .run(self._rdb_connection)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with self._rdb_context():
            r.table("domains").get_all(
                ["template", user["id"]], index="kind_user"
            ).delete().run(self._rdb_connection)
        # Delete deployments
        with self._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(user["id"], index="user")
                .run(self._rdb_connection)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)
        with self._rdb_context():
            r.table("deployments").get_all(user["id"], index="user").delete().run(
                self._rdb_connection
            )
        # Remove the user from all the resources allowed field
        for table in [
            "deployments",
            "domains",
            "media",
            "interfaces",
            "videos",
            "reservables_vgpus",
            "boots",
            "graphics",
            "desktops_priority",
            "qos_net",
        ]:
            CommonHelpers.unassign_item_from_resource(user["id"], "users", table)
        # Remove the user from the migration exceptions table
        Helpers.delete_items_from_migration_exceptions(user["id"], "user")
        if delete_user:
            with self._rdb_context():
                r.table("recycle_bin").get(self.id).update(
                    {
                        "users": r.row["users"].append(user),
                    }
                ).run(self._rdb_connection)
            UserStorage.isard_user_storage_disable_users([user])

            with self._rdb_context():
                r.table("users_migrations").get_all(
                    user["id"], index="origin_user"
                ).filter({"status": MigrationsStatusEnum.exported.value}).delete().run(
                    self._rdb_connection
                )


class RecycleBinGroup(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="group", user_id=user_id)

    # TODO: When removing a group check if there's any dependant recycle bin entry
    def add(self, group_id):
        # Delete group
        with self._rdb_context():
            group = r.table("groups").get(group_id).run(self._rdb_connection)
        self.add_group(group)
        if not self.item_name:
            self._add_item_name(group["name"])
        super()._add_owner(self.agent_id)
        with self._rdb_context():
            r.table("groups").get(group_id).delete().run(self._rdb_connection)
        return self._set_data(self.id)

    def add_group(self, group):
        with self._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .pluck("id")["id"]
                .run(self._rdb_connection)
            )
        CommonHelpers.desktops_stop(desktops_ids, 5)
        # Delete desktops
        with self._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .run(self._rdb_connection)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with self._rdb_context():
            r.table("domains").get_all(
                ["desktop", group["id"]], index="kind_group"
            ).delete().run(self._rdb_connection)
        # Delete templates
        with self._rdb_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", group["id"]], index="kind_group")["id"]
                .run(self._rdb_connection)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with self._rdb_context():
            r.table("domains").get_all(
                ["template", group["id"]], index="kind_group"
            ).delete().run(self._rdb_connection)
        # Delete deployments
        with self._rdb_context():
            users = list(
                r.table("users")
                .get_all(group["id"], index="group")
                .run(self._rdb_connection)
            )
        users_ids = [user["id"] for user in users]
        with self._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(r.args(users_ids), index="user")
                .run(self._rdb_connection)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)

        # Remove the group from the migration exceptions table
        Helpers.delete_items_from_migration_exceptions(group["id"], "group")
        with self._rdb_context():
            r.table("deployments").get_all(
                r.args(users_ids), index="user"
            ).delete().run(self._rdb_connection)
            r.table("recycle_bin").get(self.id).update(
                {
                    "users": r.row["users"].add(users),
                    "groups": r.row["groups"].append(group),
                }
            ).run(self._rdb_connection)
            r.table("users").get_all(group["id"], index="group").delete().run(
                self._rdb_connection
            )
        # Remove the user from all the resources allowed field
        for table in [
            "deployments",
            "domains",
            "media",
            "interfaces",
            "videos",
            "reservables_vgpus",
            "boots",
            "graphics",
            "desktops_priority",
            "qos_net",
        ]:
            CommonHelpers.unassign_item_from_resource(group["id"], "groups", table)
        UserStorage.isard_user_storage_disable_groups([group])


class RecycleBinCategory(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="category", user_id=user_id)

    # TODO: When removing a group check if there's any dependant recycle bin entry
    def add(self, category_id):
        # Delete group
        with self._rdb_context():
            category = r.table("categories").get(category_id).run(self._rdb_connection)
        self.add_category(category)
        if not self.item_name:
            self._add_item_name(category["name"])
        super()._add_owner(self.agent_id)
        with self._rdb_context():
            r.table("categories").get(category_id).delete().run(self._rdb_connection)
        return self._set_data(self.id)

    def add_category(self, category):
        with self._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .pluck("id")["id"]
                .run(self._rdb_connection)
            )
        CommonHelpers.desktops_stop(desktops_ids, 5)
        # Delete desktops
        with self._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .run(self._rdb_connection)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with self._rdb_context():
            r.table("domains").get_all(
                ["desktop", category["id"]], index="kind_category"
            ).delete().run(self._rdb_connection)
        # Delete templates
        with self._rdb_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", category["id"]], index="kind_category")["id"]
                .run(self._rdb_connection)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with self._rdb_context():
            r.table("domains").get_all(
                ["template", category["id"]], index="kind_category"
            ).delete().run(self._rdb_connection)
        # Delete deployments
        with self._rdb_context():
            users = list(
                r.table("users")
                .get_all(category["id"], index="category")
                .run(self._rdb_connection)
            )
        users_ids = [user["id"] for user in users]
        with self._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(r.args(users_ids), index="user")
                .run(self._rdb_connection)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)

        # Remove the category from the migration exceptions table
        Helpers.delete_items_from_migration_exceptions(category["id"], "category")
        with self._rdb_context():
            r.table("deployments").get_all(
                r.args(users_ids), index="user"
            ).delete().run(self._rdb_connection)
            groups = list(
                r.table("groups")
                .get_all(category["id"], index="parent_category")
                .run(self._rdb_connection)
            )
            r.table("recycle_bin").get(self.id).update(
                {
                    "users": r.row["users"].add(users),
                    "groups": r.row["groups"].add(groups),
                    "categories": r.row["categories"].append(category),
                }
            ).run(self._rdb_connection)
            r.table("users").get_all(category["id"], index="category").delete().run(
                self._rdb_connection
            )
            r.table("groups").get_all(
                category["id"], index="parent_category"
            ).delete().run(self._rdb_connection)
        # Remove the user from all the resources allowed field
        for table in [
            "deployments",
            "domains",
            "media",
            "interfaces",
            "videos",
            "reservables_vgpus",
            "boots",
            "graphics",
            "desktops_priority",
            "qos_net",
        ]:
            for group in groups:
                CommonHelpers.unassign_item_from_resource(group["id"], "groups", table)
            CommonHelpers.unassign_item_from_resource(
                category["id"], "categories", table
            )
        UserStorage.isard_user_storage_disable_categories([category])
