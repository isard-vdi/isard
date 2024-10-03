import traceback
from datetime import datetime, timedelta

from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

from ..views.decorators import itemExists

r = RethinkDB()
import logging as log
import threading
import time
from queue import Empty, Queue

from isardvdi_common.api_exceptions import Error
from isardvdi_common.storage import Storage
from isardvdi_common.storage_pool import StoragePool
from isardvdi_common.task import Task

from api import socketio

from ..libv2.api_user_storage import (
    isard_user_storage_disable_categories,
    isard_user_storage_disable_groups,
    isard_user_storage_disable_users,
    isard_user_storage_enable_categories,
    isard_user_storage_enable_groups,
    isard_user_storage_enable_users,
    isard_user_storage_remove_categories,
    isard_user_storage_remove_groups,
    isard_user_storage_remove_users,
)
from ..libv2.quotas import Quotas
from .bookings.api_booking import Bookings
from .flask_rethink import RDB
from .helpers import GetTemplateWithAllDerivatives, desktops_stop

quotas = Quotas()

apib = Bookings()

db = RDB(app)
db.init_app(app)


class RecycleBinDeleteQueue:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "initialized"):
            self.queue = Queue()
            self.recycle_bin_ids = set()
            self.stop_event = threading.Event()
            self.worker_thread = threading.Thread(target=self._background_worker)
            self.worker_thread.daemon = (
                True  # Allows the thread to exit when the main program exits
            )
            self.worker_thread.start()
            self.initialized = True

    def enqueue(self, item):
        recycle_bin_id = item.get("recycle_bin_id")
        if recycle_bin_id not in self.recycle_bin_ids:
            update_status(recycle_bin_id, item.get("user_id"), "queued")
            self.queue.put(item)
            self.recycle_bin_ids.add(recycle_bin_id)
            app.logger.debug(
                f"Item with recycle_bin_id {recycle_bin_id} added to the queue."
            )
        else:
            app.logger.debug(
                f"Item with recycle_bin_id {recycle_bin_id} is already in the queue."
            )

    def dequeue(self):
        try:
            item = self.queue.get(
                timeout=1
            )  # Timeout to allow thread to check for stop_event
            self.recycle_bin_ids.remove(item.get("recycle_bin_id"))
            return item
        except Empty:
            return None

    def perform_operation(self, recycle_bin_id, user_id):
        # Example operation using user_id
        app.logger.debug(f"Performing operation with user_id {user_id}")
        rb = RecycleBin(id=recycle_bin_id)
        rb.delete_storage(user_id)

    def process_next_item(self):
        item = self.dequeue()
        if item:
            user_id = item.get("user_id")
            recycle_bin_id = item.get("recycle_bin_id")
            self.perform_operation(recycle_bin_id, user_id)
            self.queue.task_done()
        else:
            app.logger.debug("No items to process.")

    def _background_worker(self):
        while not self.stop_event.is_set():
            self.process_next_item()
            time.sleep(0.1)  # Add a small sleep to prevent a tight loop

    def stop(self):
        self.stop_event.set()
        self.worker_thread.join()


@cached(cache=TTLCache(maxsize=10, ttl=30))
def get_status(category_id=None):

    query = r.table("recycle_bin")
    if category_id:
        query = query.get_all(category_id, index="owner_category")
    query = (
        query.group("status")
        .count()
        .ungroup()
        .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
    )
    with app.app_context():
        return list(query.run(db.conn))


@cached(cache=TTLCache(maxsize=50, ttl=30))
def get_category_data(category_id):
    with app.app_context():
        return (
            r.table("categories")
            .get(category_id)
            .pluck("id", "name")
            .default({"id": category_id, "name": "[Deleted]"})
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=50, ttl=30))
def get_group_data(group_id):
    with app.app_context():
        return (
            r.table("groups")
            .get(group_id)
            .pluck("id", "name")
            .default({"id": group_id, "name": "[Deleted]"})
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=50, ttl=30))
def get_user_data(user_id):
    with app.app_context():
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
            .run(db.conn)
        )
        category = get_category_data(user["category"])
        group = get_group_data(user["group"])
    return {
        "user_id": user["id"],
        "user_name": user["name"],
        "category_name": category["name"],
        "category_id": category["id"],
        "group_name": group["name"],
        "group_id": group["id"],
        "role": user["role"],
    }


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get(recycle_bin_id=None, all_data=None):
    """
    Get one recycle bin entry.

    :param recycle_bin_id: RecycleBin ID
    :param all_data: Get specific data about domains and storages
    :type all_data: bool
    :type recycle_bin_id: str
    :return: Recycle bin entry
    :rtype: dict
    """

    with app.app_context():
        result = r.table("recycle_bin").get(recycle_bin_id).run(db.conn)

    if all_data:
        for domain in result["desktops"] + result["templates"]:
            category = get_category_data(domain["category"])
            group = get_group_data(domain["group"])
            domain["category"] = category
            domain["group"] = group

        for storage in result["storages"]:
            storage["domains"] = []
            for domain in result["desktops"] + result["templates"]:
                for disk in domain["create_dict"]["hardware"]["disks"]:
                    if disk["storage_id"] == storage["id"]:
                        storage["domains"].append(domain["name"])
                        storage["category"] = domain["category"]
                        storage["user"] = domain["username"]

        for deployment in result["deployments"]:
            user = get_user_data(deployment["user"])
            category = get_category_data(user["category_id"])
            group = get_group_data(user["group_id"])
            user = (
                r.table("users")
                .get(deployment["user"])
                .default({"username": "[Deleted]"})
            )
            deployment["user"] = user["username"].run(db.conn)
            deployment["category"] = category
            deployment["group"] = group

        for user in result["users"]:
            user["category"] = get_category_data(user["category"])["name"]
            user["group"] = get_group_data(user["group"])["name"]
    return result


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get_recycle_bin_by_period(max_delete_period, category=None):
    if category:
        if max_delete_period == 0:
            with app.app_context():
                recycle_bin_list = list(
                    r.table("recycle_bin")
                    .get_all("recycled", index="status")
                    .filter({"owner_category_id": category})["id"]
                    .run(db.conn)
                )
        else:
            max_delete_period = timedelta(hours=max_delete_period)
            with app.app_context():
                recycle_bin_list = list(
                    r.table("recycle_bin")
                    .get_all("recycled", index="status")
                    .filter(
                        r.row["accessed"]
                        < (datetime.now() - max_delete_period).timestamp()
                    )
                    .filter({"owner_category_id": category})["id"]
                    .run(db.conn)
                )
    else:
        if max_delete_period == 0:
            with app.app_context():
                recycle_bin_list = list(
                    r.table("recycle_bin")
                    .get_all("recycled", index="status")["id"]
                    .run(db.conn)
                )
        else:
            max_delete_period = timedelta(hours=max_delete_period)
            with app.app_context():
                recycle_bin_list = list(
                    r.table("recycle_bin")
                    .get_all("recycled", index="status")
                    .filter(
                        r.row["accessed"]
                        < (datetime.now() - max_delete_period).timestamp()
                    )["id"]
                    .run(db.conn)
                )
    return recycle_bin_list


def update_status(rb_id, owner_id, status):
    with app.app_context():
        r.table("recycle_bin").get(rb_id).update({"status": status}).run(db.conn)
    kind = "update_recycle_bin" if status != "deleted" else "delete_recycle_bin"
    start = time.time()
    send_socket_user(
        kind,
        {"id": rb_id, "status": status},
        owner_id,
    )
    send_socket_admin(kind, {"id": rb_id, "status": status})
    log.debug(
        "RecycleBin %s update_status: Sent socket events in %s seconds",
        rb_id,
        time.time() - start,
    )


def update_task_status(task):
    start = absolute_start = time.time()
    with app.app_context():
        rb = (
            r.table("recycle_bin")
            .get(task["recycle_bin_id"])
            .pluck(
                {
                    "owner_id": True,
                    "agent_type": True,
                    "agent_id": True,
                    "agent_name": True,
                    "agent_category_id": True,
                    "agent_category_name": True,
                    "agent_role": True,
                    "tasks": True,
                    "storages": {"id"},
                }
            )
            .run(db.conn)
        )
    log.debug(
        "RecycleBin %s update_task_status: Got recycle bin in %s seconds",
        task["recycle_bin_id"],
        time.time() - start,
    )

    start = time.time()
    for t in rb["tasks"]:
        if t["id"] == task["id"]:
            t["status"] = task["status"]
            break
    log.debug(
        "RecycleBin %s update_task_status: Updated task status in %s seconds",
        task["recycle_bin_id"],
        time.time() - start,
    )

    # Check if all the recycle bin tasks are finished then update the recycle bin status to deleted
    start = time.time()
    finished_tasks = list(filter(lambda t: (t["status"] == "finished"), rb["tasks"]))
    log.debug(
        "RecycleBin %s update_task_status: Filtered finished tasks in %s seconds",
        task["recycle_bin_id"],
        time.time() - start,
    )

    if len(finished_tasks) == len(rb["storages"]):
        start = time.time()
        with app.app_context():
            r.table("recycle_bin").get(task["recycle_bin_id"]).update(
                {
                    "status": "deleted",
                    "tasks": r.row["tasks"].map(
                        lambda rb_task: r.branch(
                            rb_task["id"] == task["id"],
                            rb_task.merge({"status": task["status"]}),
                            rb_task,
                        )
                    ),
                }
            ).run(db.conn)
        log.debug(
            "RecycleBin %s update_task_status: Updated recycle bin status to deleted in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )
        start = time.time()
        send_socket_user(
            "update_recycle_bin",
            {"id": task["recycle_bin_id"], "status": "deleted"},
            rb["owner_id"],
        )
        send_socket_admin(
            "update_recycle_bin",
            {"id": task["recycle_bin_id"], "status": "deleted"},
        )
        log.debug(
            "RecycleBin %s update_task_status: Sent socket events in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )
        start = time.time()
        add_log(
            "deleted",
            task["recycle_bin_id"],
            rb["agent_type"],
            rb["agent_id"],
            rb["agent_name"],
            rb["agent_category_id"],
            rb["agent_category_name"],
            rb["agent_role"],
        )
        log.debug(
            "RecycleBin %s update_task_status: Added log entry in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )
    # Otherwise only update the tasks status
    else:
        start = time.time()
        with app.app_context():
            r.table("recycle_bin").get(task["recycle_bin_id"]).update(
                {
                    "tasks": r.row["tasks"].map(
                        lambda rb_task: r.branch(
                            rb_task["id"] == task["id"],
                            rb_task.merge({"status": task["status"]}),
                            rb_task,
                        )
                    )
                }
            ).run(db.conn)
        log.debug(
            "RecycleBin %s update_task_status: Updated tasks status in %s seconds",
            task["recycle_bin_id"],
            time.time() - start,
        )
    log.debug(
        "RecycleBin %s update_task_status: Finished in %s seconds",
        task["recycle_bin_id"],
        time.time() - absolute_start,
    )


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get_user_recycle_bin_ids(user_id, status):
    """
    Get all the users recycle_bins ids

    :param user_id: User ID
    :type user_id: str
    :return: IDs of the user recycle bins
    :rtype: array
    """
    with app.app_context():
        return list(
            r.table("recycle_bin")
            .get_all([user_id, status], index="owner_status")
            .filter({"agent_id": user_id})["id"]
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get_count(recycle_bin_id):
    with app.app_context():
        return (
            r.table("recycle_bin")
            .get(recycle_bin_id)
            .merge(
                {
                    "desktops": r.row["desktops"].count(),
                    "templates": r.row["templates"].count(),
                    "storages": r.row["storages"].count(),
                    "deployments": r.row["deployments"].count(),
                    "categories": r.row["categories"].count(),
                    "groups": r.row["groups"].count(),
                    "users": r.row["users"].count(),
                }
            )
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get_item_count(user_id=None, category_id=None, status=None):
    query = r.table("recycle_bin")
    if user_id:
        query = query.get_all([user_id, "recycled"], index="owner_status")
    elif category_id:
        if status:
            query = query.get_all([category_id, status], index="owner_category_status")
        else:
            query = query.get_all(
                [category_id, "recycled"], index="owner_category_status"
            )
    elif status:
        query = query.get_all(status, index="status")
    else:
        query = query.get_all(r.args(["recycled", "deleting"]), index="status")
    count_query = {
        "desktops": r.row["desktops"].count(),
        "templates": r.row["templates"].count(),
        "storages": r.row["storages"].count(),
        "deployments": r.row["deployments"].count(),
        "categories": r.row["categories"].count(),
        "groups": r.row["groups"].count(),
        "users": r.row["users"].count(),
        "last": r.row["logs"][-1],
    }
    query = query.merge(count_query).without("logs", "tasks")
    with app.app_context():
        return list(query.run(db.conn))


@cached(cache=TTLCache(maxsize=50, ttl=10))
def get_user_amount(user_id):
    with app.app_context():
        return (
            r.table("recycle_bin")
            .get_all([user_id, "recycled"], index="owner_status")
            .count()
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=1, ttl=10))
def get_recicle_delete_time(owner_category_id=None):
    if owner_category_id is None:
        try:
            with app.app_context():
                return (
                    r.table("scheduler_jobs")
                    .get("admin.recycle_bin_delete_admin")["kwargs"][
                        "max_delete_period"
                    ]
                    .run(db.conn)
                )
        except:
            return "null"
    else:
        with app.app_context():
            try:
                results = (
                    r.table("scheduler_jobs")
                    .get(owner_category_id + ".recycle_bin_delete")["kwargs"][
                        "max_delete_period"
                    ]
                    .run(db.conn)
                )
            except:
                try:
                    with app.app_context():
                        results = (
                            r.table("scheduler_jobs")
                            .get("admin.recycle_bin_delete_admin")["kwargs"][
                                "max_delete_period"
                            ]
                            .run(db.conn)
                        )
                except:
                    results = "null"
        return results


@cached(cache=TTLCache(maxsize=1, ttl=30))
def get_old_entries_config():
    with app.app_context():
        try:
            return r.table("config")[0]["recycle_bin"]["old_entries"].run(db.conn)
        except r.ReqlNonExistenceError:
            return {"max_time": None, "action": None}


def check_older_than_old_entry_max_time(last):
    max_time_config = get_old_entries_config()["max_time"]
    if max_time_config is None:
        return False
    else:
        max_time_hours = int(max_time_config)
        return last < (datetime.now() - timedelta(hours=max_time_hours)).timestamp()


@cached(cache=TTLCache(maxsize=1, ttl=30))
def get_default_delete():
    with app.app_context():
        try:
            return r.table("config")[0]["recycle_bin"]["default_delete"].run(db.conn)
        except r.ReqlNonExistenceError:
            return False


@cached(cache=TTLCache(maxsize=1, ttl=30))
def get_delete_action():
    with app.app_context():
        try:
            return r.table("config")[0]["recycle_bin"]["delete_action"].run(db.conn)
        except r.ReqlNonExistenceError:
            return "delete"


def send_socket_user(kind, data, owner_id):
    socketio.emit(
        kind,
        data,
        namespace="/userspace",
        room=owner_id,
    )


def send_socket_admin(kind, data):
    socketio.emit(
        kind,
        data,
        namespace="/administrators",
        room="admins",
    )


def add_log(
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
    with app.app_context():
        r.table("recycle_bin").get(id).update({"logs": r.row["logs"].append(logs)}).run(
            db.conn
        )


class RecycleBin(object):
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
            self.agent_type = "user" if user_id != "isard-scheduler" else "system"
            self.status = "recycled"
            self.agent_id = user_id
            self.item_type = item_type
            self.agent_type = "user" if user_id else "system"
            if self.agent_type == "user":
                user = get_user_data(user_id)
                self.agent_name = user["user_name"]
                self.agent_category_id = user["category_id"]
                self.agent_category_name = user["category_name"]
                self.agent_group_id = user["group_id"]
                self.agent_group_name = user["group_name"]
                self.agent_role = user["role"]
            with app.app_context():
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
                    .run(db.conn)["changes"][0]["new_val"]["id"]
                )
            add_log(
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
            with app.app_context():
                data = r.table("recycle_bin").get(id).run(db.conn)
            if not data:
                raise Error("not_found", f"recycle_bin not found: {id}")
            for key, value in data.items():
                self.__dict__[key] = value

    def _add_item_name(self, name):
        self.item_name = name
        with app.app_context():
            r.table("recycle_bin").get(self.id).update({"item_name": name}).run(db.conn)

    def _add_owner(self, user_id):
        user = get_user_data(user_id)
        with app.app_context():
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
            ).run(db.conn)
        self.owner_id = user_id
        self.owner_name = user["user_name"]
        self.owner_category_id = user["category_id"]
        self.owner_category_name = user["category_name"]
        self.owner_group_id = user["group_id"]
        self.owner_group_name = user["group_name"]
        self.owner_role = user["role"]
        self.is_new = False
        send_socket_user("add_recycle_bin", get_count(self.id), self.owner_id)
        send_socket_admin("add_recycle_bin", get_count(self.id))

    def _update_agent(self, user_id=None):
        """
        Updates agent_name, agent_id, agent_role, agent_category, agent_category_name and agent_type=user. Call after doing an action

        :param user_id: ID of the user who makes the action. Leave None so agent_type is system
        :param user_id: str, None
        """

        if user_id and (user_id != "isard-scheduler"):
            user = get_user_data(user_id)
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
        with app.app_context():
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
            ).run(db.conn)

    def _add_task(self, task):
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"tasks": r.row["tasks"].append(task)}
            ).run(db.conn)

    def _update_size(self):
        size = 0
        for s in self.storages:
            size += s.get("qemu-img-info", {}).get("actual-size", 0)
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {
                    "size": r.row["size"] + size,
                }
            ).run(db.conn)

    def check_can_restore(self):
        for desktop in self.desktops:
            if not desktop.get("tag"):
                quotas.desktop_create(desktop["user"])

        for template in self.templates:
            quotas.template_create(template["user"])

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
            quotas.deployment_create(users, deployment["user"])

    def send_socket_user(self, kind, data):
        socketio.emit(
            kind,
            data,
            namespace="/userspace",
            room=self.owner_id,
        )

    def send_socket_admin(self, kind, data):
        socketio.emit(
            kind,
            data,
            namespace="/administrators",
            room="admins",
        )

    def restore(self):
        """
        Restore an entry including domains and storage. Call this function with RecycleBin object instanced with ID
        """
        if self.status in ["deleted", "restored"]:
            raise Error(
                "precondition_required",
                "Cannot restore entry with status " + str(self.status),
            )
        try:
            itemExists("users", self.owner_id)
        except:
            raise Error(
                "not_found",
                f"Can't restore entry. User "
                + str(self.owner_name)
                + " has been deleted.",
                description_code="user_not_found",
            )

        if self.item_type not in ["deployment", "user", "group", "category"]:
            self.check_can_restore()

        with app.app_context():
            r.table("users").insert(self.users).run(db.conn)
            r.table("groups").insert(self.groups).run(db.conn)
            r.table("categories").insert(self.categories).run(db.conn)

        storage_ids = [storage["id"] for storage in self.storages]
        try:
            with app.app_context():
                r.table("storage").get_all(*storage_ids).update(
                    {
                        "status": "ready",
                        "status_logs": r.row["status_logs"].append(
                            {"time": int(time.time()), "status": "ready"}
                        ),
                    }
                ).run(db.conn)
        except:
            raise Error("not found", "Invalid storage data")
        update_status(self.id, self.owner_id, "restored")
        add_log(
            "restored",
            self.id,
            self.agent_type,
            self.agent_id,
            self.agent_name,
            self.agent_category_id,
            self.agent_category_name,
            self.agent_role,
        )
        with app.app_context():
            r.table("domains").insert(self.desktops + self.templates).run(db.conn)
        with app.app_context():
            r.table("deployments").insert(self.deployments).run(db.conn)
        if self.categories:
            isard_user_storage_enable_categories(self.categories)
        elif self.groups:
            isard_user_storage_enable_groups(self.groups)
        elif self.users:
            isard_user_storage_enable_users(self.users)

    def delete_storage(self, user_id):
        """
        Permanently delete the storage disks associated with a recycle bin entry

        :param user_id: User ID of who is performing the action
        :type user_id: str
        :param move: True to move the disk file to deleted path instead of deleting it
        :type move: bool
        """
        if self.status in ["restored", "deleted"]:
            raise Error(
                error="precondition_required",
                description="Cannot delete entry with status " + str(self.status),
            )

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
            update_status(self.id, self.owner_id, "deleted")
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
                    with app.app_context():
                        storages_status = list(
                            r.table("storage")
                            .get_all(r.args([storage["id"] for storage in rb.storages]))
                            .pluck("status")["status"]
                            .run(db.conn)
                        )
                    log.debug(
                        "RecycleBin %s delete_storage: Got storages status in %s seconds",
                        rb.id,
                        time.time() - start,
                    )
                    if all(x == "deleted" for x in storages_status):
                        start = time.time()
                        update_status(rb.id, self.owner_id, "deleted")
                        log.debug(
                            "RecycleBin %s delete_storage: All storages status deleted. Updated status to deleted in %s seconds",
                            rb.id,
                            time.time() - start,
                        )
                    else:
                        start = time.time()
                        update_status(rb.id, self.owner_id, "deleting")
                        log.debug(
                            "RecycleBin %s delete_storage: Not all storages status deleted. Updated status to deleting in %s seconds",
                            rb.id,
                            time.time() - start,
                        )
                        start = time.time()
                        add_log(
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
                            update_status(rb.id, "deleted")
                            log.debug(
                                "RecycleBin %s delete_storage: No storages. Updated status to deleted in %s seconds",
                                rb.id,
                                time.time() - start,
                            )
                        for storage in rb.storages:
                            start = time.time()
                            exists = Storage.exists(storage["id"])
                            log.debug(
                                "RecycleBin %s delete_storage: Checked if storage %s exists or status is deleted in %s seconds",
                                rb.id,
                                storage["id"],
                                time.time() - start,
                            )
                            if not exists or storage["status"] == "deleted":
                                continue
                            start = time.time()
                            storage = Storage(storage["id"])
                            if storage.status != "recycled":
                                storage.status = "recycled"
                            move = get_delete_action() == "move"
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
            isard_user_storage_remove_categories(self.categories, groups)
            log.debug(
                "RecycleBin %s delete_storage: Removed categories in %s seconds",
                self.id,
                time.time() - start,
            )
        elif self.groups:
            start = time.time()
            isard_user_storage_remove_groups(self.groups)
            log.debug(
                "RecycleBin %s delete_storage: Removed groups in %s seconds",
                self.id,
                time.time() - start,
            )
        elif self.users:
            start = time.time()
            isard_user_storage_remove_users(self.users)
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
        with app.app_context():
            return list(
                r.table("recycle_bin")
                .get_all(r.args(templates), index=index)
                .filter(lambda rb: rb["status"] == "recycled")
                .filter(lambda rb: rb["id"].ne(self.id))
                .pluck({"id": True, "storages": ["id"]})
                .distinct()
                .run(db.conn)
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
    #         query = query.filter({"owner_id": user_id, "status": "recycled"})
    #     elif category_id:
    #         query = query.filter({"owner_category_id": category_id})

    #     with app.app_context():
    #         query = list(query.run(db.conn))

    #     # for storage in query
    #     # new key category in storage
    #     # category is category name of user_id in storage
    #     return query

    @classmethod
    def set_old_entries_max_time(cls, max_time):
        with app.app_context():
            r.table("config").update(
                {"recycle_bin": {"old_entries": {"max_time": max_time}}}
            ).run(db.conn)

    @classmethod
    def set_old_entries_action(cls, action):
        with app.app_context():
            if action == "none":
                r.table("config").replace(
                    r.row.without({"recycle_bin": "old_entries"})
                ).run(db.conn)
            else:
                r.table("config").update(
                    {"recycle_bin": {"old_entries": {"action": action}}}
                ).run(db.conn)

    @classmethod
    def delete_old_entries(cls, rcb_list):
        with app.app_context():
            results = (
                r.table("recycle_bin").get_all(r.args(rcb_list)).delete().run(db.conn)
            )

    # @classmethod
    # def archive_old_entries(cls, rcb_list):
    #     with app.app_context():
    #         results = (
    #             r.table("recycle_bin_archive")
    #             .insert(rcb_list, conflict="update")
    #             .run(db.conn)
    #         )
    #         if results["inserted"]:
    #             ids = [rcb["id"] for rcb in rcb_list]
    #             cls.delete_old_entries(ids)

    @classmethod
    def set_default_delete(cls, set_default):
        with app.app_context():
            r.table("config")[0].update(
                {"recycle_bin": {"default_delete": set_default}}
            ).run(db.conn)

    @classmethod
    def set_delete_action(cls, action):
        with app.app_context():
            r.table("config")[0].update({"recycle_bin": {"delete_action": action}}).run(
                db.conn
            )


class RecycleBinDomain(RecycleBin):
    def __init__(self, id=None, item_type="desktop", user_id=None):
        super().__init__(id, item_type=item_type, user_id=user_id)

    def add(self, domain_id):
        desktops_stop([domain_id], 5)
        # Move desktop to recycle_bin
        with app.app_context():
            domain = r.table("domains").get(domain_id).run(db.conn)
        self.add_domain(domain)
        if not self.owner_id:
            super()._add_owner(domain["user"])
        if not self.item_name:
            self._add_item_name(domain["name"])
        with app.app_context():
            r.table("domains").get(domain_id).delete().run(db.conn)
        return self._set_data(self.id)

    def add_domain(self, domain):
        if domain["kind"] == "desktop":
            with app.app_context():
                r.table("recycle_bin").get(self.id).update(
                    {"desktops": r.row["desktops"].append(domain)}
                ).run(db.conn)
            apib.delete_item_bookings("desktop", domain["id"])
        if domain["kind"] == "template":
            with app.app_context():
                r.table("recycle_bin").get(self.id).update(
                    {"templates": r.row["templates"].append(domain)}
                ).run(db.conn)
        # Move its disk to recycle_bin
        if not (
            domain["kind"] == "template" and domain.get("duplicate_parent_template")
        ):

            for disk in domain["create_dict"]["hardware"]["disks"]:
                if "storage_id" in disk:
                    with app.app_context():
                        storage = (
                            r.table("storage").get(disk["storage_id"]).run(db.conn)
                        )
                    if storage:
                        RecycleBinStorage(self.id).add(disk["storage_id"])

    def add_desktops(self, desktops):
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"desktops": r.row["desktops"].add(desktops)}
            ).run(db.conn)

        rcb_storage = RecycleBinStorage(id=self.id, user_id=self.agent_id)
        storages_ids = []
        for desktop in desktops:
            apib.delete_item_bookings("desktop", desktop["id"])

            for disk in desktop["create_dict"]["hardware"]["disks"]:
                if "storage_id" in disk:
                    storages_ids.append(disk["storage_id"])
        storages = []
        for i in range(0, len(storages_ids), 200):
            batch_ids = storages_ids[i : i + 200]
            with app.app_context():
                storages += r.table("storage").get_all(r.args(batch_ids)).run(db.conn)
            with app.app_context():
                r.table("storage").get_all(r.args(batch_ids)).update(
                    {
                        "status": "recycled",
                        "status_logs": r.row["status_logs"].append(
                            {"time": int(time.time()), "status": "recycled"}
                        ),
                    }
                ).run(db.conn)
        rcb_storage.add_storages(storages)


class RecycleBinDesktop(RecycleBinDomain):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="desktop", user_id=user_id)


class RecycleBinTemplate(RecycleBinDomain):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="template", user_id=user_id)

    def add(
        self,
        template_id=None,
    ):
        """
        Adds a recycle bin entry for templates.

        :param template_id: ID of the template to recycle. All derived templates and desktops will also be recycled
        :type template_id: str, None
        """

        if template_id:
            with app.app_context():
                template = r.table("domains").get(template_id).run(db.conn)
            self._add_item_name(template["name"])
            # Get template ids tree
            data = GetTemplateWithAllDerivatives(template_id, user_id=self.agent_id)
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
        with app.app_context():
            storage = r.table("storage").get(storage_id).run(db.conn)
        self.add_storage(storage)
        super()._add_owner(storage["user_id"])
        with app.app_context():
            r.table("storage").get(storage_id).update(
                {
                    "status": "recycled",
                    "status_logs": r.row["status_logs"].append(
                        {"time": int(time.time()), "status": "recycled"}
                    ),
                }
            ).run(db.conn)
        return self._set_data(self.id)

    def add_storage(self, storage):
        if storage:
            with app.app_context():
                r.table("recycle_bin").get(self.id).update(
                    {
                        "storages": r.row["storages"].append(storage),
                        "size": r.row["size"]
                        + storage.get("qemu-img-info", {}).get("actual-size", 0),
                    }
                ).run(db.conn)

    def add_storages(self, storages):
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"storages": r.row["storages"].add(storages)}
            ).run(db.conn)


class RecycleBinDeployment(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="deployment", user_id=user_id)

    def add(self, deployment_id):
        with app.app_context():
            deployment = r.table("deployments").get(deployment_id).run(db.conn)
        self.add_deployment(deployment)
        super()._add_owner(deployment["user"])
        self._add_item_name(deployment["name"])
        with app.app_context():
            r.table("deployments").get(deployment_id).delete().run(db.conn)
        return self._set_data(self.id)

    def add_deployment(self, deployment):
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"deployments": r.row["deployments"].append(deployment)}
            ).run(db.conn)
            desktops_ids = list(
                r.table("domains")
                .get_all(deployment["id"], index="tag")
                .pluck("id")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, 5)
        with app.app_context():
            # Move deployment desktops to recycle_bin
            desktops = list(
                r.table("domains").get_all(deployment["id"], index="tag").run(db.conn)
            )
        apib.delete_item_bookings("deployment", deployment["id"])
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(deployment["id"], index="tag")
                .delete()
                .run(db.conn)
            )

    def add_deployments(self, deployments):
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"deployments": r.row["deployments"].add(deployments)}
            ).run(db.conn)
        deployments_ids = [deployment["id"] for deployment in deployments]
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .pluck("id")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, 5)
        # Move deployment desktops to recycle_bin
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .run(db.conn)
            )
        for deployment in deployments:
            apib.delete_item_bookings("deployment", deployment["id"])
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(r.args(deployments_ids), index="tag")
                .delete()
                .run(db.conn)
            )


class RecycleBinBulk(RecycleBin):
    def __init__(self, id=None, item_type="bulk", user_id=None):
        super().__init__(id, item_type=item_type, user_id=user_id)

    def add(self, desktops_ids):
        super()._add_owner(self.agent_id)
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        desktops = []

        for i in range(0, len(desktops_ids), 200):
            batch_ids = desktops_ids[i : i + 200]
            desktops_stop(batch_ids, 5)
            # Move desktops to recycle_bin
            with app.app_context():
                desktops += list(
                    r.table("domains").get_all(r.args(batch_ids)).run(db.conn)
                )
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).delete().run(db.conn)
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
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        self.add_user(user, delete_user)
        super()._add_owner(user["id"])
        self._add_item_name(user["name"])
        if delete_user:
            with app.app_context():
                r.table("users").get(user_id).delete().run(db.conn)
        return self._set_data(self.id)

    def add_user(self, user, delete_user=True):
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", user["id"]], index="kind_user")
                .pluck("id")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, 5)
        # Delete desktops
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user["id"]], index="kind_user")
                .run(db.conn)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            r.table("domains").get_all(
                ["desktop", user["id"]], index="kind_user"
            ).delete().run(db.conn)
        # Delete templates
        with app.app_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", user["id"]], index="kind_user")["id"]
                .run(db.conn)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with app.app_context():
            r.table("domains").get_all(
                ["template", user["id"]], index="kind_user"
            ).delete().run(db.conn)
        # Delete deployments
        with app.app_context():
            deployments = list(
                r.table("deployments").get_all(user["id"], index="user").run(db.conn)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)
        with app.app_context():
            r.table("deployments").get_all(user["id"], index="user").delete().run(
                db.conn
            )
        if delete_user:
            with app.app_context():
                r.table("recycle_bin").get(self.id).update(
                    {
                        "users": r.row["users"].append(user),
                    }
                ).run(db.conn)
            isard_user_storage_disable_users([user])


class RecycleBinGroup(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="group", user_id=user_id)

    # TODO: When removing a group check if there's any dependant recycle bin entry
    def add(self, group_id):
        # Delete group
        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
        self.add_group(group)
        super()._add_owner(self.agent_id)
        self._add_item_name(group["name"])
        with app.app_context():
            r.table("groups").get(group_id).delete().run(db.conn)
        return self._set_data(self.id)

    def add_group(self, group):
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .pluck("id")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, 5)
        # Delete desktops
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", group["id"]], index="kind_group")
                .run(db.conn)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            r.table("domains").get_all(
                ["desktop", group["id"]], index="kind_group"
            ).delete().run(db.conn)
        # Delete templates
        with app.app_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", group["id"]], index="kind_group")["id"]
                .run(db.conn)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with app.app_context():
            r.table("domains").get_all(
                ["template", group["id"]], index="kind_group"
            ).delete().run(db.conn)
        # Delete deployments
        with app.app_context():
            users = list(
                r.table("users").get_all(group["id"], index="group").run(db.conn)
            )
        users_ids = [user["id"] for user in users]
        with app.app_context():
            deployments = list(
                r.table("deployments")
                .get_all(r.args(users_ids), index="user")
                .run(db.conn)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)
        with app.app_context():
            r.table("deployments").get_all(
                r.args(users_ids), index="user"
            ).delete().run(db.conn)
            r.table("recycle_bin").get(self.id).update(
                {
                    "users": r.row["users"].add(users),
                    "groups": r.row["groups"].append(group),
                }
            ).run(db.conn)
            r.table("users").get_all(group["id"], index="group").delete().run(db.conn)
        isard_user_storage_disable_groups([group])


class RecycleBinCategory(RecycleBin):
    def __init__(self, id=None, user_id=None):
        super().__init__(id, item_type="category", user_id=user_id)

    # TODO: When removing a group check if there's any dependant recycle bin entry
    def add(self, category_id):
        # Delete group
        with app.app_context():
            category = r.table("categories").get(category_id).run(db.conn)
        self.add_category(category)
        super()._add_owner(self.agent_id)
        self._add_item_name(category["name"])
        with app.app_context():
            r.table("categories").get(category_id).delete().run(db.conn)
        return self._set_data(self.id)

    def add_category(self, category):
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .pluck("id")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, 5)
        # Delete desktops
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", category["id"]], index="kind_category")
                .run(db.conn)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            r.table("domains").get_all(
                ["desktop", category["id"]], index="kind_category"
            ).delete().run(db.conn)
        # Delete templates
        with app.app_context():
            templates_ids = (
                r.table("domains")
                .get_all(["template", category["id"]], index="kind_category")["id"]
                .run(db.conn)
            )
        rcb_template = RecycleBinTemplate(id=self.id, user_id=self.agent_id)
        for template_id in templates_ids:
            rcb_template.add(template_id)
        with app.app_context():
            r.table("domains").get_all(
                ["template", category["id"]], index="kind_category"
            ).delete().run(db.conn)
        # Delete deployments
        with app.app_context():
            users = list(
                r.table("users").get_all(category["id"], index="category").run(db.conn)
            )
        users_ids = [user["id"] for user in users]
        with app.app_context():
            deployments = list(
                r.table("deployments")
                .get_all(r.args(users_ids), index="user")
                .run(db.conn)
            )
        rcb_deployments = RecycleBinDeployment(id=self.id, user_id=self.agent_id)
        rcb_deployments.add_deployments(deployments)
        with app.app_context():
            r.table("deployments").get_all(
                r.args(users_ids), index="user"
            ).delete().run(db.conn)
            groups = (
                r.table("groups")
                .get_all(category["id"], index="parent_category")
                .run(db.conn)
            )
            r.table("recycle_bin").get(self.id).update(
                {
                    "users": r.row["users"].add(users),
                    "groups": r.row["groups"].add(groups),
                    "categories": r.row["categories"].append(category),
                }
            ).run(db.conn)
            r.table("users").get_all(category["id"], index="category").delete().run(
                db.conn
            )
            r.table("groups").get_all(
                category["id"], index="parent_category"
            ).delete().run(db.conn)
        isard_user_storage_disable_categories([category])
