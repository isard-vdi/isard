#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import re
import traceback

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.models.category import Category
from isardvdi_common.models.group import Group
from isardvdi_common.models.user import User
from isardvdi_common.schemas.shared.allowed import AllowedUpdate
from rethinkdb import r

_get_user_cache: TTLCache = TTLCache(maxsize=20, ttl=5)
_get_allowed_groups_cache: TTLCache = TTLCache(maxsize=20, ttl=60)


class Alloweds(RethinkCustomBase):

    @classmethod
    @cached(cache=_get_user_cache)
    def get_user(cls, user_id):
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .without("password", "user_storage")
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_user_cache(cls):
        _get_user_cache.clear()

    @classmethod
    @cached(
        cache=TTLCache(maxsize=500, ttl=5),
        key=lambda cls, user_id, user_group_id, groups: hashkey(
            user_id + user_group_id + str(groups)
        ),
    )
    def check_secondary_groups(cls, user_id, user_group_id, item_allowed_groups):
        secondary_groups = cls.get_user(user_id).get("secondary_groups", [])
        for group in cls.get_all_linked_groups([user_group_id] + secondary_groups):
            if group in item_allowed_groups:
                return True
        return False

    @classmethod
    @cached(
        cache=TTLCache(maxsize=10, ttl=5), key=lambda cls, groups: hashkey(str(groups))
    )
    def get_all_linked_groups(cls, groups):
        with cls._rdb_context():
            linked_groups = list(
                r.table("groups")
                .get_all(r.args(groups), index="id")
                .pluck("linked_groups")
                .run(cls._rdb_connection)
            )
        for lg in linked_groups:
            groups += lg.get("linked_groups", [])
        return list(dict.fromkeys(groups))

    @classmethod
    def get_table_term(
        cls,
        table,
        field,
        value,
        pluck=False,
        query_filter={},
        index_key=None,
        index_value=None,
    ):
        query = r.table(table)
        if index_key and index_value:
            query = query.get_all(index_value, index=index_key)
        if query_filter:
            query = query.filter(query_filter)
        if table == "groups":
            query = query.merge(
                lambda d: {
                    "category_name": r.table("categories")
                    .get(d["parent_category"])
                    .default({"name": "[deleted]"})["name"],
                }
            )
        if table == "users":
            query = query.filter(lambda user: user["active"].eq(True)).merge(
                lambda d: {
                    "category_name": r.table("categories")
                    .get(d["category"])
                    .default({"name": "[deleted]"})["name"],
                    "group_name": r.table("groups")
                    .get(d["group"])
                    .default({"name": "[deleted]"})["name"],
                }
            )
        with cls._rdb_context():
            return list(
                query.filter(lambda doc: doc[field].match("(?i)" + re.escape(value)))
                .pluck(pluck)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_allowed(cls, allowed):
        for k, v in allowed.items():
            if k == "groups" and v != False and len(v):
                with cls._rdb_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .merge(
                            lambda d: {
                                "category_name": r.table("categories")
                                .get(d["parent_category"])
                                .default({"name": "[deleted]"})["name"],
                            }
                        )
                        .pluck("id", "name", "uid", "parent_category", "category_name")
                        .run(cls._rdb_connection)
                    )
            elif k == "users" and v != False and len(v):
                with cls._rdb_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .merge(
                            lambda d: {
                                "category_name": r.table("categories")
                                .get(d["category"])
                                .default({"name": "[deleted]"})["name"],
                                "group_name": r.table("groups")
                                .get(d["group"])
                                .default({"name": "[deleted]"})["name"],
                            }
                        )
                        .pluck(
                            "id",
                            "name",
                            "uid",
                            "username",
                            "photo",
                            "group_name",
                            "category_name",
                        )
                        .run(cls._rdb_connection)
                    )
            elif v != False and len(v):
                with cls._rdb_context():
                    allowed[k] = list(
                        r.table(k)
                        .get_all(r.args(v), index="id")
                        .pluck("id", "name", "uid", "parent_category")
                        .run(cls._rdb_connection)
                    )
        return allowed

    @classmethod
    def build_shared_items_filter(
        cls,
        user_role: str,
        user_category: str,
        user_group: str,
        user_id: str,
        include_own: bool = False,  # Include owned items in the filter
        consider_user_role: bool = False,  # Consider user role in the filter (admin can see all, manager can see own category)
    ):
        if include_own:
            own_item_access = r.row["user"].eq(user_id)

        if consider_user_role and user_role == "admin":
            return True

        if consider_user_role and user_role == "manager":
            shared_conditions = [r.row["category"].eq(user_category)]
        else:
            shared_conditions = []

        allowed = r.row["allowed"]

        shared_conditions += [
            r.and_(
                allowed["roles"].type_of().eq("ARRAY"),
                r.or_(
                    allowed["roles"].count().eq(0),
                    allowed["roles"].contains(user_role),
                ),
            ),
            r.and_(
                allowed["categories"].type_of().eq("ARRAY"),
                r.or_(
                    allowed["categories"].count().eq(0),
                    allowed["categories"].contains(user_category),
                ),
            ),
            r.and_(
                allowed["groups"].type_of().eq("ARRAY"),
                r.or_(
                    r.and_(
                        allowed["groups"].count().eq(0),
                        r.row["category"].eq(user_category),
                    ),
                    allowed["groups"].contains(user_group),
                ),
            ),
            r.and_(
                allowed["users"].type_of().eq("ARRAY"),
                r.or_(
                    r.and_(
                        allowed["users"].count().eq(0),
                        r.row["category"].eq(user_category),
                    ),
                    allowed["users"].contains(user_id),
                ),
            ),
        ]

        return r.or_(
            *shared_conditions,
            own_item_access if include_own else r.expr(False),
        )

    # TODO: Evaluate if this would be better
    #       than the current get_items_allowed implementation
    # @classmethod
    # def get_items_allowed(
    #     cls,
    #     payload,
    #     table: str,
    #     query_pluck: list = [],
    #     query_filter: dict = {},
    #     index_key: str = None,
    #     index_value: list = None,
    #     order: str = None,
    #     query_merge: bool = True,
    #     consider_user_role: bool = True,
    #     extra_ids_allowed: list = [],
    #     include_own: bool = False,
    # ):
    #     try:
    #         build_shared_templates_filter = cls.build_shared_items_filter(
    #             user_role=payload["role_id"],
    #             user_category=payload["category_id"],
    #             user_group=payload["group_id"],
    #             user_id=payload["user_id"],
    #             include_own=include_own,
    #             consider_user_role=consider_user_role,
    #         )

    #         query = r.table(table)

    #         if index_key and index_value:
    #             query = query.get_all(index_value, index=index_key)

    #         query = query.filter(build_shared_templates_filter)

    #         if query_filter:
    #             query = query.filter(query_filter)

    #         if query_merge:
    #             query = query.merge(
    #                 lambda item: {
    #                     "category_name": r.table(Category._rdb_table)
    #                     .get(item["category"])
    #                     .pluck("name")
    #                     .default({"name": "DELETED"})["name"],
    #                     "group_name": r.table(Group._rdb_table)
    #                     .get(item["group"])
    #                     .pluck("name")
    #                     .default({"name": "DELETED"})["name"],
    #                     "user_name": r.table(User._rdb_table)
    #                     .get(item["user"])
    #                     .pluck("name")
    #                     .default({"name": "DELETED"})["name"],
    #                     "user": r.table(User._rdb_table)
    #                     .get(item["user"])
    #                     .pluck("id", "name", "photo")
    #                     .default({"name": "DELETED", "photo": None}),
    #                 }
    #             )
    #             if len(query_pluck) > 0:
    #                 query = query.pluck(
    #                     query_pluck
    #                     + [
    #                         "id",
    #                         "allowed",
    #                         "category",
    #                         "category_name",
    #                         "group",
    #                         "group_name",
    #                         "user",
    #                         "user_name",
    #                     ]
    #                 )
    #         else:
    #             if query_pluck:
    #                 query = query.pluck(query_pluck)

    #         if order:
    #             query = query.order_by(order)

    #         # If extra_ids_allowed is provided, these IDs will be included in the query
    #         # regardless of the other filters.
    #         # This is useful for cases where we want to ensure certain items are always included,
    #         # such as when a user has specific permissions that should override the general filters.
    #         if extra_ids_allowed:
    #             query = query.get_all(r.args(extra_ids_allowed)).union(query)

    #         with cls._rdb_context():
    #             items = list(query.run(cls._rdb_connection))

    #         return items

    #     except Exception:
    #         raise Error(
    #             "internal_server",
    #             "Internal server error",
    #             traceback.format_exc(),
    #             description_code="generic_error",
    #         )

    @classmethod
    def get_items_allowed(
        cls,
        payload,
        table,
        query_pluck=[],
        query_filter={},
        index_key=None,
        index_value=None,
        order=None,
        query_merge=True,
        extra_ids_allowed=[],
        only_in_allowed=False,
        exclude_owner_user_id=None,
        require_enabled=False,
    ):
        try:
            query = r.table(table)
            if index_key and index_value:
                query = query.get_all(index_value, index=index_key)
            # Declarative shortcuts so apiv4 services don't need to
            # import ``r`` directly (architectural pin —
            # ``test_no_rethink_in_services``). Both compose with an
            # explicit ``query_filter`` if the caller provides one.
            if exclude_owner_user_id and require_enabled:
                query = query.filter(
                    lambda t: r.not_(t["user"] == exclude_owner_user_id) & t["enabled"]
                )
            elif exclude_owner_user_id:
                query = query.filter(
                    lambda t: r.not_(t["user"] == exclude_owner_user_id)
                )
            elif require_enabled:
                query = query.filter({"enabled": True})
            if query_filter:
                query = query.filter(query_filter)
            if query_merge:
                query = query.merge(
                    lambda d: {
                        "category_name": r.table("categories")
                        .get(d["category"])["name"]
                        .default(None),
                        "group_name": r.table("groups")
                        .get(d["group"])["name"]
                        .default(None),
                        "user_name": r.table("users")
                        .get(d["user"])["name"]
                        .default(None),
                        "user": r.table("users")
                        .get(d["user"])
                        .pluck("id", "name", "photo")
                        .default({"name": "DELETED", "photo": None}),
                    }
                )
                if len(query_pluck) > 0:
                    query = query.pluck(
                        query_pluck
                        + [
                            "id",
                            "allowed",
                            "category",
                            "category_name",
                            "group",
                            "group_name",
                            "user",
                            "user_name",
                        ]
                    )
            else:
                if len(query_pluck) > 0:
                    query = query.pluck(["id", "allowed"] + query_pluck)
            if order:
                query = query.order_by(order)
            with cls._rdb_context():
                items = list(query.run(cls._rdb_connection))

            allowed = []
            for item in items:
                if (
                    payload["role_id"] == "admin"
                    or (
                        payload["role_id"] == "manager"
                        and payload["category_id"] == item.get("category")
                    )
                    or item.get("user") == payload["user_id"]
                ):
                    item["editable"] = True
                else:
                    item["editable"] = False
                if item["id"] in extra_ids_allowed or cls.is_allowed(
                    payload, item, table, ignore_role=only_in_allowed
                ):
                    allowed.append(item)

            return allowed
        except Exception:
            from isardvdi_common.helpers.error_factory import Error

            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )

    # ──────────────────────────────────────────────────────────────────────────────

    @classmethod
    def is_allowed(cls, payload, item, table, ignore_role=False):
        if not payload.get("user_id", False):
            return False
        if not ignore_role and (
            payload["role_id"] == "admin"
            or item.get("user") == payload["user_id"]
            or (
                payload["role_id"] == "manager"
                and item.get("category") == payload["category_id"]
            )
        ):
            return True
        if item["allowed"]["roles"] is not False:
            if len(item["allowed"]["roles"]) == 0:
                return True
            else:
                if payload["role_id"] in item["allowed"]["roles"]:
                    return True
        if item["allowed"]["categories"] is not False:
            if len(item["allowed"]["categories"]) == 0:
                return True
            else:
                if payload["category_id"] in item["allowed"]["categories"]:
                    return True
        if item["allowed"]["groups"] is not False:
            if len(item["allowed"]["groups"]) == 0:
                if table in ["domains", "media"]:
                    if item.get("category") == payload["category_id"]:
                        return True
                else:
                    return True
            else:
                if cls.check_secondary_groups(
                    payload["user_id"], payload["group_id"], item["allowed"]["groups"]
                ):
                    return True
        if item["allowed"]["users"] is not False:
            if len(item["allowed"]["users"]) == 0:
                if table in ["domains", "media"]:
                    if item.get("category") == payload["category_id"]:
                        return True
                else:
                    return True
                return False
            else:
                if payload["user_id"] in item["allowed"]["users"]:
                    return True
        return False

    @classmethod
    def get_domain_reservables(cls, domain_id):
        with cls._rdb_context():
            reservables = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": "reservables"})
                .run(cls._rdb_connection)
            )
        return reservables.get("create_dict", {})

    @classmethod
    def get_users_allowed(cls, allowed):
        users = []
        for k, v in allowed.items():
            if k == "categories" and v != False and len(v):
                with cls._rdb_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="category")
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
            elif k == "groups" and v != False and len(v):
                with cls._rdb_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="group")
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
            elif k == "users" and v != False and len(v):
                with cls._rdb_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="id")
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
            elif k == "roles" and v != False and len(v):
                with cls._rdb_context():
                    users.append(
                        r.table("users")
                        .get_all(r.args(v), index="role")
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
            elif v == []:
                with cls._rdb_context():
                    users.append(
                        r.table("users").pluck("id")["id"].run(cls._rdb_connection)
                    )

        # remove duplicates
        users = [item for sublist in users for item in sublist]

        return users

    @classmethod
    def remove_disallowed_bastion_targets(cls):
        with cls._rdb_context():
            targets = r.table("targets").run(cls._rdb_connection)

        with cls._rdb_context():
            bastion_alloweds = dict(
                r.table("config")
                .get(1)
                .pluck([{"bastion": "allowed"}])
                .run(cls._rdb_connection)["bastion"]["allowed"]
            )

        allowed_users = cls.get_users_allowed(bastion_alloweds)

        disallowed_targets = []

        for target in targets:
            if target["user_id"] not in allowed_users:
                disallowed_targets.append(target["id"])

        with cls._rdb_context():
            r.table("targets").get_all(r.args(disallowed_targets)).delete().run(
                cls._rdb_connection
            )

        return disallowed_targets

    # ``remove_disallowed_bastion_targets_th`` was a fire-and-forget
    # gevent.spawn wrapper around ``remove_disallowed_bastion_targets``.
    # Under apiv4's asyncio worker the spawned greenlet sat on a libev
    # Hub the loop never drives, so the cleanup silently never ran.
    # Apiv4 callers now schedule ``remove_disallowed_bastion_targets``
    # directly via FastAPI's ``BackgroundTasks``.

    @classmethod
    def update_bastion_alloweds(cls, allowed):
        with cls._rdb_context():
            r.table("config").get(1).update(
                {
                    "bastion": {
                        "allowed": allowed,
                    }
                }
            ).run(cls._rdb_connection)

    @classmethod
    def remove_disallowed_bastion_target_domains(cls):
        with cls._rdb_context():
            targets = r.table("targets").run(cls._rdb_connection)

        with cls._rdb_context():
            bastion_alloweds = dict(
                r.table("config")
                .get(1)
                .pluck([{"bastion": {"individual_domains": "allowed"}}])
                .run(cls._rdb_connection)["bastion"]["individual_domains"]["allowed"]
            )

        allowed_users = cls.get_users_allowed(bastion_alloweds)

        disallowed_targets = []

        for target in targets:
            if target["user_id"] not in allowed_users:
                disallowed_targets.append(target["id"])

        with cls._rdb_context():
            r.table("targets").get_all(r.args(disallowed_targets)).update(
                {
                    "domain": None,
                }
            ).run(cls._rdb_connection)

        return disallowed_targets

    # ``remove_disallowed_bastion_target_domains_th`` was a
    # fire-and-forget gevent.spawn wrapper. See the note on
    # ``remove_disallowed_bastion_targets_th`` above; apiv4 callers now
    # schedule via ``BackgroundTasks`` directly.

    @classmethod
    def update_bastion_target_domains_alloweds(cls, allowed):
        with cls._rdb_context():
            r.table("config").get(1).update(
                {
                    "bastion": {
                        "individual_domains": {
                            "allowed": allowed,
                        }
                    }
                }
            ).run(cls._rdb_connection)

    @classmethod
    def update_table_item_allowed(
        cls, table: str, item_id: str, allowed: AllowedUpdate
    ):
        # Convert to dict, excluding None values to support partial updates
        allowed_dict = allowed.model_dump(exclude_none=True)

        # Build the update query to only update fields that are provided
        allowed_update = {}
        for key, value in allowed_dict.items():
            allowed_update[key] = value

        with cls._rdb_context():
            r.table(table).get(item_id).update({"allowed": allowed_update}).run(
                cls._rdb_connection
            )

    @classmethod
    @cached(cache=_get_allowed_groups_cache)
    def get_allowed_groups(cls, category_id: str) -> dict:
        with cls._rdb_context():
            groups = (
                r.table(Group._rdb_table)
                .get_all(category_id, index="parent_category")
                .merge(
                    lambda d: {
                        "category_name": r.table("categories")
                        .get(d["parent_category"])
                        .default({"name": "[deleted]"})["name"],
                    }
                )
                .pluck("id", "name", "uid", "parent_category", "category_name")
                .run(cls._rdb_connection)
            )

        return groups

    @classmethod
    def clear_get_allowed_groups_cache(cls):
        _get_allowed_groups_cache.clear()

    @classmethod
    def update_item_allowed_dict(cls, table: str, item_id: str, allowed: dict) -> None:
        """Replace the ``allowed`` field of a row in ``table`` with the
        given dict.

        Companion to ``update_table_item_allowed`` (which takes a typed
        ``AllowedUpdate`` model + does partial-key merging) — this one
        takes a raw dict the caller has already shaped, used by the
        admin endpoints that pass ``data["allowed"]`` straight through.
        """
        with cls._rdb_context():
            r.table(table).get(item_id).update({"allowed": allowed}).run(
                cls._rdb_connection
            )

    @classmethod
    def get_item_allowed_dict(cls, table: str, item_id: str) -> dict:
        """Read the ``allowed`` field of a row in ``table``.

        Returns the raw dict (uses ``pluck("allowed")`` so we don't
        round-trip the whole row). Caller is responsible for passing
        through to ``Alloweds.get_allowed(...)`` for name enrichment.
        """
        with cls._rdb_context():
            item = r.table(table).get(item_id).pluck("allowed").run(cls._rdb_connection)
        return item.get("allowed", {}) if item else {}

    @classmethod
    def get_bastion_allowed_dict(cls) -> dict:
        """Read ``config[id=1].bastion.allowed``.

        Used by the admin /allowed endpoints to render the bastion-wide
        allowed list. Returns ``{}`` when the field is missing (fresh
        deployments before the bastion was first configured).
        """
        with cls._rdb_context():
            config = (
                r.table("config")
                .get(1)
                .pluck({"bastion": "allowed"})
                .default({"bastion": {"allowed": {}}})
                .run(cls._rdb_connection)
            )
        return config.get("bastion", {}).get("allowed", {})

    @classmethod
    def get_bastion_domains_allowed_dict(cls) -> dict:
        """Read ``config[id=1].bastion.individual_domains.allowed``."""
        with cls._rdb_context():
            config = (
                r.table("config")
                .get(1)
                .pluck({"bastion": {"individual_domains": "allowed"}})
                .default({"bastion": {"individual_domains": {"allowed": {}}}})
                .run(cls._rdb_connection)
            )
        return (
            config.get("bastion", {}).get("individual_domains", {}).get("allowed", {})
        )
