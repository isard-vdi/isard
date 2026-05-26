#
#   Copyright © 2025 Pau Abril Iranzo, Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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


import time
import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task
from rethinkdb import r


class StorageProcessed(RethinkSharedConnection):

    _rdb_table = "storage"

    @classmethod
    def get_status_counts(cls, category_id=None):
        """_From /api/libv2/api_storage.py get_status()_"""
        query = r.table("storage").pluck("status", "user_id")
        if category_id:
            query = (
                query.eq_join(
                    [r.row["user_id"], category_id],
                    r.table("users"),
                    index="user_category",
                )
                .pluck("left", {"right": {"category": True}})
                .zip()
            )
        query = (
            query.group("status")
            .count()
            .ungroup()
            .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
        )
        with cls._rdb_context():
            status = list(query.run(cls._rdb_connection))
        return status

    @classmethod
    def get_disks_ids_by_status(cls, status=None):
        """_From /api/libv2/api_storage.py get_disks_ids_by_status()_"""
        query = r.table("storage")
        if status:
            if status == "other":
                query = query.filter(
                    lambda disk: r.expr(["ready", "deleted"])
                    .contains(disk["status"])
                    .not_()
                )
            else:
                query = query.get_all(status, index="status")

        with cls._rdb_context():
            return list(query.pluck("id")["id"].run(cls._rdb_connection))

    @classmethod
    def get_storages(
        cls,
        user_id=None,
        status=None,
        pluck=None,
        category_id=None,
        categories=None,
    ):
        """_From /api/libv2/api_storage.py get_disks()_"""
        query = r.table("storage")
        if user_id:
            query = query.get_all(user_id, index="user_id")
            if status:
                query = query.filter({"status": status})
        elif status:
            query = query.get_all(status, index="status")

        if pluck:
            query = query.pluck(pluck)
        else:
            query = query.pluck(
                [
                    "id",
                    "type",
                    "status",
                    "directory_path",
                    "parent",
                    "user_id",
                    "status_logs",
                    "task",
                    "perms",
                    {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
                ]
            )
        if categories:
            query = query.filter(
                lambda disk: r.expr(categories).contains(
                    r.table("users").get(disk["user_id"].default(""))["category"]
                )
            )
        elif category_id:
            query = (
                query.eq_join(
                    [r.row["user_id"].default(""), category_id],
                    r.table("users"),
                    index="user_category",
                )
                .pluck("left", {"right": {"category": True}})
                .zip()
            )
        query = query.merge(
            lambda disk: {
                "user_name": r.table("users")
                .get(disk["user_id"].default(""))
                .default({"name": "[DELETED] " + disk["user_id"].default("")})["name"],
                "category": r.table("users")
                .get(disk["user_id"].default(""))
                .default({"category": "[DELETED]"})["category"],
                "domains": r.table("domains")
                .get_all(disk["id"], index="storage_ids")
                .count(),
                "last": r.branch(
                    disk["status_logs"].default([None]).count().eq(0),
                    None,
                    disk["status_logs"].default([None])[-1],
                ),
            }
        ).without("status_logs")

        with cls._rdb_context():
            storages = list(query.run(cls._rdb_connection))

        if status == "maintenance":
            for storage in storages:
                if storage.get("task") and Task.exists(storage["task"]):
                    storage["progress"] = Task(storage.get("task")).to_dict()[
                        "progress"
                    ]

        return storages

    @classmethod
    def check_storage(cls, payload, storage_id):
        """_From api/views/StorageView get_storage()_

        Check storage existence.

        :param storage_id: Storage ID
        :type storage_id: str
        """
        if not Storage.exists(storage_id):
            raise Error(
                error="not_found", description=f"Storage {storage_id} not found"
            )

        storage = Storage(storage_id)
        if payload["role_id"] == "admin":
            return storage

        if storage.user_id is None:
            raise Error(
                "not_found",
                f"Storage {storage_id} missing user_id",
                "not_found",
            )

        if storage.user_id == payload["user_id"]:
            return storage

        if payload["role_id"] == "manager":
            with cls._rdb_context():
                storage_category_id = (
                    r.table("users")
                    .get(storage.user_id)
                    .pluck("category")["category"]
                    .run(cls._rdb_connection)
                )
            if storage_category_id == payload["category_id"]:
                return storage

        owns_domains = [
            Helpers.owns_domain_id(payload, domain.id) for domain in storage.domains
        ]
        if any(owns_domains):
            return storage

        raise Error(
            "forbidden",
            "Not enough access rights for this user_id " + payload["user_id"],
            "forbidden",
        )

    @classmethod
    def get_user_ready_disks(cls, user_id):
        """_From /api/libv2/api_storage.py get_user_ready_disks()_"""
        query = (
            r.table("storage")
            .get_all([user_id, "ready"], index="user_status")
            .pluck(
                [
                    "id",
                    "user_id",
                    "user_name",
                    {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
                    "status_logs",
                ],
            )
            .merge(
                lambda disk: {
                    "user_name": r.table("users")
                    .get(disk["user_id"])
                    .default({"name": "[DELETED] " + disk["user_id"]})["name"],
                    "category": r.table("users")
                    .get(disk["user_id"])
                    .default({"category": "[DELETED]"})["category"],
                    "domains": r.table("domains")
                    .get_all(disk["id"], index="storage_ids")
                    .filter({"user": user_id})
                    .pluck("id", "name", "status")
                    .coerce_to("array"),
                }
            )
        )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_storage_domains(cls, storage_id):
        """_From /api/libv2/api_storage.py get_storage_domains()_"""
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(storage_id, index="storage_ids")
                .pluck("id", "kind", "name")
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_storage(cls, storage_id):
        """_From /api/libv2/api_storage.py get_storage()_"""
        with cls._rdb_context():
            disk = (
                r.table("storage")
                .get(storage_id)
                .merge(
                    lambda stg: {
                        "category": r.table("users").get(stg["user_id"])["category"]
                    }
                )
                .run(cls._rdb_connection)
            )
        return cls.parse_disks([disk])[0]

    @classmethod
    def get_storage_info(cls, storage_id):
        """_From /api/libv2/api_storage.py get_storage_info()_"""
        with cls._rdb_context():
            disk = r.table("storage").get(storage_id).run(cls._rdb_connection)
        if disk:
            domains = Storage(storage_id).domains
            disk["domains"] = [
                {"name": d.name, "id": d.id, "kind": d.kind} for d in domains
            ]
        return cls.parse_disks([disk])[0]

    @classmethod
    def parse_disks(cls, disks):
        """_From /api/libv2/api_storage.py parse_disks()_"""
        parsed_disks = []
        for disk in disks:
            if disk.get("qemu-img-info"):
                disk["actual_size"] = disk["qemu-img-info"]["actual-size"]
                disk["virtual_size"] = disk["qemu-img-info"]["virtual-size"]
                disk.pop("qemu-img-info")
            if disk.get("status_logs"):
                disk["last"] = disk["status_logs"][-1]["time"]
                disk.pop("status_logs")
            parsed_disks.append(disk)
        return parsed_disks

    @classmethod
    def get_domains_delete_pending(cls, category_id=None):
        """_From /api/libv2/api_storage.py get_domains_delete_pending()_"""
        query = r.table("storage").get_all("delete_pending", index="status")
        if category_id:
            query = query.filter({"last_domain_attached": {"category": category_id}})
        query = query.pluck(
            "id",
            "type",
            "status",
            "directory_path",
            "parent",
            "user_id",
            "status_logs",
            "last_domain_attached",
            {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
        )
        query = query.merge(
            lambda disk: {
                "user_name": r.table("users").get(disk["user_id"])["name"],
                "category_name": r.table("categories").get(
                    r.table("users").get(disk["user_id"])["category"]
                )["name"],
            }
        )
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_storage_derivatives(cls, storage_id):
        """_From /api/libv2/api_storage.py get_storage_derivatives()_"""
        total = []
        domains = Storage(storage_id).domains
        for domain in domains:
            total.append(domain.id)
            if domain.kind == "template":
                with cls._rdb_context():
                    derivative_list = list(
                        r.table("domains")
                        .get_all(domain.id, index="parents")
                        .distinct()
                        .map(
                            lambda doc: doc.merge(
                                {
                                    "storage": doc["create_dict"]["hardware"]["disks"][
                                        0
                                    ]["storage_id"]
                                }
                            )
                        )
                        .pluck("id", "storage", "status")
                        .run(cls._rdb_connection)
                    )
                for derivative in derivative_list:
                    total.append(derivative["id"])
                    d = cls.get_storage_derivatives(derivative["storage"])
                    if d:
                        total.extend(d)

        return list(set(total))

    @classmethod
    def get_storages_with_uuid(cls, category_id=None, status=None):
        """_From /api/libv2/api_storage.py get_storages_with_uuid()_"""
        query = r.table("storage")

        if category_id:
            query = (
                query.eq_join(
                    [r.row["user_id"], category_id],
                    r.table("users"),
                    index="user_category",
                )
                .pluck("left", {"right": {"category": True}})
                .zip()
            )

        query = (
            query.pluck("id", "storages_with_uuid")
            .merge(
                lambda storage: r.branch(
                    storage.has_fields("storages_with_uuid"),
                    storage["storages_with_uuid"].map(
                        lambda doc: doc.merge({"id": storage["id"]})
                    ),
                    [],
                )
            )
            .reduce(lambda acc, arr: acc.union(arr))
            .default([])
        )

        if status:
            query = query.filter({"status": status})

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_storages_with_uuid_status(cls, category_id=None):
        """_From /api/libv2/api_storage.py get_storages_with_uuid_status()_"""
        query = r.table("storage")

        if category_id:
            query = (
                query.eq_join(
                    [r.row["user_id"], category_id],
                    r.table("users"),
                    index="user_category",
                )
                .pluck("left", {"right": {"category": True}})
                .zip()
            )

        query = (
            query.pluck("id", "storages_with_uuid")
            .merge(
                lambda storage: r.branch(
                    storage.has_fields("storages_with_uuid"),
                    storage["storages_with_uuid"].map(
                        lambda doc: doc.merge({"id": storage["id"]})
                    ),
                    [],
                )
            )
            .reduce(lambda acc, arr: acc.union(arr))
            .default([])
        )

        query = (
            query.group("status")
            .count()
            .ungroup()
            .map(lambda doc: {"status": doc["group"], "count": doc["reduction"]})
        )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_storages_by_role(cls, role):
        """_From /api/libv2/api_storage.py get_storages_by_role()_

        Get all storages with a specific role, ordered by the latest status_logs entry.

        :param role: The role to filter storages by.
        :type role: str
        :return: List of storages with the specified role, ordered by the latest status_logs entry.
        :rtype: list
        """

        with cls._rdb_context():
            return list(
                r.table("users")
                .get_all(role, index="role")
                .eq_join("id", r.table("storage"), index="user_id")
                .map(lambda doc: doc["right"])
                .merge(
                    lambda storage: {
                        "latest_status_time": storage["status_logs"][-1]["time"],
                        "qemu-img-info": {
                            "full-backing-filename": storage["qemu-img-info"]
                            .default({})
                            .get_field("full-backing-filename")
                            .default(None),
                            "actual-size": storage["qemu-img-info"]
                            .default({})
                            .get_field("actual-size")
                            .default(None),
                        },
                    }
                )
                .merge(
                    lambda storage: {
                        "kind": r.table("domains")
                        .get_all(storage["id"], index="storage_ids")
                        .pluck("kind")
                        .coerce_to("array")
                        .map(lambda domain: domain["kind"])
                        .default([]),
                    }
                )
                .order_by(r.desc("latest_status_time"))
                .pluck(
                    "id",
                    "directory_path",
                    "type",
                    "kind",
                    "status",
                    {
                        "qemu-img-info": {
                            "full-backing-filename": True,
                            "actual-size": True,
                        }
                    },
                    "latest_status_time",
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_storage_actual_size(cls, storage_id):
        with cls._rdb_context():
            return (
                r.table(cls._rdb_table)
                .get(storage_id)
                .pluck("qemu-img-info")
                .default({})
                .get_field("qemu-img-info")
                .default({})
                .get_field("actual-size")
                .default(0)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_storage_row(cls, storage_id: str) -> dict | None:
        """Return the raw ``storage`` row by id (or ``None`` if missing).

        Bypasses the ``Storage`` model wrapper, which can't be cast to
        ``dict()`` directly because ``RethinkCustomBase.__getattr__``
        returns ``None`` for unknown attributes — calling the builtin
        ``dict()`` then dispatches to ``None()`` and dies. Endpoints
        that need the wire-shape row use this helper instead.
        """
        with cls._rdb_context():
            return r.table(cls._rdb_table).get(storage_id).run(cls._rdb_connection)

    @classmethod
    def batch_stop_desktops_by_kind_ids(
        cls,
        desktop_ids: list[str],
        update_data: dict,
        current_status: str,
        batch_size: int = 20,
    ) -> None:
        """Update ``status`` on every desktop in ``desktop_ids`` whose
        current row state is ``current_status``.

        Backs the storage-action "stop these desktops" path: the rows
        live in ``domains`` keyed by ``kind_ids`` (``[kind, id]``).
        ``update_data`` is the partial update applied to matched rows
        (typically ``{"status": new_status, "accessed": <ts>}``).

        Batched via ``batch_size`` because ``get_all`` with hundreds of
        keys produces a single large rdb cursor; chunking keeps memory
        bounded on big bulk-stop calls. Caller decides whether to sleep
        between batches.
        """
        for i in range(0, len(desktop_ids), batch_size):
            batch_ids = desktop_ids[i : i + batch_size]
            keys = [["desktop", d_id] for d_id in batch_ids]
            with cls._rdb_context():
                r.table("domains").get_all(*keys, index="kind_ids").filter(
                    {"status": current_status}
                ).update(update_data).run(cls._rdb_connection)
