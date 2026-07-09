#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer
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

import logging as logger
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from os import getenv

import jwt
from cachetools import cached
from cachetools.keys import hashkey
from isardvdi_common.configuration import Configuration
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.category import Category
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.schemas.recycle_bin import RecycleBinStatusEnum
from rethinkdb import r

from ....connections.api_notifier import send_verification_email
from ....connections.api_sessions import get_user_session_id, revoke_user_session
from ....helpers.api_notify import notify_admin
from ....helpers.bastion import Bastion
from ....helpers.desktop_events import DesktopEvents
from ....helpers.error_factory import Error
from ....helpers.helpers import Helpers
from ....helpers.password import Password
from ....helpers.quotas import Quotas
from ....helpers.recycle_bin import Helpers as RecycleBinHelpers
from ....helpers.recycle_bin import RecycleBinDeleteQueue, RecycleBinUser
from ....helpers.user_storage import UserStorage
from ....lib.users.categories.categories import CategoriesProcessed
from ....models.user import UserModel
from ....schemas.user import UserFromCSV
from .user_policies import UserPolicies


class UsersProcessed(RethinkSharedConnection):

    _rdb_table = "users"

    @classmethod
    def ids_by_groups(cls, group_ids: list):
        """
        Get all users from a list of groups
        """
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(r.args(group_ids), index="group")["id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_by_category(cls, category_id: str) -> list[dict]:
        """List users in ``category_id`` with the admin-summary
        fields (id, name, username, photo, role, group, active).

        Used by the webapp's category detail panel to render the
        member-user table.
        """
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(category_id, index="category")
                .pluck("id", "name", "username", "photo", "role", "group", "active")
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_with_category(cls, category_id: str | None) -> list:
        """
        Get all users with their categories.

        Returns:
            list: A list of dictionaries containing user information.
        """
        query = r.table(cls._rdb_table)

        if category_id:
            query = query.get_all(category_id, index="category")

        query = query.merge(
            {
                "category_name": r.table("categories")
                .get(r.row["category"])
                .default({"name": "[deleted]"})["name"],
                "photo": r.branch(r.row.has_fields("photo"), r.row["photo"], ""),
            }
        ).pluck("id", "name", "category", "category_name", "photo", "accessed")

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_user_role_group_and_category_name(cls, user_id):
        # Defensive ``.default(...)`` on each bracket access so a user
        # row that references a category / group / role that has already
        # been deleted (race between user-create and category-delete in
        # bulk flows like k6 load tests) does not crash the whole change-
        # handler with ``ReqlNonExistenceError: Cannot perform bracket
        # on a non-object non-sequence ``null```.  Missing referenced
        # rows surface as ``None`` in the returned dict; consumers
        # already tolerate that shape.
        with cls._rdb_context():
            group_and_category_names = (
                r.table(cls._rdb_table)
                .get(user_id)
                .pluck("role", "group", "category", "secondary_groups")
                .merge(
                    lambda user: {
                        "role_name": r.table("roles")
                        .get(user["role"])
                        .default({"name": None})["name"],
                        "group_name": r.table("groups")
                        .get(user["group"])
                        .default({"name": None})["name"],
                        "category_name": r.table("categories")
                        .get(user["category"])
                        .default({"name": None})["name"],
                        "secondary_groups_data": r.table("groups")
                        .get_all(r.args(user["secondary_groups"]))
                        .pluck("id", "name")
                        .coerce_to("array"),
                    }
                )
                .run(cls._rdb_connection)
            )
        return group_and_category_names

    @classmethod
    def check_user_exists(cls, uid: str, category_id: str, provider: str) -> bool:
        """
        Check if a user exists in the database.

        Args:
            user_id (str): The ID of the user to check.
            category_id (str): The category ID of the user.
            provider (str): The provider of the user.

        Returns:
            bool: True if the user exists, False otherwise.
        """
        with cls._rdb_context():
            return any(
                r.table(cls._rdb_table)
                .get_all([uid, category_id, provider], index="uid_category_provider")
                .run(cls._rdb_connection)
            )

    @classmethod
    @cached(
        cache=SynchronizedTTLCache(maxsize=100, ttl=10),
        key=lambda cls, secondary_groups: hashkey(str(secondary_groups)),
    )
    def get_secondary_groups_data(cls, secondary_groups):
        """_From api/libv2/api_users.py get_secondary_groups_data()_"""
        with cls._rdb_context():
            return (
                r.table("groups")
                .get_all(r.args(secondary_groups))
                .pluck("id", "name")
                .coerce_to("array")
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_full_data(cls, user_id):
        """_From api/libv2/api_users.py get_user_full_data()_"""
        try:
            user = Caches.get_document(cls._rdb_table, user_id)
            # user["category_name"] = get_category(user["category"])["name"]
            user["category_name"] = Caches.get_document("categories", user["category"])[
                "name"
            ]
            # user["group_name"] = get_group(user["group"])["name"]
            user["group_name"] = Caches.get_document("groups", user["group"])["name"]
            user["secondary_groups_data"] = cls.get_secondary_groups_data(
                user["secondary_groups"]
            )
        except Exception:
            raise Error(
                "not_found",
                "Not found user_id " + user_id,
                traceback.format_exc(),
            )
        return user

    @classmethod
    def get_user_last_started_desktop_log(cls, user_id):
        """_From api/libv2/api_users.py get_user_last_started_desktop_log()_

        Retrieve the last started desktop of a user.

        :param user_id: The user id.
        :type user_id: str
        :return: The users last started desktop id.
        :rtype: str
        """
        with cls._rdb_context():
            return (
                r.table("logs_desktops")
                .get_all(user_id, index="owner_user_id")
                .filter({"starting_by": "desktop-owner"})
                .order_by(r.desc("starting_time"))
                .limit(1)
                .nth(0)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_second_to_last_started_desktop_log(cls, user_id):
        """_From api/libv2/api_users.py get_user_second_to_last_started_desktop_log()_

        Retrieve the second to last started desktop of a user.

        :param user_id: The user id.
        :type user_id: str
        :return: The users second to last started desktop id.
        :rtype: str
        """
        with cls._rdb_context():
            return (
                r.table("logs_desktops")
                .get_all(user_id, index="owner_user_id")
                .filter({"starting_by": "desktop-owner"})
                .order_by(r.desc("starting_time"))
                .skip(1)
                .limit(1)
                .run(cls._rdb_connection)
            )

    @staticmethod
    def gen_impersonate_jwt(user_id, minutes=30):
        """_From api/libv2/api_users.py ApiUsers.Jwt()_

        Short-lived: the token bypasses session revocation
        (``session_id="isardvdi-service"``), so a tight TTL bounds its
        irrevocable window."""
        return {
            "jwt": jwt.encode(
                {
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
                    "kid": "isardvdi",
                    "session_id": "isardvdi-service",
                    "data": {
                        **Helpers.gen_payload_from_user(user_id),
                        "session_id": "isardvdi-service",  # Added to ignore impersonated users on the config session retrieval
                    },
                },
                getenv("API_ISARDVDI_SECRET"),
                algorithm="HS256",
            )
        }

    @staticmethod
    def gen_validate_email_jwt(user_id, email, minutes=60):
        """_From api/libv2/api_users.py validate_email_jwt()_"""
        return {
            "jwt": jwt.encode(
                {
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
                    "kid": "isardvdi",
                    "type": "email-verification",
                    "user_id": user_id,
                    "email": email,
                },
                getenv("API_ISARDVDI_SECRET"),
                algorithm="HS256",
            )
        }

    @classmethod
    def bulk_create(cls, users):
        """_From api/libv2/api_users.py bulk_create()_"""
        users = [UserModel(**user).model_dump() for user in users]

        for i in range(0, len(users), 100):
            batch_users = users[i : i + 100]
            with cls._rdb_context():
                r.table("users").insert(batch_users).run(cls._rdb_connection)
        for user in users:
            UserStorage.isard_user_storage_add_user(user["id"])

    @classmethod
    def generate_users(cls, payload, data):
        """_From api/libv2/api_users.py ApiUsers.generate_users()_"""
        batch_id = str(uuid.uuid4())

        new_users = []
        errors = []

        # TODO: Check in quotas whether can create users

        amount, total = 0, len(data["users"])
        for user in data["users"]:
            new_user = {}

            try:
                user = cls.bulk_user_check(payload, user, "generate")
            except Error as e:
                errors.append(
                    f"Skipping user {user['username']}: {e.error.get('description')}"
                )
                continue

            new_user["uid"] = user["username"]
            new_user["provider"] = "local"
            new_user["category"] = user["category_id"]
            new_user["group"] = user["group_id"]
            new_user["username"] = user["username"]
            new_user["password"] = Password.encrypt(user["password"])
            new_user["name"] = user["name"]
            new_user["role"] = user["role"]
            new_user["accessed"] = int(time.time())
            new_user["quota"] = False
            new_user["email"] = user.get("email", "")
            # # Must be done first to avoid the removal of the following fields
            # new_user = _validate_item("user", new_user)
            new_user["password_history"] = [Password.encrypt(user["password"])]
            new_user["password_last_updated"] = int(time.time())
            new_user["email_verification_token"] = None
            new_user["email_verified"] = (
                int(time.time()) if data.get("email_verified") else False
            )
            new_user["api_key"] = None
            new_users.append(new_user)

            amount += 1

            notify_admin(
                payload["user_id"],
                "User data generated",
                "user '{username}' data generated \n{amount}/{total}".format(
                    username=user["username"], amount=amount, total=total
                ),
                notify_id=batch_id,
                type="info",
                params={
                    "hide": False,
                    "delay": 1000,
                    "icon": "user-plus",
                },
            )
        notify_admin(
            payload["user_id"],
            "",
            "",
            notify_id=batch_id,
            params={"delete": True},
        )

        # Always persist the rows that passed validation — earlier behavior
        # silently discarded the entire batch when any single row errored.
        if new_users:
            cls.bulk_create(new_users)

        if errors:
            notify_admin(
                payload["user_id"],
                title=f"There were {len(errors)} errors",
                description=f"{len(new_users)} users created, {len(errors)} errors",
                type="error",
            )
            for err in errors:
                notify_admin(
                    payload["user_id"],
                    title=("Error creating user"),
                    description=err,
                    type="error",
                    params={"hide": False, "icon": "user-times"},
                )
        else:
            notify_admin(
                payload["user_id"],
                title="Bulk user creation",
                description=f"{len(new_users)} users created",
                type="success",
            )

        return {"users": new_users, "errors": errors}

    @classmethod
    def bulk_user_check(cls, payload, user, item_type):
        """_From api/libv2/api_users.py ApiUsers.bulk_user_check()_"""
        if item_type == "csv":
            user = UserFromCSV(**user).model_dump()
        elif item_type == "generate":
            pass
        else:
            raise Error(
                "bad_request",
                f"Item type {item_type} not allowed",
                description_code="item_type_not_allowed",
            )

        user["username"] = user["username"].replace(" ", "")

        match = Helpers.category_name_group_name_match(user["category"], user["group"])
        user["category_id"] = match["category_id"]
        user["group_id"] = match["group_id"]

        Helpers.owns_category_id(payload, user["category_id"])

        user_id = cls.get_by_provider_category_uid(
            "local", user["category_id"], user["username"]
        )
        if user_id:
            raise Error(
                "bad_request",
                "User already exists",
                description_code="user_already_exists",
            )

        # Check if the role is valid
        if payload["role_id"] == "manager":
            if user["role"] not in ["manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    "Role not in manager, advanced or user",
                    description_code="role_not_allowed",
                )
        else:
            if user["role"] not in ["admin", "manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    "Role not in admin, manager, advanced or user",
                    description_code="role_not_allowed",
                )

        # p = Password()
        if item_type == "csv":
            policy = UserPolicies.get_user_policy(
                "password", user["category_id"], user["role"], "local"
            )
            user["password"] = Password.generate_password(policy)
        elif item_type == "generate":
            policy = UserPolicies.get_user_policy(
                "password", match["category_id"], user["role"], "local"
            )
            if policy:
                Password.check_policy(
                    user["password"], policy, username=user["username"]
                )

        return user

    @classmethod
    def get_by_provider_category_uid(cls, provider, category, uid):
        """_From api/libv2/api_users.py ApiUsers.GetByProviderCategoryUID()_"""
        with cls._rdb_context():
            user = list(
                r.table("users")
                .get_all([uid, category, provider], index="uid_category_provider")
                .without("password")
                .run(cls._rdb_connection)
            )
        return user

    @classmethod
    def is_blocked_migration(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.is_blocked_migration()_"""
        user = Caches.get_document("users", user_id)
        user_migration_forced = (
            Caches.get_config()["auth"][user["provider"]]
            .get("migration", {})
            .get("force_migration", False)
        )
        if user_migration_forced:
            exceptions = Caches.get_cached_users_migrations_exceptions()
            if user["category"] in exceptions["categories"]:
                return False
            if user["role"] in exceptions["roles"]:
                return False
            if user["group"] in exceptions["groups"]:
                return False
            if user_id in exceptions["users"]:
                return False
            return True
        return False

    @classmethod
    @cached(
        cache=SynchronizedTTLCache(maxsize=600, ttl=60),
        key=lambda cls, payload: payload["user_id"],
    )
    def user_config(cls, payload):
        """_From api/libv2/api_users.py ApiUsers.Config()_"""
        show_bookings_button = (
            True
            if payload["role_id"] == "admin"
            or getenv("FRONTEND_SHOW_BOOKINGS") == "True"
            else False
        )
        # Admins always see the GPU planner; a manager sees it only when their
        # category has the 'plannings' manager permission (matches the
        # can_manage_gpu_plannings API gate). Regular users never see it. (!4546)
        show_gpu_plannings = payload["role_id"] == "admin"
        if not show_gpu_plannings and payload["role_id"] == "manager":
            show_gpu_plannings = bool(
                (Category(payload["category_id"]).manager_permissions or {}).get(
                    "plannings"
                )
            )
        frontend_show_temporal_tab = (
            True
            if getenv("FRONTEND_SHOW_TEMPORAL") is None
            else getenv("FRONTEND_SHOW_TEMPORAL") == "True"
        )
        frontend_show_change_email = Configuration().smtp.get("enabled")
        if payload.get("provider", "local") in ["saml", "ldap"]:
            env_var = f"AUTHENTICATION_AUTHENTICATION_{payload['provider'].upper()}_SAVE_EMAIL"
            if os.environ.get(env_var, "").lower() == "true":
                frontend_show_change_email = False

        UserStorage.isard_user_storage_update_user_quota(payload["user_id"])
        if Helpers.can_use_bastion(payload):
            bastion_allowed = True
            bastion_domain = Bastion.get_bastion_domain(payload["category_id"])
        else:
            bastion_allowed = False
            bastion_domain = None
        # If the session id is isard-service it means that it's an impersonated user
        if payload.get("session_id") in ["isardvdi-service", "api-key"]:
            session = {
                "id": "isardvdi-service",
                "max_renew_time": 0,
                "max_time": 0,
            }
        else:
            user_session = get_user_session_id(payload["user_id"])
            session = {
                "id": user_session.id,
                "max_renew_time": user_session.time.max_renew_time.ToSeconds(),
                "max_time": user_session.time.max_time.ToSeconds(),
            }

        frontend_mode_raw = getenv("FRONTEND_MODE", "deprecated")
        frontend_mode = (
            frontend_mode_raw
            if frontend_mode_raw in ("deprecated", "actual", "all", "hidden")
            else "deprecated"
        )

        faro_enabled = getenv("FARO_ENABLED", "false").lower() == "true"
        faro = {
            "enabled": faro_enabled,
            "url": (getenv("FARO_URL") or "/faro/collect") if faro_enabled else None,
        }

        return {
            **{
                "show_bookings_button": show_bookings_button,
                "show_gpu_plannings": show_gpu_plannings,
                "documentation_url": getenv(
                    "FRONTEND_DOCS_URI", "https://isard.gitlab.io/isardvdi-docs/"
                ),
                "viewers_documentation_url": getenv(
                    "FRONTEND_VIEWERS_DOCS_URI",
                    "https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/",
                ),
                "show_change_email_button": frontend_show_change_email,
                "show_temporal_tab": frontend_show_temporal_tab,
                "http_port": getenv("HTTP_PORT", "80"),
                "https_port": getenv("HTTPS_PORT", "443"),
                "bastion_domain": bastion_domain,
                "bastion_ssh_port": (
                    getenv(
                        "BASTION_SSH_PORT",
                        getenv("HTTPS_PORT", "443"),
                    )
                    if bastion_allowed
                    else None
                ),
                "can_use_bastion": bastion_allowed,
                "can_use_bastion_individual_domains": Helpers.can_use_bastion_individual_domains(
                    payload
                ),
                "migrations_block": cls.is_blocked_migration(payload["user_id"]),
                "session": session,
                "category_custom_url": CategoriesProcessed.get_custom_login_url(
                    payload["category_id"]
                ),
                "frontend_mode": frontend_mode,
                "faro": faro,
            },
        }

    @classmethod
    def get_user(cls, user_id, get_quota=False):
        """_From api/libv2/api_users.py ApiUsers.Get()_"""
        user = Caches.get_cached_user_with_names(user_id)
        if user is None:
            raise Error(
                "not_found",
                "Not found user_id " + user_id,
                traceback.format_exc(),
            )
        if get_quota:
            user = {**user, **Quotas.Get(user_id)}
        return user

    @classmethod
    def admin_list_users(cls, nav, category_id=None):
        # Bug 43: the ``users`` table can carry orphan rows that only
        # have ``id`` (+ stranded ``vpn`` config) — typically a user
        # whose document was deleted but whose wireguard peer config
        # was not. The merge below dereferences ``user["group"]`` /
        # ``user["role"]`` / ``user["category"]`` directly; on an
        # orphan row each access raises ``ReqlNonExistenceError`` and
        # the route's ``except Exception`` 500s the entire admin user
        # list. Wrap each field access in ``.default(None)`` so the
        # orphan row surfaces with empty cells instead of breaking the
        # endpoint — same philosophy as the Bug 44 schema relax,
        # applied at the ReQL layer because this code path doesn't
        # round-trip through ``AdminUser``.
        query = r.table("users")
        if category_id:
            query = query.get_all(category_id, index="category")

        query = query.pluck(
            "id",
            "active",
            "name",
            "provider",
            "category",
            "uid",
            "username",
            "role",
            "group",
            "secondary_groups",
            "email",
            "accessed",
            "email_verified",
            "disclaimer_acknowledged",
            {"vpn": {"wireguard": {"connected": True}}},
            {"user_storage": {"provider_quota": {"used": True, "relative": True}}},
        )
        if nav == "management":
            query = query.merge(
                lambda user: {
                    "group_name": r.table("groups")
                    .get(user["group"].default(None))["name"]
                    .default(None),
                    "role_name": r.table("roles")
                    .get(user["role"].default(None))["name"]
                    .default(None),
                    "category_name": r.table("categories")
                    .get(user["category"].default(None))["name"]
                    .default(None),
                    # Older user docs created before ``secondary_groups``
                    # was added to the schema lack the field; default to
                    # an empty list so the merge doesn't blow up.
                    "secondary_groups_names": r.table("groups")
                    .get_all(r.args(user["secondary_groups"].default([])))["name"]
                    .coerce_to("array"),
                }
            )
        if nav == "quotas_limits":
            query = query.pluck(
                "id",
                "name",
                "username",
                "role",
                "category",
                "group",
                {"user_storage": {"provider_quota": {"used": True, "relative": True}}},
            ).merge(
                lambda user: {
                    "group_name": r.table("groups")
                    .get(user["group"].default(None))["name"]
                    .default(None),
                    "role_name": r.table("roles")
                    .get(user["role"].default(None))["name"]
                    .default(None),
                    "category_name": r.table("categories")
                    .get(user["category"].default(None))["name"]
                    .default(None),
                    "volatile": r.table("domains")
                    .get_all(["desktop", user["id"]], index="kind_user")
                    .filter({"persistent": False})
                    .pluck("id")
                    .count(),
                    "desktops": r.table("domains")
                    .get_all(["desktop", user["id"], False], index="kind_user_tag")
                    .filter({"persistent": True})
                    .pluck("id")
                    .count(),
                    "templates": r.table("domains")
                    .get_all(["template", user["id"]], index="kind_user")
                    .pluck("id")
                    .count(),
                    "media_size": (
                        r.table("media")
                        .get_all(user["id"], index="user")
                        .pluck({"progress": "total_bytes"})
                        .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    )
                    / 1073741824,
                    "domains_size": (
                        r.table("storage")
                        .get_all([user["id"], "ready"], index="user_status")
                        .pluck({"qemu-img-info": "actual-size"})
                        .sum(
                            lambda size: size["qemu-img-info"]["actual-size"].default(0)
                        )
                    )
                    / 1073741824,
                }
            )
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def categories_get(cls):
        with cls._rdb_context():
            return list(
                r.table("categories")
                .pluck("id", "name", "frontend")
                .order_by("name")
                .run(cls._rdb_connection)
            )

    @classmethod
    def admin_list_categories(cls, nav, category_id=False):
        query = []
        if nav == "management":
            if category_id:
                query = (
                    r.table("categories")
                    .get_all(category_id)
                    .without("quota", "limits")
                )
            else:
                query = r.table("categories").without("quota", "limits")

        elif nav == "quotas_limits":
            if category_id:
                query = (
                    r.table("categories")
                    .get_all(category_id)
                    .merge(
                        {
                            "media_size": (
                                r.table("media")
                                .get_all(category_id, index="category")
                                .pluck({"progress": "total_bytes"})
                                .sum(
                                    lambda size: size["progress"][
                                        "total_bytes"
                                    ].default(0)
                                )
                            )
                            / 1073741824,
                            "domains_size": (
                                r.table("users")
                                .get_all(category_id, index="category")
                                .pluck("id")
                                .merge(
                                    lambda user: {
                                        "storage": r.table("storage")
                                        .get_all(
                                            [user["id"], "ready"],
                                            index="user_status",
                                        )
                                        .pluck({"qemu-img-info": "actual-size"})
                                        .sum(
                                            lambda right: right["qemu-img-info"][
                                                "actual-size"
                                            ].default(0)
                                        ),
                                    }
                                )
                                .sum("storage")
                            )
                            / 1073741824,
                        }
                    )
                )

            else:
                query = r.table("categories").merge(
                    lambda category: {
                        "media_size": (
                            r.table("media")
                            .get_all(category["id"], index="category")
                            .pluck({"progress": "total_bytes"})
                            .sum(
                                lambda size: size["progress"]["total_bytes"].default(0)
                            )
                        )
                        / 1073741824,
                        "domains_size": (
                            r.table("users")
                            .get_all(category["id"], index="category")
                            .pluck("id")
                            .merge(
                                lambda user: {
                                    "storage": r.table("storage")
                                    .get_all(
                                        [user["id"], "ready"],
                                        index="user_status",
                                    )
                                    .pluck({"qemu-img-info": "actual-size"})
                                    .sum(
                                        lambda right: right["qemu-img-info"][
                                            "actual-size"
                                        ].default(0)
                                    ),
                                }
                            )
                            .sum("storage")
                        )
                        / 1073741824,
                    }
                )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def admin_list_groups(cls, nav, category_id=False):
        query = []
        if nav == "management":
            if category_id:
                query = (
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .without("quota", "limits")
                    .merge(
                        lambda group: {
                            "linked_groups_data": r.table("groups")
                            .get_all(r.args(group["linked_groups"].default([])))
                            .merge(
                                lambda g: {
                                    "category_name": r.table("categories")
                                    .get(g["parent_category"])
                                    .default({"name": "[deleted]"})["name"]
                                }
                            )
                            .pluck("id", "name", "category_name")
                            .coerce_to("array")
                        }
                    )
                )

            else:
                query = (
                    r.table("groups")
                    .without("quota", "limits")
                    .merge(
                        lambda group: {
                            "linked_groups_data": r.table("groups")
                            .get_all(r.args(group["linked_groups"].default([])))
                            .merge(
                                lambda g: {
                                    "category_name": r.table("categories")
                                    .get(g["parent_category"])
                                    .default({"name": "[deleted]"})["name"]
                                }
                            )
                            .pluck("id", "name", "category_name")
                            .coerce_to("array"),
                            "parent_category_name": r.table("categories")
                            .get(group["parent_category"])
                            .default({"name": "[deleted]"})["name"],
                        }
                    )
                )

        elif nav == "quotas_limits":
            if category_id:
                query = (
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .merge(
                        lambda group: {
                            "linked_groups_data": r.table("groups")
                            .get_all(r.args(group["linked_groups"].default([])))
                            .pluck("id", "name")
                            .coerce_to("array"),
                            "media_size": (
                                r.table("media")
                                .get_all(group["id"], index="group")
                                .pluck({"progress": "total_bytes"})
                                .sum(
                                    lambda size: size["progress"][
                                        "total_bytes"
                                    ].default(0)
                                )
                            )
                            / 1073741824,
                            "domains_size": (
                                r.table("users")
                                .get_all(group["id"], index="group")
                                .pluck("id")
                                .merge(
                                    lambda user: {
                                        "storage": r.table("storage")
                                        .get_all(
                                            [user["id"], "ready"], index="user_status"
                                        )
                                        .pluck({"qemu-img-info": "actual-size"})
                                        .sum(
                                            lambda right: right["qemu-img-info"][
                                                "actual-size"
                                            ].default(0)
                                        ),
                                    }
                                )
                                .sum("storage")
                            )
                            / 1073741824,
                        }
                    )
                    .without(
                        "enrollment", "external_app_id", "external_gid", "linked_groups"
                    )
                )
            else:
                query = (
                    r.table("groups")
                    .merge(
                        lambda group: {
                            "linked_groups_data": r.table("groups")
                            .get_all(r.args(group["linked_groups"].default([])))
                            .pluck("id", "name")
                            .coerce_to("array"),
                            "parent_category_name": r.table("categories")
                            .get(group["parent_category"])
                            .default({"name": "[deleted]"})["name"],
                            "media_size": (
                                r.table("media")
                                .get_all(group["id"], index="group")
                                .pluck({"progress": "total_bytes"})
                                .sum(
                                    lambda size: size["progress"][
                                        "total_bytes"
                                    ].default(0)
                                )
                            )
                            / 1073741824,
                            "domains_size": (
                                r.table("users")
                                .get_all(group["id"], index="group")
                                .pluck("id")
                                .merge(
                                    lambda user: {
                                        "storage": r.table("storage")
                                        .get_all(
                                            [user["id"], "ready"], index="user_status"
                                        )
                                        .pluck({"qemu-img-info": "actual-size"})
                                        .sum(
                                            lambda right: right["qemu-img-info"][
                                                "actual-size"
                                            ].default(0)
                                        ),
                                    }
                                )
                                .sum("storage")
                            )
                            / 1073741824,
                        }
                    )
                    .without(
                        "enrollment", "external_app_id", "external_gid", "linked_groups"
                    )
                )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def change_password(cls, password, user_id):
        """_From api/libv2/api_users.py ApiUsers.change_password()_"""
        # Log user password changes with relevant metadata for auditing purposes.
        logger.info(
            "password_mutation",
            extra={
                "audit_event": "users.password.changed",
                "target_user_id": user_id,
                "ts": int(time.time()),
            },
        )

        with cls._rdb_context():
            raw = r.table("users").get(user_id).default(None).run(cls._rdb_connection)
        if raw is None:
            raise Error(
                "not_found",
                f"User {user_id} not found",
                description_code="user_not_found",
            )
        user = {
            "category": raw.get("category"),
            "role": raw.get("role"),
            "password_history": raw.get("password_history", []),
            "provider": raw.get("provider"),
        }

        # p = Password()
        policy = UserPolicies.get_user_policy(
            "password", user["category"], user["role"], user["provider"]
        )

        if policy:
            Password.check_policy(password, policy, user_id)
        password = Password.encrypt(password)

        if policy["old_passwords"] == 0:
            password_history = []
        else:
            password_history = user["password_history"]
            password_history.append(password)
            password_history = password_history[-policy["old_passwords"] :]

        with cls._rdb_context():
            # TODO: pydantic
            r.table("users").get(user_id).update(
                {
                    "password_history": password_history,
                    "password_last_updated": int(time.time()),
                    "password": password,
                }
            ).run(cls._rdb_connection)

    @classmethod
    def change_user_group(cls, user_id, group_id):
        """_From api/libv2/api_users.py ApiUsers.change_user_group()_"""
        user_gen_payload = Helpers.gen_payload_from_user(user_id, invalidate_cache=True)
        user_gen_payload["group_id"] = group_id

        # change provider to local if it's an external user
        if user_gen_payload["provider"].startswith("external_"):
            with cls._rdb_context():
                r.table("users").get(user_id).update({"provider": "local"}).run(
                    cls._rdb_connection
                )

        with cls._rdb_context():
            user_domains = list(
                r.table("domains")
                .get_all(user_id, index="user")
                .pluck("id", "create_dict", "kind")
                .run(cls._rdb_connection)
            )
        desktops_ids = list(
            map(
                lambda d: d["id"],
                filter(lambda d: (d["kind"] == "desktop"), user_domains),
            )
        )

        # Stop user desktops
        try:
            DesktopEvents.desktops_stop(desktops_ids, force=True)
        except Exception:
            raise Error(
                "internal_server",
                "Unable to stop desktops when changing the user group",
                traceback.format_exc(),
                description_code="generic_error",
            )

        ## Empty Recycle Bin
        try:
            rb_ids = RecycleBinHelpers.get_user_recycle_bin_ids(user_id, "recycled")
            for rb_id in rb_ids:
                RecycleBinDeleteQueue().enqueue_sync(
                    {
                        "action": "delete",
                        "recycle_bin_id": rb_id,
                        "user_id": user_id,
                    }
                )
        except Exception:
            raise Error(
                "internal_server",
                "Unable to empty recycle bin when changing the user group",
                traceback.format_exc(),
                description_code="generic_error",
            )

        ## Change the domains group and limit their hardware considering the new group permissions
        try:
            for domain in user_domains:
                Helpers.revoke_hardware_permissions(domain, user_gen_payload)
                with cls._rdb_context():
                    r.table("domains").get(domain["id"]).update(
                        {
                            "create_dict": domain["create_dict"],
                            "reservables": domain.get("reservables"),
                            "group": group_id,
                        }
                    ).run(cls._rdb_connection)
        except Exception:
            raise Error(
                "internal_server",
                "Unable to limit user hardware allowed when changing the users domains group",
                traceback.format_exc(),
                description_code="generic_error",
            )

        if user_gen_payload["role_id"] != "user":
            # Change media group
            with cls._rdb_context():
                r.table("media").get_all(user_id, index="user").update(
                    {"group": group_id}
                ).run(cls._rdb_connection)

            # Check hardware allowed for deployments and deployment desktops
            # Note: There's no need to update the group in the deployments table
            try:
                with cls._rdb_context():
                    deployments = list(
                        r.table("deployments")
                        .get_all(user_id, index="user")
                        .pluck("id", "create_dict")
                        .run(cls._rdb_connection)
                    )
            except Exception:
                raise Error(
                    "internal_server",
                    "Unable to get deployments when changing the users group",
                    traceback.format_exc(),
                    description_code="generic_error",
                )

            # TODO: Test when changing to apiv4 since deployments in apiv4 are different
            for deployment in deployments:
                new_create_dict = []
                for create_dict in deployment["create_dict"]:
                    Helpers.revoke_hardware_permissions(
                        {"create_dict": create_dict}, user_gen_payload
                    )
                    new_create_dict.append(create_dict)
                    allowed_interfaces = create_dict["hardware"]["interfaces"]
                    with cls._rdb_context():
                        r.table("domains").get_all(
                            create_dict["tag_desktop_id"], index="tag_desktop_id"
                        ).update(
                            lambda desktop: {
                                "create_dict": {
                                    "hardware": {
                                        "interfaces": desktop["create_dict"][
                                            "hardware"
                                        ]["interfaces"].filter(
                                            lambda interface: r.expr(
                                                allowed_interfaces
                                            ).contains(interface["id"])
                                        ),
                                        "boot_order": create_dict["hardware"][
                                            "boot_order"
                                        ],
                                        "disk_bus": create_dict["hardware"]["disk_bus"],
                                        "floppies": create_dict["hardware"]["floppies"],
                                        "isos": create_dict["hardware"]["isos"],
                                        "memory": create_dict["hardware"]["memory"],
                                        "vcpus": create_dict["hardware"]["vcpus"],
                                        "videos": create_dict["hardware"]["videos"],
                                    },
                                    "reservables": create_dict["reservables"],
                                }
                            }
                        ).run(
                            cls._rdb_connection
                        )

                with cls._rdb_context():
                    r.table("deployments").get(deployment["id"]).update(
                        {"create_dict": new_create_dict}
                    ).run(cls._rdb_connection)

                # Limit deployment desktops hardware
                allowed_interfaces = new_create_dict["hardware"]["interfaces"]
                with cls._rdb_context():
                    r.table("domains").get_all(deployment["id"], index="tag").update(
                        lambda desktop: {
                            "create_dict": {
                                "hardware": {
                                    "interfaces": desktop["create_dict"]["hardware"][
                                        "interfaces"
                                    ].filter(
                                        lambda interface: r.expr(
                                            allowed_interfaces
                                        ).contains(interface["id"])
                                    ),
                                    "boot_order": new_create_dict["hardware"][
                                        "boot_order"
                                    ],
                                    "disk_bus": new_create_dict["hardware"]["disk_bus"],
                                    "floppies": new_create_dict["hardware"]["floppies"],
                                    "isos": new_create_dict["hardware"]["isos"],
                                    "memory": new_create_dict["hardware"]["memory"],
                                    "vcpus": new_create_dict["hardware"]["vcpus"],
                                    "videos": new_create_dict["hardware"]["videos"],
                                },
                                "reservables": new_create_dict["reservables"],
                            }
                        }
                    ).run(cls._rdb_connection)

    # ``update_multiple_users_th`` was a fire-and-forget gevent.spawn
    # wrapper around ``update_multiple_users``. Under apiv4's asyncio
    # worker the spawned greenlet sat on a libev Hub the loop never
    # drives, so the bulk update silently never ran. Apiv4 callers now
    # schedule ``update_multiple_users`` directly via FastAPI's
    # ``BackgroundTasks``. See APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.

    @classmethod
    def update_multiple_users(cls, user_ids, data, batch_id=None, payload=None):
        """_From api/libv2/api_users.py ApiUsers.update_multiple_users()_"""
        total = len(user_ids)
        amount = 0
        if not batch_id:
            batch_id = str(uuid.uuid4())

        if (
            "local-default-admin-admin" in user_ids
            and data.get("group") != "default-default"
        ):
            raise Error(
                "forbidden",
                "User local-default-admin-admin can not be moved to another group",
                traceback.format_exc(),
            )

        for user_id in user_ids:
            revoke_user_session(user_id)

        if data.get("password"):
            for user_id in user_ids:
                cls.change_password(data["password"], user_id)
            data.pop("password")
        if data.get("ids"):
            data.pop("ids")

        with cls._rdb_context():
            users = (
                r.table("users")
                .get_all(r.args(user_ids))
                .pluck("id", "category", "group", "uid", "provider")
                .run(cls._rdb_connection)
            )

        for user in users:
            if (
                data.get("email")
                and not data.get("email_verified")
                and Configuration().smtp.get("enabled")
                and data["email"] != user["email"]
            ):
                should_verify_email = True

                # Check if SAML/LDAP user with auto-save email enabled
                if user["provider"] in ["saml", "ldap"]:
                    env_var = f"AUTHENTICATION_AUTHENTICATION_{user['provider'].upper()}_SAVE_EMAIL"
                    if os.environ.get(env_var, "").lower() == "true":
                        should_verify_email = False

                if should_verify_email:
                    if UserPolicies.get_user_policy(
                        "email_verification",
                        user["category"],
                        user["role"],
                        user["provider"],
                    ):

                        token = cls.gen_validate_email_jwt(user["id"], data["email"])[
                            "jwt"
                        ]
                        with cls._rdb_context():
                            r.table("users").get(user["id"]).update(
                                {
                                    "email_verification_token": token,
                                    "email_verified": False,
                                }
                            ).run(cls._rdb_connection)
                        send_verification_email(data["email"], user["id"], token)
                    else:
                        with cls._rdb_context():
                            r.table("users").get(user["id"]).update(
                                {
                                    "email_verification_token": None,
                                    "email_verified": False,
                                }
                            ).run(cls._rdb_connection)

            if data.get("email_verified") == True:
                data["email_verified"] = int(time.time())

            if data.get("category") and user["category"] != data["category"]:
                raise Error(
                    "bad_request",
                    "Category can not be changed",
                    traceback.format_exc(),
                )

            if data.get("group") and user["group"] != data["group"]:
                group = Caches.get_document("groups", data["group"])
                if group["parent_category"] != user["category"]:
                    raise Error(
                        "bad_request",
                        f"Group {data['group']} does not belong to category {user['category']}",
                        traceback.format_exc(),
                    )
                data["quota"] = False
            if payload:
                amount += 1
                notify_admin(
                    payload["user_id"],
                    "User validated",
                    f"User '{user['uid']}' data validated \n{amount}/{total}",
                    notify_id=batch_id,
                    type="info",
                    params={
                        "hide": False,
                        "delay": 1000,
                        "icon": "check",
                    },
                )

        if data.get("active") is False:
            for user_id in user_ids:
                Helpers.unassign_item_from_resource(user_id, "users", "deployments")

        Caches.invalidate_caches("users", user_ids)

        if payload:
            amount = 0
            notify_admin(
                payload["user_id"],
                False,
                f"Updating {total} users...",
                notify_id=batch_id,
                type="",
                params={
                    "hide": False,
                    "delay": 1000,
                    "icon": "spinner fa-spin",
                },
            )
        with cls._rdb_context():
            # TODO(move-users-to-common): pydantic
            r.table("users").get_all(r.args(user_ids)).update(data).run(
                cls._rdb_connection
            )
        for user_id in user_ids:
            UserStorage.isard_user_storage_update_user(
                user_id=user_id,
                email=data.get("email"),
                displayname=data.get("name"),
                role=data.get("role"),
                enabled=data.get("active"),
            )

            if data.get("group") and user["group"] != data["group"]:
                cls.change_user_group(
                    user_id,
                    data["group"],
                )

            if payload:
                amount += 1
                notify_admin(
                    payload["user_id"],
                    "User updated",
                    f"{amount}/{total} updated",
                    notify_id=batch_id,
                    type="info",
                    params={
                        "hide": False,
                        "delay": 1000,
                        "icon": "user-plus",
                    },
                )

            # second revoke to ensure changes are applied if the user logs in again during the update
            revoke_user_session(user_id)

        if payload:
            notify_admin(
                payload["user_id"],
                title="Bulk user update",
                description=f"{len(user_ids)} users updated",
                type="success",
                notify_id=batch_id,
                params={"hide": True},
            )

    @classmethod
    def update_user(cls, user_id, data, revoke=True, force_email_verification=False):
        """_From api/libv2/api_users.py ApiUsers.update_user()_"""
        if (
            data.get("group")
            and user_id == "local-default-admin-admin"
            and data["group"] != "default-default"
        ):
            raise Error(
                "forbidden",
                "User local-default-admin-admin can not be moved to another group",
                traceback.format_exc(),
            )

        if revoke:
            revoke_user_session(user_id)

        if data.get("password"):
            cls.change_password(data["password"], user_id)
            data.pop("password")

        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck(
                    "id",
                    "email",
                    "category",
                    "role",
                    "email_verified",
                    "group",
                    "provider",
                )
                .run(cls._rdb_connection)
            )

        if (
            data.get("email")
            and not data.get("email_verified")
            and Configuration().smtp.get("enabled")
            and (force_email_verification or data["email"] != user["email"])
        ):
            should_verify_email = True

            # Check if SAML/LDAP user with auto-save email enabled
            if user["provider"] in ["saml", "ldap"]:
                env_var = f"AUTHENTICATION_AUTHENTICATION_{user['provider'].upper()}_SAVE_EMAIL"
                if os.environ.get(env_var, "").lower() == "true":
                    should_verify_email = False

            if should_verify_email:
                if UserPolicies.get_user_policy(
                    "email_verification",
                    user["category"],
                    user["role"],
                    user["provider"],
                ):
                    token = cls.gen_validate_email_jwt(user["id"], data["email"])["jwt"]
                    data.update(
                        {
                            "email_verification_token": token,
                            "email_verified": False,
                        }
                    )
                    send_verification_email(data["email"], user["id"], token)
                else:
                    data.update(
                        {
                            "email_verification_token": None,
                            "email_verified": False,
                        }
                    )

        if data.get("category") and user["category"] != data["category"]:
            raise Error(
                "bad_request",
                "Category can not be changed",
                traceback.format_exc(),
            )

        if data.get("group") and user["group"] != data["group"]:
            group = Caches.get_document("groups", data["group"])
            if group["parent_category"] != user["category"]:
                raise Error(
                    "bad_request",
                    f"Group {data['group']} does not belong to category {user['category']}",
                    traceback.format_exc(),
                )
            data["quota"] = False

            cls.change_user_group(
                user["id"],
                data["group"],
            )

        with cls._rdb_context():
            # TODO(move-users-to-common): pydantic validation
            r.table("users").get(user_id).update(data).run(cls._rdb_connection)
        Caches.invalidate_cache("users", user_id)
        UserStorage.isard_user_storage_update_user(
            user_id=user_id,
            email=data.get("email"),
            displayname=data.get("name"),
            role=data.get("role"),
            enabled=data.get("active"),
        )

        if data.get("group") and user["group"] != data["group"]:
            cls.change_user_group(
                user["id"],
                data["group"],
            )
        # second revoke to ensure changes are applied if the user logs in again during the update
        if revoke:
            revoke_user_session(user_id)

    @classmethod
    def delete_user(cls, user_id, agent_id, delete_user):
        """_From api/libv2/api_users.py ApiUsers.Delete()_"""
        cls.get_user(user_id)

        with cls._rdb_context():
            user_media_ids = (
                r.table("media")
                .get_all(user_id, index="user")["id"]
                .run(cls._rdb_connection)
            )
        Helpers.change_owner_medias(
            user_media_ids, Helpers.get_new_user_data("local-default-admin-admin")
        )

        DesktopEvents.user_delete(agent_id, user_id, delete_user)

    @classmethod
    def user_delete_checks(cls, item_ids, table):
        """_From api/libv2/api_users.py ApiUsers._delete_checks()_"""
        users = []
        groups = []
        desktops = []
        templates = []
        deployments = []
        media = []
        tags = []
        if table == "user":
            with cls._rdb_context():
                users = list(
                    r.table("users")
                    .get_all(r.args(item_ids))
                    .pluck("id", "name", "username", "provider")
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                deployments = list(
                    r.table("deployments")
                    .get_all(r.args(item_ids), index="user")
                    .pluck("id", "name", "user")
                    .merge(
                        lambda row: {
                            "user_name": r.table("users").get(row["user"])["name"],
                            "username": r.table("users").get(row["user"])["username"],
                        }
                    )
                    .run(cls._rdb_connection)
                )
            tags = [deployment["id"] for deployment in deployments]
            with cls._rdb_context():
                desktops = desktops + list(
                    r.table("domains")
                    .get_all(r.args(tags), index="tag")
                    .pluck(
                        "id",
                        "name",
                        "kind",
                        "user",
                        "status",
                        "parents",
                        "persistent",
                        "duplicate_parent_template",
                    )
                    .merge(
                        lambda d: {
                            "username": r.table("users").get(d["user"])["username"],
                            "user_name": r.table("users").get(d["user"])["name"],
                        }
                    )
                    .run(cls._rdb_connection)
                )
        elif table in ["category", "group"]:
            with cls._rdb_context():
                users = list(
                    r.table("users")
                    .get_all(r.args(item_ids), index=table)
                    .pluck("id", "name", "username")
                    .run(cls._rdb_connection)
                )
            users_ids = [user["id"] for user in users]
            with cls._rdb_context():
                deployments = list(
                    r.table("deployments")
                    .get_all(r.args(users_ids), index="user")
                    .pluck("id", "name", "user")
                    .merge(
                        lambda row: {
                            "user_name": r.table("users").get(row["user"])["name"],
                            "username": r.table("users").get(row["user"])["username"],
                        }
                    )
                    .run(cls._rdb_connection)
                )
            tags = [deployment["id"] for deployment in deployments]
            with cls._rdb_context():
                desktops = desktops + list(
                    r.table("domains")
                    .get_all(r.args(tags), index="tag")
                    .pluck("id", "name", "kind", "user", "status", "parents")
                    .merge(
                        lambda d: {
                            "username": r.table("users").get(d["user"])["username"],
                            "user_name": r.table("users").get(d["user"])["name"],
                        }
                    )
                    .run(cls._rdb_connection)
                )
            if table == "category":
                with cls._rdb_context():
                    groups = list(
                        r.table("groups")
                        .get_all(r.args(item_ids), index="parent_category")
                        .pluck("id", "name")
                        .run(cls._rdb_connection)
                    )
            else:
                with cls._rdb_context():
                    groups = list(
                        r.table("groups")
                        .get_all(r.args(item_ids))
                        .pluck("id", "name")
                        .run(cls._rdb_connection)
                    )
        with cls._rdb_context():
            desktops = desktops + list(
                r.table("domains")
                .get_all(r.args(item_ids), index=table)
                .filter({"kind": "desktop"})
                .pluck("id", "name", "kind", "user", "status", "parents", "persistent")
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = list(
                r.table("domains")
                .get_all(r.args(item_ids), index=table)
                .filter({"kind": "template"})
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "user",
                    "category",
                    "group",
                    "duplicate_parent_template",
                )
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )
        domains_derivated = []
        for template in templates:
            domains_derivated = (
                domains_derivated
                + Helpers.get_template_with_all_derivatives(template["id"])
            )
        desktops = desktops + list(
            filter(lambda d: d["kind"] == "desktop", domains_derivated)
        )
        desktops = list({v["id"]: v for v in desktops}.values())
        templates = templates + list(
            filter(lambda d: d["kind"] == "template", domains_derivated)
        )
        templates = list({v["id"]: v for v in templates}.values())

        with cls._rdb_context():
            media = list(
                r.table("media")
                .get_all(r.args(item_ids), index=table)
                .pluck("id", "name", "user")
                .merge(
                    lambda row: {
                        "user_name": r.table("users").get(row["user"])["name"],
                        "username": r.table("users").get(row["user"])["username"],
                    }
                )
                .run(cls._rdb_connection)
            )
        if table == "category":
            with cls._rdb_context():
                storage_pools = (
                    r.table("storage_pool")["categories"]
                    .filter(lambda pool: pool.contains(r.args(item_ids)))
                    .count()
                    .run(cls._rdb_connection)
                )

            return {
                "desktops": desktops,
                "templates": templates,
                "deployments": deployments,
                "media": media,
                "users": users,
                "groups": groups,
                "storage_pools": storage_pools,
            }

        return {
            "desktops": desktops,
            "templates": templates,
            "deployments": deployments,
            "media": media,
            "users": users,
            "groups": groups,
        }

    @classmethod
    def update_secondary_groups(cls, action, data):
        """_From api/libv2/api_users.py ApiUsers.UpdateSecondaryGroups()_"""
        query = r.table("users").get_all(r.args(data["ids"]))

        if action == "add":
            query = query.update(
                lambda user: {
                    "secondary_groups": user["secondary_groups"].set_union(
                        data["secondary_groups"]
                    )
                }
            )
        elif action == "delete":
            query = query.update(
                lambda user: {
                    "secondary_groups": user["secondary_groups"].difference(
                        data["secondary_groups"]
                    )
                }
            )
        elif action == "overwrite":
            query = query.update({"secondary_groups": data["secondary_groups"]})
        else:
            raise Error("bad_request", "Action: " + action + " not allowed")

        with cls._rdb_context():
            # TODO(move-users-to-common): pydantic validation
            query.run(cls._rdb_connection)

    @classmethod
    def change_user_language(cls, user_id, lang):
        """_From api/libv2/api_users.py ApiUsers.change_user_language()_"""
        with cls._rdb_context():
            r.table("users").get(user_id).update({"lang": lang}).run(
                cls._rdb_connection
            )

    @classmethod
    def get_user_language(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.get_lang()_"""
        with cls._rdb_context():
            return r.table("users").get(user_id).run(cls._rdb_connection).get("lang")

    @classmethod
    def check_password_expiration(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.check_password_expiration()_"""
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("category", "role", "password_last_updated", "provider")
                .run(cls._rdb_connection)
            )
        if user["provider"] != "local":
            return False
        if not user.get("category") or not user.get("role"):
            return False
        policy = UserPolicies.get_user_policy(
            "password", user["category"], user["role"], user["provider"]
        )
        if not policy:
            return False

        if not policy["expiration"] or policy["expiration"] == 0:
            return False
        return (
            True
            if not user.get("password_last_updated")
            else (
                datetime.fromtimestamp(user["password_last_updated"], tz=timezone.utc)
                + timedelta(days=policy["expiration"])
                < datetime.now(timezone.utc)
            )
        )

    @classmethod
    def verify_password(cls, user_id, password):
        """_From api/libv2/api_users.py ApiUsers.verify_password()_"""
        with cls._rdb_context():
            user_password = (
                r.table("users").get(user_id)["password"].run(cls._rdb_connection)
            )
        if not Password.valid(password, user_password):
            raise Error(
                "forbidden",
                "Wrong password entered",
                description_code="wrong_password_entered",
            )
        else:
            return True

    @classmethod
    def check_verified_email(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.check_verified_email()_"""
        if not Configuration().smtp.get("enabled"):
            return True
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("email_verified", "category", "role", "provider")
                .run(cls._rdb_connection)
            )
        if user["provider"] in ["saml", "ldap"]:
            env_var = (
                f'AUTHENTICATION_AUTHENTICATION_{user["provider"].upper()}_SAVE_EMAIL'
            )
            if os.environ.get(env_var, "").lower() == "true":
                return True
        policy = UserPolicies.get_user_policy(
            "email_verification",
            user["category"],
            user["role"],
            provider=user["provider"],
        )
        if not policy:
            return True
        else:
            return user.get("email_verified")

    @classmethod
    def check_acknowledged_disclaimer(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.check_acknowledged_disclaimer()_"""
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck(
                    "role", "category", "provider", "lang", "disclaimer_acknowledged"
                )
                .run(cls._rdb_connection)
            )
        if user.get("disclaimer_acknowledged"):
            return False

        policy = UserPolicies.get_user_policy(
            "disclaimer", "all", user["role"], user["provider"], user_id
        )
        if policy:
            return True
        else:
            return False

    @classmethod
    def get_user_by_email_and_category(cls, email, category):
        """_From api/libv2/api_users.py ApiUsers.get_user_by_email_and_category()_"""
        with cls._rdb_context():
            users = list(
                r.table("users")
                .get_all(category, index="category")
                .filter(
                    lambda user: (user["email"].eq(email))
                    & (user["email_verified"].ne(None))
                )
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )
        if len(users) == 1:
            return users[0]
        if len(users) == 0:
            raise Error(
                "not_found",
                f"No verified user with email {email} in category {category}",
                description_code="user_not_found",
            )
        raise Error(
            "conflict",
            f"Multiple verified users with email {email} in category {category}",
            description_code="user_email_conflict",
        )

    @classmethod
    def get_api_key(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.get_api_key()_"""
        with cls._rdb_context():
            api_key = (
                r.table("users").get(user_id).pluck("api_key").run(cls._rdb_connection)
            )

        api_key = api_key.get("api_key")
        if api_key:
            try:
                return {
                    "exists": True,
                    "expires": int(
                        jwt.decode(
                            api_key,
                            getenv("API_ISARDVDI_SECRET"),
                            algorithms=["HS256"],
                            verify=False,
                            options=dict(
                                verify_aud=False, verify_sub=False, verify_exp=False
                            ),
                        )["exp"]
                    ),
                }
            except Exception as e:
                logger.error(str(e))
                return {
                    "exists": True,
                    "expires": 0,
                }

        return {
            "exists": False,
            "expires": 0,
        }

    @classmethod
    def delete_api_key(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.delete_api_key()_"""
        with cls._rdb_context():
            r.table("users").get(user_id).update({"api_key": None}).run(
                cls._rdb_connection
            )

    @classmethod
    def get_roles(cls, role=None):
        """_From api/libv2/api_users.py ApiUsers.RoleGet()_"""
        if role == "manager":
            with cls._rdb_context():
                return list(
                    r.table("roles")
                    .order_by("sortorder")
                    .pluck("id", "name", "description")
                    .filter(lambda doc: doc["id"] != "admin")
                    .run(cls._rdb_connection)
                )
        else:
            with cls._rdb_context():
                return list(
                    r.table("roles")
                    .order_by("sortorder")
                    .pluck("id", "name", "description")
                    .run(cls._rdb_connection)
                )

    @classmethod
    def get_user_info(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.get_user_info()_"""
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .pluck("name", "email", "role", "photo")
                .merge(
                    {
                        "role_name": r.table("roles")
                        .get(r.row["role"])["name"]
                        .default(""),
                        "items_in_bin": r.table("recycle_bin")
                        .get_all(
                            [user_id, RecycleBinStatusEnum.recycled.value],
                            index="owner_status",
                        )
                        .pluck("id")
                        .count()
                        .default(0),
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_details(cls, user_id):
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .pluck("name", "email", "role", "photo")
                .merge(
                    {
                        "role_name": r.table("roles")
                        .get(r.row["role"])["name"]
                        .default(""),
                        "items_in_bin": r.table("recycle_bin")
                        .get_all(
                            [user_id, RecycleBinStatusEnum.recycled.value],
                            index="owner_status",
                        )
                        .pluck("id")
                        .count()
                        .default(0),
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def reset_vpn(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.reset_vpn()_"""
        with cls._rdb_context():
            r.table("users").get(user_id).update(
                {"vpn": {"wireguard": {"keys": False}}}
            ).run(cls._rdb_connection)
