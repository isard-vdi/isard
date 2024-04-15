from datetime import datetime, timedelta

from rethinkdb import RethinkDB

from api import app

from ..views.decorators import itemExists, ownsStorageId
from .api_storage import _add_storage_log

r = RethinkDB()
import time

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
from .helpers import GetAllTemplateDerivates, desktops_stop

quotas = Quotas()

apib = Bookings()

db = RDB(app)
db.init_app(app)


def get_status(category_id=None):
    with app.app_context():
        query = r.table("recycle_bin")
        if category_id:
            query = query.get_all(category_id, index="owner_category")
        query = (
            query.group("status")
            .count()
            .ungroup()
            .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
        )
        status = list(query.run(db.conn))
    return status


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
        category = (
            r.table("categories")
            .get(user["category"])
            .pluck("name", "id")
            .default({"name": "[Deleted]", "id": "[Deleted]"})
            .run(db.conn)
        )
        group = (
            r.table("groups")
            .get(user["group"])
            .pluck("name", "id")
            .default({"name": "[Deleted]", "id": "[Deleted]"})
            .run(db.conn)
        )
    return {
        "user_id": user["id"],
        "user_name": user["name"],
        "category_name": category["name"],
        "category_id": category["id"],
        "group_name": group["name"],
        "group_id": group["id"],
        "role": user["role"],
    }


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
                with app.app_context():
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
            self._add_log("recycled")

        else:
            with app.app_context():
                data = r.table("recycle_bin").get(id).run(db.conn)
            if not data:
                raise Error("not_found", "recycle_bin not found")
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
        self.send_socket_user("add_recycle_bin", self.get_count())
        self.send_socket_admin("add_recycle_bin", self.get_count())

    def _add_log(self, status):
        """
        Add a log entry for a status change with agent

        :param status: new status
        :type status: str
        """
        logs = {
            "time": int(time.time()),
            "action": status,
            "agent_type": self.agent_type,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_category_id": self.agent_category_id,
            "agent_category_name": self.agent_category_name,
            "agent_role": self.agent_role,
        }
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"logs": r.row["logs"].append(logs)}
            ).run(db.conn)
        # if self.logs_inserted:
        #     return
        # if status not in ["recycled", "restored", "deleted"]:
        #     raise Error("bad_request", "action not allowed")
        # if RecycleBin.status == status:
        #     raise Error("bad_request", "action not allowed as is the current status")
        # if not RecycleBin.status:
        #     if action != "recycled":
        #         raise Error("bad_request", "initial only allowed action is 'recycled'")
        #     RecycleBin.status = "recycled"
        # with app.app_context():
        #     r.table("recycle_bin").get(RecycleBin.id).update(
        #         {
        #             "logs": r.row["logs"].append(
        #                 {
        #                     "time": time.time(),
        #                     "action": action,
        #                     "agent_type": RecycleBin.agent_type,
        #                     "agent_id": RecycleBin.agent_id,
        #                     "agent_name": RecycleBin.agent_name,
        #                 }
        #             )
        #         }
        #     ).run(db.conn)

    def _update_agent(self, user_id=None):
        """
        Updates agent_name, agent_id, agent_role, agent_category, agent_category_name and agent_type=user. Call after doing an action

        :param user_id: ID of the user who makes the action. Leave None so agent_type is system
        :param user_id: str, None
        """

        if user_id and (user_id != "isard-scheduler"):
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("name", "category", "role")
                    .run(db.conn)
                )
                self.agent_category_name = (
                    r.table("categories").get(user["category"])["name"].run(db.conn)
                )
            self.agent_id = user_id
            self.agent_name = user["name"]
            self.agent_category_id = user["category"]
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
        self.tasks.append(task)
        with app.app_context():
            r.table("recycle_bin").get(self.id).update(
                {"tasks": r.row["tasks"].append(task)}
            ).run(db.conn)

    def _update_status(self, status):
        self.status = status
        with app.app_context():
            r.table("recycle_bin").get(self.id).update({"status": status}).run(db.conn)

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
            quotas.desktop_create(desktop["user"])

        for template in self.templates:
            quotas.template_create(template["user"])

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
        if self.item_type not in ["deployment", "user", "group", "category"]:
            self.check_can_restore()
        if self.status in ["deleted", "restored"]:
            raise Error(
                "precondition_required",
                "Cannot restore entry with status " + str(self.status),
            )
        r.table("users").insert(self.users).run(db.conn)
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
        r.table("groups").insert(self.groups).run(db.conn)
        r.table("categories").insert(self.categories).run(db.conn)
        storage_ids = [storage["id"] for storage in self.storages]
        with app.app_context():
            try:
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
            self._update_status("restored")
            self._add_log("restored")
            r.table("domains").insert(self.desktops + self.templates).run(db.conn)
            r.table("deployments").insert(self.deployments).run(db.conn)
        if self.categories:
            isard_user_storage_enable_categories(self.categories)
        elif self.groups:
            isard_user_storage_enable_groups(self.groups)
        elif self.users:
            isard_user_storage_enable_users(self.users)
        self.send_socket_user(
            "update_recycle_bin", {"id": self.id, "status": "restored"}
        )
        self.send_socket_admin(
            "update_recycle_bin", {"id": self.id, "status": "restored"}
        )

    def delete_storage(self, user_id):
        """
        Permanently delete the storage disks associated with a recycle bin entry

        :param user_id: User ID of who is performing the action
        :type user_id: str
        :param move: True to move the disk file to deleted path instead of deleting it
        :type move: bool
        """

        if self.categories:
            groups = [group["id"] for group in self.groups]
            isard_user_storage_remove_categories(self.categories, groups)
        elif self.groups:
            isard_user_storage_remove_groups(self.groups)
        elif self.users:
            isard_user_storage_remove_users(self.users)

        tasks = []
        if self.status in ["restored", "deleted"]:
            raise Error(
                error="precondition_required",
                description="Cannot delete entry with status " + str(self.status),
            )
        self._update_agent(user_id)
        self.deleteTemplatesDependencies()

        if not self.storages:
            self._update_status("deleted")
            self.send_socket_user(
                "delete_recycle_bin", {"id": self.id, "status": "deleted"}
            )
            self.send_socket_admin(
                "update_recycle_bin", {"id": self.id, "status": "deleted"}
            )
        else:
            with app.app_context():
                storages_status = (
                    r.table("storage")
                    .get_all(r.args([storage["id"] for storage in self.storages]))
                    .pluck("status")["status"]
                    .run(db.conn)
                )
            if all(x == "deleted" for x in storages_status):
                self._update_status("deleted")
                self.send_socket_user(
                    "delete_recycle_bin", {"id": self.id, "status": "deleted"}
                )
                self.send_socket_admin(
                    "update_recycle_bin", {"id": self.id, "status": "deleted"}
                )
            else:
                self._update_status("deleting")
                self._add_log("deleting")
                self.send_socket_user(
                    "update_recycle_bin", {"id": self.id, "status": "deleting"}
                )
                self.send_socket_admin(
                    "update_recycle_bin", {"id": self.id, "status": "deleting"}
                )
                for storage in self.storages:
                    if not Storage.exists(storage["id"]):
                        raise Error(
                            error="not_found",
                            description="Storage with id "
                            + storage["id"]
                            + "not found",
                        )
                    storage = Storage(storage["id"])
                    if storage.status == "deleted":
                        continue
                    if storage.status not in [
                        "ready",
                        "recycled",
                        "non-existing",
                        "orphan",
                    ]:
                        raise Error(
                            error="precondition_required",
                            description="Storage with id "
                            + storage.id
                            + " not ready. Status: "
                            + storage.status,
                        )
                    move = self.get_delete_action() == "move"
                    task_name = "move_delete" if move else "delete"
                    task = Task(
                        user_id=self.owner_id,
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
                                                "deleted": {"storage": [storage.id]},
                                            },
                                            "failed": {
                                                "recycled": {"storage": [storage.id]},
                                            },
                                            "canceled": {
                                                "recycled": {"storage": [storage.id]},
                                            },
                                        },
                                    },
                                },
                                "dependents": [
                                    {
                                        "queue": "core",
                                        "task": "recycle_bin_update",
                                        "job_kwargs": {
                                            "kwargs": {"recycle_bin_id": self.id}
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
                    self._add_task(
                        {
                            "id": task.id,
                            "item_id": storage.id,
                            "item_type": "storage",
                            "status": task.status,
                        }
                    )
                    tasks.append(
                        {"id": task.id, "storage_id": storage.id, "status": task.status}
                    )
        return tasks

    def deleteTemplatesDependencies(self):
        for template in self.templates:
            with app.app_context():
                dependencies = list(
                    r.table("recycle_bin")
                    .get_all(template["id"], index="parents")
                    .filter(
                        lambda rb: r.expr(["recycled", "deleting"]).contains(
                            rb["status"]
                        )
                    )
                    .filter(lambda rb: rb["id"].ne(self.id))
                    .pluck("id")["id"]
                    .run(db.conn)
                )
            for dependency in dependencies:
                RecycleBin(dependency).delete_storage(self.owner_id)

    def get_count(self):
        with app.app_context():
            return (
                r.table("recycle_bin")
                .get(self.id)
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

    @classmethod
    def get_all(cls, category_id=None, user_id=None):
        """
        Get all recycle bin entries.

        :return: Recycle bin entries
        :rtype: list
        """
        query = r.table("recycle_bin")
        if user_id:
            query = query.filter({"owner_id": user_id, "status": "recycled"})
        elif category_id:
            query = query.filter({"owner_category_id": category_id})

        with app.app_context():
            query = list(query.run(db.conn))

        # for storage in query
        # new key category in storage
        # category is category name of user_id in storage
        return query

    @classmethod
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
        query = r.table("recycle_bin").get(recycle_bin_id)

        with app.app_context():
            result = query.run(db.conn)

        if all_data:
            for domain in result["desktops"] + result["templates"]:
                user = r.table("users").get(domain["user"])
                with app.app_context():
                    category = (
                        r.table("categories")
                        .get(domain["category"])
                        .default({"name": "[Deleted]"})["name"]
                        .run(db.conn)
                    )
                    group = (
                        r.table("groups")
                        .get(domain["group"])
                        .default({"name": "[Deleted]"})["name"]
                        .run(db.conn)
                    )
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
                user = (
                    r.table("users")
                    .get(deployment["user"])
                    .default({"username": "[Deleted]"})
                )
                with app.app_context():
                    category = (
                        r.table("categories")
                        .get(user["category"])
                        .default({"name": "[Deleted user]"})["name"]
                        .run(db.conn)
                    )
                    group = (
                        r.table("groups")
                        .get(user["group"])
                        .default({"name": "[Deleted user]"})["name"]
                        .run(db.conn)
                    )
                    deployment["user"] = user["username"].run(db.conn)
                    deployment["category"] = category
                    deployment["group"] = group

            with app.app_context():
                for user in result["users"]:
                    try:
                        user["category"] = (
                            r.table("categories")
                            .get(user["category"])["name"]
                            .run(db.conn)
                        )
                    except:
                        user["category"] = "[DELETED]"

                    try:
                        user["group"] = (
                            r.table("groups").get(user["group"])["name"].run(db.conn)
                        )
                    except:
                        user["group"] = "[DELETED]"

        return result

    @classmethod
    def get_user_recycle_bin_ids(cls, user_id, status):
        """
        Get all the users recycle_bins ids

        :param user_id: User ID
        :type user_id: str
        :return: IDs of the user recycle bins
        :rtype: array
        """
        return list(
            r.table("recycle_bin")
            .get_all([user_id, status], index="owner_status")
            .filter({"agent_id": user_id})["id"]
            .run(db.conn)
        )

    @classmethod
    def get_recycle_bin_by_period(cls, max_delete_period, category=None):
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

    def get_item_count(user_id=None, category_id=None, status=None):
        query = r.table("recycle_bin")
        if user_id:
            query = query.get_all([user_id, "recycled"], index="owner_status")
        elif category_id:
            if status:
                query = query.get_all(
                    [category_id, status], index="owner_category_status"
                )
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

    def get_user_amount(user_id):
        return (
            r.table("recycle_bin")
            .get_all([user_id, "recycled"], index="owner_status")
            .count()
            .run(db.conn)
        )

    @classmethod
    def update_task_status(cls, task):
        # Update task status
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

        # If the all of the tasks are finished update the recycle bin status to deleted
        with app.app_context():
            recycle_bin = (
                r.table("recycle_bin").get(task["recycle_bin_id"]).run(db.conn)
            )
        finished_tasks = list(
            filter(lambda t: (t["status"] == "finished"), recycle_bin.get("tasks", []))
        )
        if len(finished_tasks) == len(recycle_bin.get("storages", [])):
            r.table("recycle_bin").get(task["recycle_bin_id"]).update(
                {"status": "deleted"}
            ).run(db.conn)
            rb = RecycleBin(task["recycle_bin_id"])
            rb._add_log("deleted")
            rb.send_socket_user(
                "update_recycle_bin", {"id": rb.id, "status": "deleted"}
            )
            rb.send_socket_admin(
                "update_recycle_bin", {"id": rb.id, "status": "deleted"}
            )

    def get_delete_time(self):
        if not self.owner_category_id:
            try:
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
                        .get(self.owner_category_id + ".recycle_bin_delete")["kwargs"][
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

    @classmethod
    def set_default_delete(cls, set_default):
        with app.app_context():
            r.table("config")[0].update(
                {"recycle_bin": {"default_delete": set_default}}
            ).run(db.conn)

    @classmethod
    def get_default_delete(cls):
        with app.app_context():
            try:
                return r.table("config")[0]["recycle_bin"]["default_delete"].run(
                    db.conn
                )
            except r.ReqlNonExistenceError:
                return False

    @classmethod
    def set_delete_action(cls, action):
        with app.app_context():
            r.table("config")[0].update({"recycle_bin": {"delete_action": action}}).run(
                db.conn
            )

    @classmethod
    def get_delete_action(cls):
        with app.app_context():
            try:
                return r.table("config")[0]["recycle_bin"]["delete_action"].run(db.conn)
            except r.ReqlNonExistenceError:
                return "delete"


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
            with app.app_context():
                for disk in domain["create_dict"]["hardware"]["disks"]:
                    if "storage_id" in disk:
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
        storages = r.table("storage").get_all(r.args(storages_ids)).run(db.conn)
        rcb_storage.add_storages(storages)
        with app.app_context():
            r.table("storage").get_all(r.args(storages_ids)).update(
                {
                    "status": "recycled",
                    "status_logs": r.row["status_logs"].append(
                        {"time": int(time.time()), "status": "recycled"}
                    ),
                }
            ).run(db.conn)


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
            data = GetAllTemplateDerivates(template_id, user_id=self.agent_id)
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
            with app.app_context():
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
            # Move deployment desktops to recycle_bin
            desktops = list(
                r.table("domains").get_all(deployment["id"], index="tag").run(db.conn)
            )
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
        desktops_ids = list(
            r.table("domains")
            .get_all(r.args(desktops_ids))
            .pluck("id")["id"]
            .run(db.conn)
        )
        desktops_stop(desktops_ids, 5)
        # Move desktops to recycle_bin
        with app.app_context():
            desktops = list(
                r.table("domains").get_all(r.args(desktops_ids)).run(db.conn)
            )
        rcb_desktop = RecycleBinDesktop(id=self.id, user_id=self.agent_id)
        rcb_desktop.add_desktops(desktops)
        with app.app_context():
            desktops = (
                r.table("domains").get_all(r.args(desktops_ids)).delete().run(db.conn)
            )
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
