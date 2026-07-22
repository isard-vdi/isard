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

from random import choice, choices
from typing import List
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.storage.storage_pools.paths import usage_subpath_matches
from pydantic import BaseModel, Field
from rethinkdb import r

from ..schemas.shared.allowed import Allowed
from ..schemas.storage_pool import *


class StoragePoolModel(BaseModel):
    allowed: Allowed
    categories: List[str]
    description: str
    enabled: bool
    enabled_virt: bool
    id: str = Field(default_factory=lambda: str(uuid4()))
    mountpoint: str
    name: str
    paths: PathsModel
    read: bool
    startable: bool
    unused_desktops_cutoff_time: int
    write: bool


class StoragePool(RethinkCustomBase):
    """
    Manage Storage Pool.

    Use constructor with keyword arguments to create new Storage Pool or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Storage Pool.
    """

    _rdb_table = "storage_pool"

    def has_category(self, category_id):
        """
        Check if Storage Pool has a category.

        :param category_id: Category id
        :type category_id: str
        :return: True if Storage Pool has category, otherwise False
        :rtype: bool
        """
        return category_id in self.categories

    def get_usage_path(self, usage):
        """
        Get best usage path by usage.

        :param usage: Usage type: desktop, media, template or volatile.
        :type path: str
        :return: Usage path
        :rtype: str
        """
        paths = []
        weights = []
        for path in self.paths.get(usage, []):
            paths.append(path.get("path"))
            weights.append(path.get("weight"))
        if not paths:
            # An empty path list would make random.choices raise an opaque
            # IndexError. Surface a clear error instead: a pool that does not
            # define a path for this usage must not be selected for it.
            raise Exception(
                "bad_request",
                f"Storage pool {self.id} has no '{usage}' path configured",
            )
        return choices(paths, weights=weights)[0]

    def get_usage_by_path(self, path):
        """
        Get usage by path.

        :param path: Path
        :type path: str
        :return: Usage type: desktop, media, template or volatile.
        :rtype: str
        """

        # Check if full_path starts with mountpoint
        if not path.startswith(self.mountpoint):
            return None  # Not in the correct mountpoint

        # Path relative to the pool mountpoint.
        relative = path[len(self.mountpoint) :].lstrip("/")

        if self.id == DEFAULT_STORAGE_POOL_ID:
            # The default pool has no per-category subdir and no {category}
            # token: match the usage path directly. `relative` is
            # "<usage_path>" or "<usage_path>/<id>.<type>".
            for usage, paths in self.paths.items():
                for path_info in paths:
                    usage_path = path_info["path"]
                    if relative == usage_path or relative.startswith(usage_path + "/"):
                        return usage
            return None

        # Category pool: usage_subpath_matches resolves both the legacy
        # <category>/<usage_path> layout and the {category}-placeholder layout
        # (e.g. fast/{category}/templates), tolerating a trailing <id>.<type>.
        for usage, paths in self.paths.items():
            for path_info in paths:
                if usage_subpath_matches(relative, path_info["path"]):
                    return usage
        return None

    @classmethod
    def get_by_path(cls, path):
        """
        Get the Storage Pool a path belongs to.

        Category pools live under /isard/storage_pools/<name> and the default
        pool at /isard, so /isard is a prefix of every category-pool path. The
        pool is therefore resolved by the LONGEST mountpoint that is a prefix of
        the path, so the most specific pool wins over the default ancestor. This
        replaces the previous hardcoded "/isard/storage_pools/<id>" string
        surgery and stays correct for any leaf name an admin gives a pool.

        When no mountpoint is a prefix of the path (e.g. the path belongs to a
        removed pool) the default pool is returned so callers never get an empty
        result and crash on ``[0]``.

        :param path: Path
        :type path: str
        :return: StoragePool objects (the single best match, or empty if even
            the default pool is missing)
        :rtype: list
        """
        with cls._rdb_context():
            try:
                pools = list(
                    r.table(cls._rdb_table)
                    .pluck("id", "mountpoint", "enabled")
                    .run(cls._rdb_connection)
                )
            except Exception:
                return []

        best = None
        for pool in pools:
            mountpoint = pool.get("mountpoint")
            if not mountpoint:
                continue
            # A mountpoint matches when the path is the mountpoint itself or
            # lives under it. Compare against "<mountpoint>/" so "/isard" does
            # not spuriously match "/isardvdi/...".
            if path == mountpoint or path.startswith(mountpoint.rstrip("/") + "/"):
                if best is None:
                    best = pool
                    continue
                cur_len, best_len = len(mountpoint), len(best["mountpoint"])
                # Longest mountpoint wins (most specific pool over the default
                # ancestor). On an exact-length tie -- two pools sharing a
                # mountpoint, which add/update now forbid but legacy data may
                # still hold -- break it deterministically: prefer an enabled
                # pool, then the lowest id, so the resolution never depends on
                # db-scan order (which silently routed downloads to a worker-less
                # duplicate before).
                if cur_len > best_len:
                    best = pool
                elif cur_len == best_len:
                    cur_key = (pool.get("enabled", True) is False, pool["id"])
                    best_key = (best.get("enabled", True) is False, best["id"])
                    if cur_key < best_key:
                        best = pool

        if best is None:
            best = next((p for p in pools if p["id"] == DEFAULT_STORAGE_POOL_ID), None)
            if best is None:
                return []
        return [cls(best["id"])]

    @classmethod
    def get_by_user_kind(cls, user_id, kind):
        """
        Get Storage Pools based on a user's category and that has a specific kind of path

        :param user: User
        :type user: str
        :return: StoragePool objects
        :rtype: list
        """

        with cls._rdb_context():
            category_id = (
                r.table("users").get(user_id)["category"].run(cls._rdb_connection)
            )
        with cls._rdb_context():
            sps = list(r.table(cls._rdb_table).run(cls._rdb_connection))
        default = {}

        for sp in sps:
            if sp["id"] == DEFAULT_STORAGE_POOL_ID:
                default = sp
            # Only route a category to its pool when the pool is enabled and
            # actually has a non-empty path list for this usage. A disabled pool
            # (F5) or one missing this usage (F1) falls through to the default
            # pool, which always defines every usage. `paths.get(kind)` is empty
            # for both a missing key and a configured-but-empty list.
            if (
                sp.get("enabled", True) is not False
                and category_id in sp.get("categories", [])
                and sp.get("paths", {}).get(kind)
            ):
                return cls.init_document(**sp)
        return cls.init_document(**default)

    @classmethod
    def get_best_for_action(cls, action, path=None):
        """
        Get the best Storage Pool for an action.
        Currently the best Storage Pool is selected randomly.

        :param path: Path
        :type path: str
        :return: StoragePool object
        :rtype: StoragePool
        """
        if path:
            storage_pools = cls.get_by_path(path)
        else:
            storage_pools = cls.get_all()
        # No eligible pool (empty/misconfigured storage_pool table). Surface a
        # typed error instead of returning None — every caller dereferences
        # ``.id`` on the result, so a None would become an opaque 500 for what
        # is really a "no storage pool available, try later" condition.
        if not len(storage_pools):
            raise Error(
                "precondition_required",
                f"No storage pool available for action '{action}'",
                description_code="no_storage_pool_available",
            )
        return choice(storage_pools)
