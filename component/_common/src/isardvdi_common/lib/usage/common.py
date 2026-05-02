#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Shared usage-consolidation helpers.

These helpers back the per-item-type consolidators (desktop / user /
storage / media / consolidate). Layer-2 entry points are
``UsageProcessed`` classmethods that touch RethinkDB; pure-logic
helpers (``get_owner_info`` lookup, ``securize_eval``) are exposed as
module-level functions so the consolidator code can mix them with the
classmethod calls without a layer hop.
"""

import ast
import logging
from datetime import datetime

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError

log = logging.getLogger(__name__)

# Named caches so writers can invalidate them after mutations.
_group_name_cache: TTLCache = TTLCache(maxsize=1000, ttl=240)
_category_name_cache: TTLCache = TTLCache(maxsize=1000, ttl=240)
_owners_info_cache: TTLCache = TTLCache(maxsize=1, ttl=240)
_params_cache: TTLCache = TTLCache(maxsize=100, ttl=60)
_params_item_type_custom_cache: TTLCache = TTLCache(maxsize=100, ttl=60)


class UsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for usage consolidators.

    Aggregates over ``usage_consumption`` / ``usage_parameter`` plus
    name lookups against ``users`` / ``groups`` / ``categories``. The
    cached methods carry their own ``clear_*_cache`` invalidator, plus
    a single ``clear_all_caches`` entry point for the admin
    "reload usage parameters" button.
    """

    @classmethod
    @cached(cache=_group_name_cache)
    def get_group_name(cls, group_id: str) -> str:
        """Return the group's display name, or ``[DELETED]`` if absent."""
        try:
            with cls._rdb_context():
                group = (
                    r.table("groups")
                    .get(group_id)
                    .pluck("name")
                    .run(cls._rdb_connection)
                )
        except ReqlNonExistenceError:
            group = {"name": "[DELETED]"}
        return group["name"]

    @classmethod
    def clear_get_group_name_cache(cls) -> None:
        """Invalidate the group-name cache."""
        _group_name_cache.clear()

    @classmethod
    @cached(cache=_category_name_cache)
    def get_category_name(cls, category_id: str) -> str:
        """Return the category's display name, or ``[DELETED]`` if absent."""
        try:
            with cls._rdb_context():
                category = (
                    r.table("categories")
                    .get(category_id)
                    .pluck("name")
                    .run(cls._rdb_connection)
                )
        except ReqlNonExistenceError:
            category = {"name": "[DELETED]"}
        return category["name"]

    @classmethod
    def clear_get_category_name_cache(cls) -> None:
        """Invalidate the category-name cache."""
        _category_name_cache.clear()

    @classmethod
    @cached(cache=_owners_info_cache)
    def get_owners_info(cls) -> dict:
        """Return a {user_id: owner_info} mapping for every known user.

        The owner_info dict contains user/group/category id+name. Used
        by every consolidator's ``get_owner_info`` lookup. Cached for
        4 minutes to keep batch consolidations fast.

        Defensive against orphan user rows: a row that lacks ``name``,
        ``group``, or ``category`` (manually inserted, abandoned
        migration, etc.) historically crashed the whole consolidate
        pass with ``KeyError: 'name'``. Now each missing field falls
        back to an ``[ORPHAN]`` placeholder and emits a single warning
        log so the bad row stays visible without taking down the
        admin "consolidate consumption" trigger. Same defensive-guard
        shape as the gpu-profiles fix in
        ``isardvdi_common.lib.bookings.reservables``.
        """
        with cls._rdb_context():
            users = list(
                r.table("users")
                .pluck("id", "name", "group", "category")
                .run(cls._rdb_connection)
            )
        info = {}
        for user in users:
            missing = [k for k in ("name", "group", "category") if k not in user]
            if missing:
                log.warning(
                    "usage: orphan user row %s missing %s; using [ORPHAN] placeholder",
                    user.get("id", "<no id>"),
                    missing,
                )
            group_id = user.get("group")
            category_id = user.get("category")
            info[user["id"]] = {
                "owner_user_id": user["id"],
                "owner_user_name": user.get("name", "[ORPHAN]"),
                "owner_group_id": group_id or "[ORPHAN]",
                "owner_group_name": (
                    cls.get_group_name(group_id) if group_id else "[ORPHAN]"
                ),
                "owner_category_id": category_id or "[ORPHAN]",
                "owner_category_name": (
                    cls.get_category_name(category_id) if category_id else "[ORPHAN]"
                ),
            }
        return info

    @classmethod
    def clear_get_owners_info_cache(cls) -> None:
        """Invalidate the owners-info cache."""
        _owners_info_cache.clear()

    @classmethod
    def get_abs_consumptions(cls, item_type: str, date: datetime) -> dict:
        """Return absolute consumptions for ``item_type`` up to ``date``.

        Values are flattened to ``"<item_id>##<consumer>" -> reduction``
        so consolidators can substract incremental data day-over-day
        without re-grouping.
        """
        with cls._rdb_context():
            return (
                r.table("usage_consumption")
                .get_all(item_type, index="item_type")
                .filter(r.row["date"] <= date)
                .group("item_id", "item_consumer")
                .max("date")
                .ungroup()
                .map(
                    lambda item: [
                        item["group"][0] + "##" + item["group"][1],
                        item["reduction"],
                    ]
                )
                .coerce_to("object")
                .run(cls._rdb_connection, array_limit=300000)
            )

    @classmethod
    @cached(cache=_params_cache)
    def get_params(cls) -> dict:
        """Return all usage parameters grouped by ``item_type``."""
        with cls._rdb_context():
            return (
                r.table("usage_parameter")
                .group("item_type")
                .ungroup()
                .map(lambda item: [item["group"], item["reduction"]])
                .coerce_to("object")
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_params_cache(cls) -> None:
        """Invalidate the usage-parameters cache."""
        _params_cache.clear()

    @classmethod
    def get_default_consumption(cls, parameters_ids: list[str] | None = None) -> dict:
        """Return ``{parameter_id: default_value}`` for the given ids.

        ``parameters_ids=None`` returns defaults for every parameter.
        """
        with cls._rdb_context():
            query = r.table("usage_parameter")
            if parameters_ids:
                query = query.get_all(r.args(parameters_ids))
            default_consumption = list(query.run(cls._rdb_connection))
        return {dc["id"]: dc["default"] for dc in default_consumption}

    @classmethod
    @cached(cache=_params_item_type_custom_cache)
    def get_params_item_type_custom(cls, item_type: str, custom: bool) -> list[dict]:
        """Return the parameter rows for ``item_type`` matching ``custom``."""
        with cls._rdb_context():
            return list(
                r.table("usage_parameter")
                .get_all([custom, item_type], index="custom_type")
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_params_item_type_custom_cache(cls) -> None:
        """Invalidate the per-item-type-custom parameter cache."""
        _params_item_type_custom_cache.clear()

    @classmethod
    def list_consumers(cls, item_type: str) -> list[str]:
        """Return the distinct ``item_consumer`` values seen for ``item_type``."""
        with cls._rdb_context():
            return list(
                r.table("usage_consumption")
                .get_all(item_type, index="item_type")
                .pluck("item_consumer")
                .distinct()["item_consumer"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def count_consumption_rows(cls) -> int:
        """Return the total number of rows in ``usage_consumption``."""
        with cls._rdb_context():
            return r.table("usage_consumption").count().run(cls._rdb_connection)

    @classmethod
    def delete_all_consumption(cls) -> None:
        """Wipe every row from ``usage_consumption``.

        Used by the admin "reset usage data" path. Caller must be sure;
        there is no soft-delete fallback.
        """
        with cls._rdb_context():
            r.table("usage_consumption").delete().run(cls._rdb_connection)

    @classmethod
    def unify_item_name(cls, item_id: str) -> str:
        """Rewrite every consumption row's ``item_name`` to the latest one.

        Items can be renamed (e.g. desktop name change); historical
        consumption rows keep the old name and trigger duplicate-id
        rendering in the admin UI. This helper picks the most-recent
        row's name and back-fills it across the rest. Raises
        ``not_found`` if no consumption row exists for the id.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            rows = list(
                r.table("usage_consumption")
                .get_all(item_id, index="item_id")
                .order_by("date")
                .run(cls._rdb_connection)
            )
        if not rows:
            raise Error(
                "not_found",
                f"No consumption data for item {item_id}",
                description_code="consumption_not_found",
            )
        current_name = rows[-1]["item_name"]
        with cls._rdb_context():
            r.table("usage_consumption").get_all(item_id, index="item_id").filter(
                lambda uc: uc["item_name"] != current_name
            ).update({"item_name": current_name}).run(cls._rdb_connection)
        return current_name

    @classmethod
    def check_item_ownership(cls, payload: dict, filters: dict) -> None:
        """Reject manager access to items outside their own category.

        ``filters`` carries ``item_type`` and ``item_ids``; the manager
        category is in ``payload["category_id"]``. For each item kind
        we verify the resource's parent category matches; admins
        bypass via the absent ``role_id == "manager"`` check.
        """
        from isardvdi_common.helpers.error_factory import Error

        if not filters.get("item_ids"):
            return
        item_type = filters.get("item_type")
        if item_type == "category":
            for item_id in filters["item_ids"]:
                if (
                    payload["role_id"] == "manager"
                    and payload["category_id"] != item_id
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this category",
                    )
        elif item_type == "group":
            for item_id in filters["item_ids"]:
                with cls._rdb_context():
                    group = (
                        r.table("groups")
                        .get(item_id)
                        .pluck("parent_category")
                        .run(cls._rdb_connection)
                    )
                if (
                    group
                    and payload["role_id"] == "manager"
                    and payload["category_id"] != group.get("parent_category")
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this group",
                    )
        elif item_type == "user":
            for item_id in filters["item_ids"]:
                with cls._rdb_context():
                    user = (
                        r.table("users")
                        .get(item_id)
                        .pluck("category")
                        .run(cls._rdb_connection)
                    )
                if (
                    user
                    and payload["role_id"] == "manager"
                    and payload["category_id"] != user.get("category")
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this user",
                    )

    @classmethod
    def get_logs_started_time(cls, item_type: str) -> datetime:
        """Return the earliest ``started_time`` in ``logs_<item_type>``.

        Backs the ``consolidate_consumptions(total_days="all")`` path
        — the admin trigger uses this to compute how far back to roll
        consolidation. ``item_type`` is interpolated into the table
        name; callers must pass a known kind ("desktop", "user", ...).
        """
        with cls._rdb_context():
            return (
                r.table("logs_" + item_type)
                .order_by(index="started_time")
                .nth(0)["started_time"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_all_caches(cls) -> None:
        """Clear every usage helper cache at once.

        Usage parameters are admin-edited via the usage admin
        endpoints; a single sweep helper keeps writers from having to
        know each cache name.
        """
        _group_name_cache.clear()
        _category_name_cache.clear()
        _owners_info_cache.clear()
        _params_cache.clear()
        _params_item_type_custom_cache.clear()


def get_owner_info(user_id: str) -> dict:
    """Return ``user_id``'s owner info, or a placeholder if missing.

    Pure lookup over ``UsageProcessed.get_owners_info()`` — kept as a
    module function so consolidators don't have to know about the
    cache shape.
    """
    owners = UsageProcessed.get_owners_info()
    if user_id in owners:
        return owners[user_id]
    return {
        "owner_user_id": user_id,
        "owner_user_name": "[DELETED]",
        "owner_group_id": "[USER DELETED]",
        "owner_group_name": "[USER DELETED]",
        "owner_category_id": "[USER DELETED]",
        "owner_category_name": "[USER DELETED]",
    }


def securize_eval(formula: str, safe_dict: dict):
    """Evaluate a custom usage-parameter formula against ``safe_dict``.

    Whitelist-based AST validation prevents attribute / subscript /
    import abuse. Builtins are disabled for the eval call. This is
    a 1:1 port of the apiv4 securize_eval; admin-only formulas only.
    """
    whitelist = (
        ast.Expression,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.BinOp,
        ast.UnaryOp,
        ast.operator,
        ast.unaryop,
        ast.cmpop,
        ast.Num,
        ast.Constant,
    )
    denylist = (ast.Attribute, ast.Subscript, ast.Import, ast.ImportFrom)
    tree = ast.parse(formula, mode="eval")
    has_denied = any(isinstance(node, denylist) for node in ast.walk(tree))
    if has_denied:
        raise ValueError(f"Formula contains forbidden constructs: {formula}")
    valid = all(isinstance(node, whitelist) for node in ast.walk(tree))
    if valid:
        # AST-validated formula with builtins disabled; admin-only
        # custom usage parameter computations.
        return eval(  # noqa: S307
            compile(tree, filename="", mode="eval"),
            {"__builtins__": None},
            safe_dict,
        )
    raise ValueError(f"Formula contains non-whitelisted constructs: {formula}")
