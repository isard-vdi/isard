#
#   Copyright © 2025 Pau Abril Iranzo
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
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task
from rethinkdb import r


class StoragePoolsProcessed(RethinkSharedConnection):

    _rdb_table = "storage_pool"

    @staticmethod
    def _check_with_validate_weight(data):
        """_From /api/libv2/api_storage.py \_check_with_validate_weight()_"""
        for key in data:
            if len(data[key]):
                total = sum(item["weight"] for item in data[key])
                if total != 100:
                    raise Error("bad_request", "Same type's weight sum must be 100")

    @staticmethod
    def _check_duplicated_paths(data):
        """_From /api/libv2/api_storage.py \_check_duplicated_paths()_"""
        seen_paths = set()
        for key in data:
            for item in data[key]:
                path = item["path"]
                if path in seen_paths:
                    raise Error(
                        "bad_request", "Paths of the same pool must have a unique name"
                    )
                seen_paths.add(path)

    @classmethod
    def remove_common_categories_from_other_pools(cls, categories):
        """_From /api/libv2/api_storage.py remove_common_categories_from_other_pools()_

        Remove categories from other storage pools so they can be added to another pool

        :param categories: List of category ids
        :type categories: list
        """
        if len(categories):
            with cls._rdb_context():
                existing_pools = list(
                    r.table("storage_pool")
                    .pluck("categories", "id")
                    .run(cls._rdb_connection)
                )
            for pool in existing_pools:
                common_categories = set(pool["categories"]).intersection(
                    set(categories)
                )
                if common_categories:
                    with cls._rdb_context():
                        r.table("storage_pool").get(pool["id"]).update(
                            {
                                "categories": r.row["categories"].difference(
                                    list(common_categories)
                                )
                            }
                        ).run(cls._rdb_connection)

    @classmethod
    def add_storage_pool(cls, data):
        """_From /api/libv2/api_storage.py add_storage_pool()_"""
        if data.get("paths"):
            cls._check_with_validate_weight(data["paths"])
            cls._check_duplicated_paths(data["paths"])
        if data.get("enabled") is False:
            data["enabled_virt"] = False
        else:
            data["enabled_virt"] = True
        cls.remove_common_categories_from_other_pools(data["categories"])
        with cls._rdb_context():
            r.table("storage_pool").insert(data).run(cls._rdb_connection)

    @classmethod
    def get_storage_pools(cls):
        """_From /api/libv2/api_storage.py get_storage_pools()_"""
        with cls._rdb_context():
            return list(
                r.table("storage_pool")
                .merge(
                    lambda pool: {
                        "categories_names": r.branch(
                            pool["categories"].is_empty(),
                            [],
                            r.table("categories")
                            .get_all(r.args(pool["categories"]))
                            .pluck("name", "id")
                            .coerce_to("array"),
                        ),
                        "storages": r.table("hypervisors")
                        .filter(
                            lambda hyper: hyper["status"] == "Online"
                            and hyper["enabled"] == True
                            and hyper["storage_pools"].contains(pool["id"])
                        )
                        .count(),
                        "hypers": r.table("hypervisors")
                        .filter(
                            lambda hyper: hyper["status"] == "Online"
                            and hyper["enabled"] == True
                            and hyper["enabled_virt_pools"].contains(pool["id"])
                        )
                        .count(),
                        "is_default": pool["id"].eq(DEFAULT_STORAGE_POOL_ID),
                    }
                )
                .run(cls._rdb_connection)
            )

    @staticmethod
    def _check_default_paths(cls, paths):
        """_From /api/libv2/api_storage.py \_check_default_paths()_"""
        if not (
            any(obj.get("path") == "groups" for obj in paths["desktop"])
            and any(obj.get("path") == "media" for obj in paths["media"])
            and any(obj.get("path") == "templates" for obj in paths["template"])
            and any(obj.get("path") == "volatile" for obj in paths["volatile"])
        ):
            raise Error(
                "bad_request",
                "Default pool must have at least one empty path per type",
            )

    @classmethod
    def update_storage_pool(cls, storage_pool_id, data):
        """_From /api/libv2/api_storage.py update_storage_pool()_"""
        if data.get("paths"):
            cls._check_duplicated_paths(data["paths"])
            cls._check_with_validate_weight(data["paths"])
        if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
            if "enabled" in data:
                raise Error("bad_request", "Default pool can't be disabled")
            for key in ["name", "description", "mountpoint", "categories"]:
                if key in data:
                    data.pop(key)
            if "paths" in data:
                cls._check_default_paths(data["paths"])

        # If the pool is disabled, the virt pool must be disabled too
        if data.get("enabled") is not None:
            data["enabled_virt"] = data["enabled"]
        elif data.get("enabled_virt") and not StoragePool.get(storage_pool_id).get(
            "enabled"
        ):
            raise Error(
                "bad_request",
                "The virtual pool cannot be enabled if the storage pool is disabled",
            )
        if "categories" in data:
            cls.remove_common_categories_from_other_pools(data["categories"])
        with cls._rdb_context():
            r.table("storage_pool").get(storage_pool_id).update(data).run(
                cls._rdb_context
            )

    @classmethod
    def delete_storage_pool(cls, storage_pool_id):
        """_From /api/libv2/api_storage.py delete_storage_pool()_"""
        if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
            raise Error("bad_request", "Default pool can't be removed")
        with cls._rdb_context():
            r.table("storage_pool").get(storage_pool_id).delete().run(cls._rdb_context)
        with cls._rdb_context():
            r.table("hypervisors").update(
                lambda hyper: {
                    "storage_pools": hyper["storage_pools"].filter(
                        lambda pool: pool != storage_pool_id
                    ),
                    "enabled_storage_pools": hyper["enabled_storage_pools"].filter(
                        lambda pool: pool != storage_pool_id
                    ),
                    "virt_pools": hyper["virt_pools"].filter(
                        lambda pool: pool != storage_pool_id
                    ),
                    "enabled_virt_pools": hyper["enabled_virt_pools"].filter(
                        lambda pool: pool != storage_pool_id
                    ),
                }
            ).run(cls._rdb_context)

    @classmethod
    def remove_category_from_storage_pool(cls, category_id):
        """_From /api/libv2/api_storage.py remove_category_from_storage_pool()_"""
        with cls._rdb_context():
            r.table(cls._rdb_table).filter(
                lambda pool: pool["categories"].contains(category_id)
            ).update(
                lambda pool: pool["categories"].filter(lambda cat: cat != category_id)
            ).run(
                cls._rdb_connection
            )

    @classmethod
    def add_category_to_storage_pool(cls, storage_pool_id, category_id):
        """_From /api/libv2/api_storage.py add_category_to_storage_pool()_"""
        if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
            raise Error(
                "bad_request", "Unable to assign category to default storage pool"
            )
        with cls._rdb_context():
            r.table("storage_pool").get(storage_pool_id).update(
                {"categories": r.row["categories"].append(category_id)}
            ).run(cls._rdb_connection)

    @classmethod
    def check_category_storage_pool_availability(
        cls, categories_ids, storage_pool_id=None
    ):
        """_From /api/libv2/api_storage.py check_category_storage_pool_availability()_

        Check if these categories are in another storage pool

        :param categories_ids: List of category ids
        :type categories_ids: list
        :param storage_pool_id: Storage pool id
        :type storage_pool_id: str
        :return: True if none of the categories are in another storage pool, otherwise False
        :rtype: bool
        """
        query = r.table("storage_pool").pluck("categories", "id")
        if storage_pool_id:
            query = query.filter(r.row["id"] != storage_pool_id)

        with cls._rdb_context():
            existing_categories = list(query.run(cls._rdb_connection))

        return not any(
            any(category_id in pool["categories"] for category_id in categories_ids)
            for pool in existing_categories
        )
