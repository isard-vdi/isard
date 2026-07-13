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


import re
import time
import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.storage.storage_pools.paths import CATEGORY_TOKEN
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task
from rethinkdb import r


class StoragePoolsProcessed(RethinkSharedConnection):

    _rdb_table = "storage_pool"

    # A category pool must live under /isard/storage_pools/<name> (host
    # /opt/isard/storage_pools/<name>) - the only path bind-mounted into the
    # storage and hypervisor containers.
    STORAGE_POOLS_ROOT = "/isard/storage_pools"

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
    def _check_mountpoint_safe(cls, mountpoint):
        """_From /api/libv2/api_storage.py \_check_mountpoint_safe()_

        A category pool's mountpoint must be /isard/storage_pools/<name>.

        That root (host /opt/isard/storage_pools) is the only storage location
        bind-mounted into the storage and hypervisor containers, so a mountpoint
        outside it - or one using '..' to climb out - would put disks where the
        containers cannot reach them. The leaf is the admin-chosen directory
        name and must be a single safe path segment.
        """
        prefix = cls.STORAGE_POOLS_ROOT + "/"
        if not mountpoint or "\x00" in mountpoint or not mountpoint.startswith(prefix):
            raise Error(
                "bad_request",
                f"Storage pool mountpoint must be under {prefix} "
                "(the only path mounted into the storage and hypervisor containers)",
            )
        leaf = mountpoint[len(prefix) :].strip("/")
        if not leaf or "/" in leaf or ".." in leaf.split("/") or leaf.strip(".") == "":
            raise Error(
                "bad_request",
                f"Storage pool mountpoint must be {prefix}<name> with a single safe "
                "segment (no '/', no '..')",
            )
        if leaf == "default":
            # Reserved: fresh installs place the default pool at
            # /isard/storage_pools/default, so a category pool can't reuse that leaf.
            raise Error(
                "bad_request",
                f"Storage pool mountpoint {prefix}default is reserved for the default pool",
            )

    @classmethod
    def _check_mountpoint_unique(cls, mountpoint, exclude_id=None):
        """Reject a mountpoint already used by another storage pool.

        A pool's mountpoint is its on-disk identity: ``get_by_path`` /
        ``get_best_for_action`` resolve a disk path back to a pool by the
        longest mountpoint that is a prefix of it. Two pools sharing the exact
        same mountpoint make that reverse lookup ambiguous -- the tie is broken
        by db-scan order, so a download task can be enqueued onto the wrong
        pool's queue and, if that pool is not served by any worker, stall
        silently at ``DownloadStarting``. Sharing one physical location across
        categories is already expressed as a single multi-category pool plus the
        ``{category}`` token, so duplicate mountpoints are never needed. Enforce
        uniqueness here (``exclude_id`` skips the pool being renamed on update).
        """
        with cls._rdb_context():
            query = r.table("storage_pool").filter({"mountpoint": mountpoint})
            if exclude_id is not None:
                query = query.filter(lambda pool: pool["id"] != exclude_id)
            clash = query.count().run(cls._rdb_connection)
        if clash:
            raise Error(
                "bad_request",
                f"Storage pool mountpoint {mountpoint} is already used by another "
                "pool; each storage pool must have a unique mountpoint",
                description_code="storage_pool_mountpoint_in_use",
            )

    @staticmethod
    def _check_paths_safe(data):
        """_From /api/libv2/api_storage.py \_check_paths_safe()_

        Reject path entries that could escape the pool's category subtree.

        Pool paths are relative directory names concatenated into the on-disk
        path (<mountpoint>/<category>/<path>). They are sanitized for HTML but
        not for filesystem traversal, so an absolute path, a ".." segment or a
        null byte would let a disk land outside its tenant subtree.
        """
        for key in data:
            for item in data[key]:
                path = item.get("path", "")
                segments = path.split("/")
                if (
                    not path
                    or path.startswith("/")
                    or "\x00" in path
                    or ".." in segments
                ):
                    raise Error(
                        "bad_request",
                        f"Invalid storage pool path '{path}': must be a relative "
                        "directory without '..' segments",
                    )
                # Optional {category} placeholder: lets the tier sit before the
                # category (<mountpoint>/fast/{category}/templates). It must be a
                # whole segment and appear at most once; any other brace usage is
                # a typo and is rejected so it never becomes a literal directory.
                if segments.count(CATEGORY_TOKEN) > 1:
                    raise Error(
                        "bad_request",
                        f"Invalid storage pool path '{path}': the "
                        f"'{CATEGORY_TOKEN}' placeholder may appear at most once",
                    )
                for segment in segments:
                    if segment == CATEGORY_TOKEN:
                        continue
                    if "{" in segment or "}" in segment:
                        raise Error(
                            "bad_request",
                            f"Invalid storage pool path '{path}': '{{' and '}}' are "
                            f"only allowed as the exact '{CATEGORY_TOKEN}' segment",
                        )

    @classmethod
    def remove_common_categories_from_other_pools(cls, categories, keep_pool_id=None):
        """_From /api/libv2/api_storage.py remove_common_categories_from_other_pools()_

        Remove categories from other storage pools so they can be added to another pool

        Done as a single server-side update over all pools, so a category is
        never transiently present in two pools (or none) the way the previous
        pluck-then-loop did. ``keep_pool_id`` excludes the pool that is about to
        be written with these categories, so they are not stripped right before
        being set on it.

        :param categories: List of category ids
        :type categories: list
        :param keep_pool_id: Pool id to leave untouched
        :type keep_pool_id: str
        """
        if not categories:
            return
        query = r.table("storage_pool")
        if keep_pool_id is not None:
            query = query.filter(lambda pool: pool["id"] != keep_pool_id)
        with cls._rdb_context():
            query.update(
                lambda pool: {
                    "categories": pool["categories"].set_difference(list(categories))
                }
            ).run(cls._rdb_connection)

    @classmethod
    def add_storage_pool(cls, data):
        """_From /api/libv2/api_storage.py add_storage_pool()_"""
        # The admin chooses the leaf name; we only validate it stays within the
        # storage_pools root, is a single safe segment, and is not already used
        # by another pool (a duplicate mountpoint makes path->pool resolution
        # ambiguous).
        cls._check_mountpoint_safe(data["mountpoint"])
        cls._check_mountpoint_unique(data["mountpoint"])
        if data.get("paths"):
            cls._check_with_validate_weight(data["paths"])
            cls._check_duplicated_paths(data["paths"])
            cls._check_paths_safe(data["paths"])
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
    def _check_default_paths(paths):
        """_From /api/libv2/api_storage.py _check_default_paths()_

        The default pool must keep at least one path for every usage type. The
        specific leaf names are not pinned: legacy installs use
        groups/media/templates/volatile, fresh installs use
        desktops/templates/media/volatile under /isard/storage_pools/default.
        """
        for usage in ("desktop", "media", "template", "volatile"):
            if not paths.get(usage):
                raise Error(
                    "bad_request",
                    f"Default pool must have at least one '{usage}' path",
                )
        # The default pool has no category segment, so a {category} placeholder
        # would never be substituted and would become a literal directory.
        for entries in paths.values():
            for item in entries:
                if CATEGORY_TOKEN in item.get("path", ""):
                    raise Error(
                        "bad_request",
                        f"The '{CATEGORY_TOKEN}' placeholder is not allowed on the "
                        "default pool (it has no category)",
                    )

    @classmethod
    def update_storage_pool(cls, storage_pool_id, data):
        """_From /api/libv2/api_storage.py update_storage_pool()_"""
        if data.get("paths"):
            cls._check_duplicated_paths(data["paths"])
            cls._check_with_validate_weight(data["paths"])
            cls._check_paths_safe(data["paths"])
        if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
            if "enabled" in data:
                raise Error("bad_request", "Default pool can't be disabled")
            # The default pool stays at /isard; its name/categories are fixed too.
            for key in ["name", "description", "mountpoint", "categories"]:
                if key in data:
                    data.pop(key)
            if "paths" in data:
                cls._check_default_paths(data["paths"])
        elif "mountpoint" in data:
            # A category pool's mountpoint may be renamed (webapp allows it) but
            # must stay under /isard/storage_pools/<name> and not collide with
            # another pool's mountpoint.
            cls._check_mountpoint_safe(data["mountpoint"])
            cls._check_mountpoint_unique(data["mountpoint"], exclude_id=storage_pool_id)

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
            cls.remove_common_categories_from_other_pools(
                data["categories"], keep_pool_id=storage_pool_id
            )
        with cls._rdb_context():
            r.table("storage_pool").get(storage_pool_id).update(data).run(
                cls._rdb_connection
            )

    @classmethod
    def delete_storage_pool(cls, storage_pool_id):
        """_From /api/libv2/api_storage.py delete_storage_pool()_"""
        if storage_pool_id == DEFAULT_STORAGE_POOL_ID:
            raise Error("bad_request", "Default pool can't be removed")
        pool = StoragePool.get(storage_pool_id)
        if pool is None:
            raise Error("not_found", f"Storage pool {storage_pool_id} not found")
        # Removing a pool that still owns categories or disks orphans them: their
        # on-disk files stay under the (now unknown) mountpoint while new disks
        # fall back to the default pool. Require the admin to reassign/migrate
        # first.
        if pool.get("categories"):
            raise Error(
                "bad_request",
                "Cannot remove a storage pool that still has categories assigned; "
                "reassign them to another pool first",
            )
        mountpoint = (
            pool.get("mountpoint") or f"{cls.STORAGE_POOLS_ROOT}/{storage_pool_id}"
        )
        with cls._rdb_context():
            disks = (
                r.table("storage")
                .filter(lambda s: s["status"] != "deleted")
                .filter(
                    lambda s: s["directory_path"]
                    .default("")
                    .match("^" + re.escape(mountpoint) + "/")
                )
                .count()
                .run(cls._rdb_connection)
            )
        if disks:
            raise Error(
                "bad_request",
                f"Cannot remove storage pool: {disks} disk(s) still reside in it; "
                "migrate them to another pool first",
            )
        with cls._rdb_context():
            r.table("storage_pool").get(storage_pool_id).delete().run(
                cls._rdb_connection
            )
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
            ).run(cls._rdb_connection)

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
