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

import os
import time
import traceback
import uuid
from datetime import datetime, timedelta

import bcrypt
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.api_exceptions import Error
from rethinkdb.errors import ReqlNonExistenceError

from api import app

from ..libv2.recycle_bin import RecycleBinDeleteQueue
from .api_notify import notify_custom
from .api_sessions import revoke_user_session
from .api_storage import remove_category_from_storage_pool
from .bookings.api_booking import Bookings
from .caches import get_cached_user_with_names, get_document, invalidate_caches
from .recycle_bin import get_user_recycle_bin_ids

apib = Bookings()

from .api_desktop_events import category_delete, group_delete, user_delete
from .quotas import Quotas

quotas = Quotas()


from string import ascii_lowercase, digits

import jwt
from rethinkdb import RethinkDB

from .api_notifier import send_verification_email
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

rb_delete_queue = RecycleBinDeleteQueue()

from ..libv2.api_user_storage import (
    isard_user_storage_add_user,
    isard_user_storage_update_user,
    isard_user_storage_update_user_quota,
    user_storage_quota,
)
from ..views.decorators import (
    CategoryNameGroupNameMatch,
    can_use_bastion,
    ownsCategoryId,
)
from .api_admin import (
    change_category_items_owner,
    change_group_items_owner,
    change_user_items_owner,
    get_user_migration_config,
)
from .api_notify import notify_admin, notify_admins
from .helpers import (
    _check,
    _parse_desktop,
    _random_password,
    change_owner_deployments,
    change_owner_desktops,
    change_owner_medias,
    change_owner_templates,
    gen_payload_from_user,
    get_new_user_data,
    get_template_with_all_derivatives,
    revoke_hardware_permissions,
)
from .validators import _validate_item


@cached(cache=TTLCache(maxsize=300, ttl=10))
def user_exists(user_id):
    with app.app_context():
        try:
            return (
                r.table("users")
                .get(user_id)
                .pluck("id", "username", "name", "category", "group", "active")
                .run(db.conn)
            )
        except r.ReqlNonExistenceError:
            raise Error("not_found", "User not found")


def get_user(user_id):
    return get_document("users", user_id)


@cached(cache=TTLCache(maxsize=100, ttl=10))
def get_group(group_id):
    with app.app_context():
        return r.table("groups").get(group_id).run(db.conn)


@cached(cache=TTLCache(maxsize=100, ttl=10), key=lambda groups: hashkey(str(groups)))
def get_secondary_groups_data(secondary_groups):
    with app.app_context():
        return (
            r.table("groups")
            .get_all(r.args(secondary_groups))
            .pluck("id", "name")
            .coerce_to("array")
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=100, ttl=10))
def get_category(category_id):
    with app.app_context():
        return r.table("categories").get(category_id).run(db.conn)


@cached(cache=TTLCache(maxsize=100, ttl=10))
def get_role(role_id):
    with app.app_context():
        return r.table("roles").get(role_id).run(db.conn)


def get_user_full_data(user_id):
    try:
        user = get_user(user_id)
        user["category_name"] = get_category(user["category"])["name"]
        user["group_name"] = get_group(user["group"])["name"]
        user["secondary_groups_data"] = get_secondary_groups_data(
            user["secondary_groups"]
        )
    except:
        raise Error(
            "not_found",
            "Not found user_id " + user_id,
            traceback.format_exc(),
        )
    return user


def check_category_domain(category_id, domain):
    allowed_domain = get_category(category_id).get("allowed_domain")
    allowed = not allowed_domain or domain == allowed_domain
    if not allowed:
        raise Error(
            "forbidden",
            "Register domain does not match category allowed domain",
            traceback.format_exc(),
        )


def bulk_create(users):
    for i in range(0, len(users), 5000):
        batch_users = users[i : i + 5000]
        with app.app_context():
            r.table("users").insert(batch_users).run(db.conn)
    for user in users:
        isard_user_storage_add_user(user["id"])


class ApiUsers:
    def Jwt(self, user_id, minutes=240):
        return {
            "jwt": jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(minutes=minutes),
                    "kid": "isardvdi",
                    "session_id": "isardvdi-service",  # TODO: Fix
                    "data": gen_payload_from_user(user_id),
                },
                os.environ.get("API_ISARDVDI_SECRET"),
                algorithm="HS256",
            )
        }

    def generate_users(self, payload, data):
        batch_id = str(uuid.uuid4())

        new_users = []
        errors = []

        # TODO: Check in quotas whether can create users
        p = Password()

        amount, total = 0, len(data["users"])
        for user in data["users"]:
            new_user = {}

            try:
                user = self.bulk_user_check(payload, user, "generate")
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
            new_user["password"] = p.encrypt(user["password"])
            new_user["name"] = user["name"]
            new_user["role"] = user["role"]
            new_user["accessed"] = int(time.time())
            new_user["quota"] = False
            new_user["email"] = user.get("email", "")
            # Must be done first to avoid the removal of the following fields
            new_user = _validate_item("user", new_user)
            new_user["password_history"] = [p.encrypt(user["password"])]
            new_user["password_last_updated"] = int(time.time())
            new_user["email_verification_token"] = None
            new_user["email_verified"] = (
                int(time.time()) if data.get("email_verified") else False
            )
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

        if not errors:
            notify_admin(
                payload["user_id"],
                title="Bulk user creation",
                description=f"{len(new_users)} users created",
                type="success",
            )
            bulk_create(new_users)
        else:
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

        return {"users": new_users, "errors": errors}

    # TODO: Fix this!
    def Login(self, user_id, user_passwd, provider="local", category_id="default"):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .default({})
                .pluck(
                    "id",
                    "password",
                    "active",
                    "role",
                    "category",
                    "group",
                    "username",
                    "email",
                    "photo",
                )
                .run(db.conn)
            )
        if user.get("id") == None:
            raise Error("unauthorized", "", traceback.format_exc())
        if not user.get("active", False):
            raise Error(
                "unauthorized",
                "User " + user_id + " is disabled",
                traceback.format_exc(),
            )

        pw = Password()
        if pw.valid(user_passwd, user["password"]):
            logged_user = {
                "user_id": user["id"],
                "role_id": user["role"],
                "category_id": user["category"],
                "group_id": user["group"],
                "username": user["username"],
                "email": user["email"],
                "photo": user["photo"],
            }
            return user_id, jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(hours=4),
                    "kid": "isardvdi",
                    "session_id": "isardvdi-service",
                    "data": logged_user,
                },
                os.environ.get("API_ISARDVDI_SECRET"),
                algorithm="HS256",
            )
        raise Error(
            "unauthorized",
            "Invalid login credentials for user_id " + user_id,
            traceback.format_exc(),
        )

    def Config(self, payload):
        show_bookings_button = (
            True
            if payload["role_id"] == "admin"
            or os.environ.get("FRONTEND_SHOW_BOOKINGS") == "True"
            else False
        )
        frontend_show_temporal_tab = (
            True
            if os.environ.get("FRONTEND_SHOW_TEMPORAL") == None
            else os.environ.get("FRONTEND_SHOW_TEMPORAL") == "True"
        )
        frontend_show_change_email = (
            payload.get("provider") == "local"
            and os.environ.get("NOTIFY_EMAIL") == "True"
            and self.get_email_policy(payload["category_id"], payload["role_id"])
        )
        isard_user_storage_update_user_quota(payload["user_id"])
        return {
            **{
                "show_bookings_button": show_bookings_button,
                "documentation_url": os.environ.get(
                    "FRONTEND_DOCS_URI", "https://isard.gitlab.io/isardvdi-docs/"
                ),
                "viewers_documentation_url": os.environ.get(
                    "FRONTEND_VIEWERS_DOCS_URI",
                    "https://isard.gitlab.io/isardvdi-docs/user/viewers/viewers/",
                ),
                "show_change_email_button": frontend_show_change_email,
                "show_temporal_tab": frontend_show_temporal_tab,
                "http_port": os.environ.get("HTTP_PORT", "80"),
                "https_port": os.environ.get("HTTPS_PORT", "443"),
                "bastion_ssh_port": os.environ.get(
                    "BASTION_SSH_PORT",
                    "2222",
                ),
                "can_use_bastion": can_use_bastion(payload),
            },
        }

    def Get(self, user_id, get_quota=False):
        user = get_cached_user_with_names(user_id)
        if user is None:
            raise Error(
                "not_found",
                "Not found user_id " + user_id,
                traceback.format_exc(),
            )
        if get_quota:
            user = {**user, **quotas.Get(user_id)}
        return user

    def get_user_full_data(self, user_id):
        with app.app_context():
            try:
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                            "secondary_groups_data": r.table("groups")
                            .get_all(r.args(d["secondary_groups"]))
                            .pluck("id", "name")
                            .coerce_to("array"),
                        }
                    )
                    .without("password")
                    .run(db.conn)
                )
            except:
                raise Error(
                    "not_found",
                    "Not found user_id " + user_id,
                    traceback.format_exc(),
                )
        return user

    def GetByProviderCategoryUID(self, provider, category, uid):
        with app.app_context():
            user = list(
                r.table("users")
                .get_all([uid, category, provider], index="uid_category_provider")
                .without("password")
                .run(db.conn)
            )
        return user

    def list_users(self, nav, category_id=None):
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
                    "group_name": r.table("groups").get(user["group"])["name"],
                    "role_name": r.table("roles").get(user["role"])["name"],
                    "category_name": r.table("categories").get(user["category"])[
                        "name"
                    ],
                    "secondary_groups_names": r.table("groups")
                    .get_all(r.args(user["secondary_groups"]))["name"]
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
                    "group_name": r.table("groups").get(user["group"])["name"],
                    "role_name": r.table("roles").get(user["role"])["name"],
                    "category_name": r.table("categories").get(user["category"])[
                        "name"
                    ],
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
        with app.app_context():
            return list(query.run(db.conn))

    def list_categories(self, nav, category_id=False):
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

        with app.app_context():
            return list(query.run(db.conn))

    def list_groups(self, nav, category_id=False):
        query = []
        if nav == "management":
            if category_id:
                query = (
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .without("quota", "limits")
                    .merge(
                        lambda group: {
                            "linked_groups_names": r.table("groups")
                            .get_all(r.args(group["linked_groups"]))["name"]
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
                            "linked_groups_names": r.table("groups")
                            .get_all(r.args(group["linked_groups"]))["name"]
                            .coerce_to("array"),
                            "parent_category_name": r.table("categories").get(
                                group["parent_category"]
                            )["name"],
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
                            .get_all(r.args(group["linked_groups"]))
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
                            .get_all(r.args(group["linked_groups"]))
                            .pluck("id", "name")
                            .coerce_to("array"),
                            "parent_category_name": r.table("categories").get(
                                group["parent_category"]
                            )["name"],
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

        return list(query.run(db.conn))

    # this method is needed for user auto-registering
    # It will get the quota from the user group provided
    def Create(
        self,
        provider,
        category_id,
        user_uid,
        user_username,
        name,
        role_id,
        group_id,
        password=False,
        encrypted_password=False,
        photo="",
        email="",
        secondary_groups=[],
    ):
        # password=False generates a random password
        user_id = str(uuid.uuid4())
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) != None:
                raise Error(
                    "conflict",
                    "Already exists user_id " + user_id,
                    traceback.format_exc(),
                )

        if get_role(role_id) is None:
            raise Error(
                "not_found",
                "Not found role_id " + role_id + " for user_id " + user_id,
                traceback.format_exc(),
            )

        if get_category(category_id) is None:
            raise Error(
                "not_found",
                "Not found category_id " + category_id + " for user_id " + user_id,
                traceback.format_exc(),
            )

        group = get_group(group_id)
        if group is None:
            raise Error(
                "not_found",
                "Not found group_id " + group_id + " for user_id " + user_id,
                traceback.format_exc(),
            )
        if password == False:
            password = _random_password()
        else:
            bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        if encrypted_password != False:
            password = encrypted_password

        user = {
            "id": user_id,
            "name": name,
            "uid": user_uid,
            "provider": provider,
            "active": True,
            "accessed": int(time.time()),
            "username": user_username,
            "password": password,
            "role": role_id,
            "category": category_id,
            "group": group_id,
            "email": email,
            "photo": photo,
            "default_templates": [],
            "quota": group["quota"],  # 10GB
            "secondary_groups": secondary_groups,
            "password_history": [password],
            "email_verification_token": None,
            "email_verified": False,
        }
        with app.app_context():
            r.table("users").insert(user).run(db.conn)
        isard_user_storage_add_user(user_id)
        return user_id

    def Update(self, user_ids, data):
        for user_id in user_ids:
            revoke_user_session(user_id)

        if data.get("password"):
            for user_id in user_ids:
                self.change_password(data["password"], user_id)
            data.pop("password")
        if data.get("ids"):
            data.pop("ids")

        if os.environ.get("NOTIFY_EMAIL") and data.get("email"):
            for user_id in user_ids:
                with app.app_context():
                    user = (
                        r.table("users")
                        .get(user_id)
                        .pluck("email", "category", "role", "email_verified")
                        .run(db.conn)
                    )
                if data.get("email") != user["email"]:
                    if self.get_email_policy(user["category"], user["role"]):
                        token = validate_email_jwt(user_id, data["email"])["jwt"]
                        with app.app_context():
                            r.table("users").get(user_id).update(
                                {
                                    "email_verification_token": token,
                                    "email_verified": False,
                                }
                            ).run(db.conn)
                        send_verification_email(data.get("email"), user_id, token)
                    else:
                        with app.app_context():
                            r.table("users").get(user_id).update(
                                {
                                    "email_verification_token": None,
                                    "email_verified": False,
                                }
                            ).run(db.conn)
        if data.get("email_verified") == True:
            data["email_verified"] = int(time.time())

        invalidate_caches("users", user_ids)

        with app.app_context():
            r.table("users").get_all(r.args(user_ids)).update(data).run(db.conn)
        for user_id in user_ids:
            # second revoke to ensure changes are applied if the user logs in again during the update
            revoke_user_session(user_id)

            isard_user_storage_update_user(
                user_id=user_id,
                email=data.get("email"),
                displayname=data.get("name"),
                role=data.get("role"),
                enabled=data.get("active"),
            )

    def Templates(self, payload):
        try:
            with app.app_context():
                templates = (
                    r.table("domains")
                    .get_all(["template", payload["user_id"]], index="kind_user")
                    .order_by("name")
                    .pluck(
                        {
                            "id",
                            "name",
                            "allowed",
                            "enabled",
                            "kind",
                            "category",
                            "group",
                            "icon",
                            "image",
                            "user",
                            "description",
                            "status",
                        },
                        {"create_dict": {"hardware": {"disks": {"storage_id": True}}}},
                    )
                    .run(db.conn)
                )
            return templates
        except Exception:
            raise Error(
                "internal_server", "Internal server error", traceback.format_exc()
            )

    def Desktops(self, user_id):
        self.Get(user_id)
        try:
            with app.app_context():
                desktops = list(
                    r.table("domains")
                    .get_all(["desktop", user_id], index="kind_user")
                    .order_by("name")
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "group",
                            "category",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "guest_properties",
                            "tag",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {
                                "create_dict": {
                                    "hardware": ["interfaces", "videos", "disks"],
                                    "reservables": True,
                                }
                            },
                            "server",
                            "progress",
                            "booking_id",
                            "scheduled",
                            "tag",
                            "current_action",
                        ]
                    )
                    .run(db.conn)
                )
            return [
                _parse_desktop(desktop)
                for desktop in desktops
                if not desktop.get("tag")
                or desktop.get("tag")
                and desktop.get("tag_visible")
            ]
        except:
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )

    def Desktop(self, desktop_id, user_id):
        self.Get(user_id)
        try:
            with app.app_context():
                desktop = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck(
                        [
                            "id",
                            "name",
                            "icon",
                            "image",
                            "user",
                            "group",
                            "category",
                            "status",
                            "description",
                            "parents",
                            "persistent",
                            "os",
                            "guest_properties",
                            "tag",
                            "tag_visible",
                            {"viewer": "guest_ip"},
                            {
                                "create_dict": {
                                    "hardware": ["interfaces", "videos"],
                                    "reservables": True,
                                }
                            },
                            "progress",
                            "booking_id",
                        ]
                    )
                    .run(db.conn)
                )
            if (
                not desktop.get("tag")
                or desktop.get("tag")
                and desktop.get("tag_visible")
            ):
                return _parse_desktop(desktop)
            else:
                raise Error(
                    "forbidden",
                    f"Desktop {desktop_id} is not visible to this user now.",
                    description_code="desktop_is_not_visible",
                )
        except:
            raise Error(
                "not_found",
                f"Desktop {desktop_id} not found",
                description_code="desktop_not_found",
            )

    def Delete(self, user_id, agent_id, delete_user):
        self.Get(user_id)
        change_user_items_owner("media", user_id)
        user_delete(agent_id, user_id, delete_user)

    def get_user_resources(self, user_id):
        desktops = []
        templates = []
        deployments = []
        media = []
        with app.app_context():
            deployments = list(
                r.table("deployments").get_all(user_id, index="user")["id"].run(db.conn)
            )
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")["id"]
                .run(db.conn)
            )
        with app.app_context():
            templates = list(
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")["id"]
                .run(db.conn)
            )
        with app.app_context():
            media = list(
                r.table("media").get_all(user_id, index="user")["id"].run(db.conn)
            )
        return {
            "desktops": desktops,
            "templates": templates,
            "deployments": deployments,
            "media": media,
        }

    def _delete_checks(self, item_ids, table):
        users = []
        groups = []
        desktops = []
        templates = []
        deployments = []
        media = []
        tags = []
        if table == "user":
            with app.app_context():
                users = list(
                    r.table("users")
                    .get_all(r.args(item_ids))
                    .pluck("id", "name", "username", "provider")
                    .run(db.conn)
                )
            with app.app_context():
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
                    .run(db.conn)
                )
            tags = [deployment["id"] for deployment in deployments]
            with app.app_context():
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
                    .run(db.conn)
                )
        elif table in ["category", "group"]:
            with app.app_context():
                users = list(
                    r.table("users")
                    .get_all(r.args(item_ids), index=table)
                    .pluck("id", "name", "username")
                    .run(db.conn)
                )
            users_ids = [user["id"] for user in users]
            with app.app_context():
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
                    .run(db.conn)
                )
            tags = [deployment["id"] for deployment in deployments]
            with app.app_context():
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
                    .run(db.conn)
                )
            if table == "category":
                with app.app_context():
                    groups = list(
                        r.table("groups")
                        .get_all(r.args(item_ids), index="parent_category")
                        .pluck("id", "name")
                        .run(db.conn)
                    )
            else:
                with app.app_context():
                    groups = list(
                        r.table("groups")
                        .get_all(r.args(item_ids))
                        .pluck("id", "name")
                        .run(db.conn)
                    )
        with app.app_context():
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
                .run(db.conn)
            )
        with app.app_context():
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
                .run(db.conn)
            )
        domains_derivated = []
        for template in templates:
            domains_derivated = domains_derivated + get_template_with_all_derivatives(
                template["id"]
            )
        desktops = desktops + list(
            filter(lambda d: d["kind"] == "desktop", domains_derivated)
        )
        desktops = list({v["id"]: v for v in desktops}.values())
        templates = templates + list(
            filter(lambda d: d["kind"] == "template", domains_derivated)
        )
        templates = list({v["id"]: v for v in templates}.values())

        with app.app_context():
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
                .run(db.conn)
            )
        if table == "category":
            with app.app_context():
                storage_pools = (
                    r.table("storage_pool")["categories"]
                    .filter(lambda pool: pool.contains(r.args(item_ids)))
                    .count()
                    .run(db.conn)
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

    def _user_storage_delete_checks(self, user_id):
        with app.app_context():
            user_storage = (
                r.table("users").get(user_id).pluck("name", "user_storage").run(db.conn)
            )
        if user_storage.get("user_storage"):
            return {
                "id": None,
                "kind": "user_storage",
                "user_name": user_storage.get("name"),
                "name": str(user_storage_quota(user_id).get("used", 0)) + " MB",
            }

    @cached(TTLCache(maxsize=10, ttl=5))
    def OwnsDesktopViewerIP(self, user_id, category_id, role_id, guess_ip):
        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all(guess_ip, index="guest_ip")
                    .filter(
                        lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                            domain["status"]
                        )
                    )
                    .pluck("user", "category", "tag")
                    .run(db.conn)
                )
        except:
            app.logger.error(traceback.format_exc())
            raise Error(
                "forbidden",
                "Forbidden access to desktop viewer",
                traceback.format_exc(),
            )
        if not len(domains):
            raise Error(
                "bad_request",
                f"No desktop with requested guess_ip {guess_ip} to access viewer",
                traceback.format_exc(),
            )
        if len(domains) > 1:
            app.logger.error(traceback.format_exc())
            raise Error(
                "internal_server",
                "Two desktops with the same viewer guest_ip",
                traceback.format_exc(),
            )

        if role_id == "admin":
            return True
        elif role_id == "manager" and domains[0].get("category") == category_id:
            return True
        elif domains[0].get("user") == user_id:
            return True
        elif domains[0].get("tag"):
            with app.app_context():
                deployment_user_owner = (
                    r.table("deployments")
                    .get(domains[0].get("tag"))
                    .pluck("user")
                    .run(db.conn)
                ).get("user", None)
            if deployment_user_owner == user_id:
                return True

        raise Error(
            "forbidden",
            f"Forbidden access to user {user_id} to desktop {domains[0]} viewer",
            traceback.format_exc(),
        )

    @cached(TTLCache(maxsize=10, ttl=5))
    def OwnsDesktopViewerProxiesPort(
        self, user_id, category_id, role_id, proxy_video, proxy_hyper_host, port
    ):
        try:
            proxy_video_parts = proxy_video.split(":")
            if len(proxy_video_parts) == 2:
                proxy_video = proxy_video_parts[0]
                proxy_video_port = proxy_video_parts[1]
            else:
                proxy_video_port = "443"
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all(
                        [proxy_video, proxy_video_port, proxy_hyper_host],
                        index="proxies",
                    )
                    .filter(
                        lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                            domain["status"]
                        )
                    )
                    .filter(r.row["viewer"]["ports"].contains(port))
                    .pluck("user", "category", "tag")
                    .run(db.conn)
                )
        except:
            raise Error(
                "forbidden",
                "Forbidden access to desktop viewer",
                traceback.format_exc(),
            )
        if not len(domains):
            raise Error(
                "bad_request",
                f"No desktop with requested parameters (proxy_video: {proxy_video}, proxy_hyper_host: {proxy_hyper_host}, port: {port}) to access viewer",
                traceback.format_exc(),
            )
        if len(domains) > 1:
            raise Error(
                "internal_server",
                "Two desktops with the same viewer guest_ip",
                traceback.format_exc(),
            )

        if role_id == "admin":
            return True
        elif role_id == "manager" and domains[0].get("category") == category_id:
            return True
        elif domains[0].get("user") == user_id:
            return True
        elif domains[0].get("tag"):
            with app.app_context():
                deployment_user_owner = (
                    r.table("deployments")
                    .get(domains[0].get("tag"))
                    .pluck("user")
                    .run(db.conn)
                ).get("user", None)
            if deployment_user_owner == user_id:
                return True

        raise Error(
            "forbidden",
            f"Forbidden access to user {user_id} to desktop {domains[0]} viewer",
            traceback.format_exc(),
        )

    def CodeSearch(self, code):
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"manager": code}}).run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "role": "manager",
                "category": category,
                "group": found[0]["id"],
            }
        with app.app_context():
            found = list(
                r.table("groups")
                .filter({"enrollment": {"advanced": code}})
                .run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "role": "advanced",
                "category": category,
                "group": found[0]["id"],
            }
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"user": code}}).run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {"role": "user", "category": category, "group": found[0]["id"]}
        raise Error(
            "not_found",
            "Code not found code:" + code,
            traceback.format_exc(),
            description_code="code_not_found",
        )

    def CategoryGet(self, category_id, all_data=False):
        with app.app_context():
            category = r.table("categories").get(category_id).run(db.conn)
        if not category:
            raise Error(
                "not_found",
                "Category not found category_id:" + category_id,
                traceback.format_exc(),
                description_code="category_not_found",
            )
        if not all_data:
            return {"name": category["name"]}
        else:
            return category

    @cached(TTLCache(maxsize=100, ttl=10))
    def CategoryGetByName(self, category_name):
        with app.app_context():
            category = list(
                r.table("categories").get_all(category_name, index="name").run(db.conn)
            )
        if not category:
            raise Error(
                "not_found",
                "Category name " + category_name + " not found",
                traceback.format_exc(),
            )
        else:
            return category[0]

    def category_get_by_custom_url(self, custom_url):
        with app.app_context():
            category = list(
                r.table("categories")
                .filter({"custom_url_name": custom_url})
                .pluck("id", "name")
                .run(db.conn)
            )
        if not category:
            raise Error(
                "not_found",
                "Category with custom url " + custom_url + " not found",
                traceback.format_exc(),
            )
        else:
            return category[0]

    def category_get_custom_login_url(self, category_id):
        try:
            with app.app_context():
                category = (
                    r.table("categories")
                    .get(category_id)
                    .pluck("frontend", "custom_url_name")
                    .run(db.conn)
                )
            return category.get("custom_url_name")
        except:
            return "/login"

    ### USER Schema

    def CategoriesGet(self):
        with app.app_context():
            return list(
                r.table("categories")
                .pluck({"id", "name", "frontend"})
                .order_by("name")
                .run(db.conn)
            )

    def CategoriesFrontendGet(self):
        with app.app_context():
            return list(
                r.table("categories")
                .pluck({"id", "name", "frontend", "custom_url_name"})
                .filter({"frontend": True})
                .order_by("name")
                .run(db.conn)
            )

    def CategoryDelete(self, category_id, agent_id):
        change_category_items_owner("media", category_id)
        category_delete(agent_id, category_id)
        remove_category_from_storage_pool(category_id)

    def GroupGet(self, group_id):
        group = get_group(group_id)
        if group is None:
            raise Error(
                "not_found",
                "Not found group_id " + group_id,
                traceback.format_exc(),
                description_code="group_not_found",
            )
        return group

    def group_get_full_data(self, group_id):
        with app.app_context():
            group = (
                r.table("groups")
                .get(group_id)
                .merge(
                    lambda d: {
                        "linked_groups_data": r.table("groups")
                        .get_all(r.args(d["linked_groups"]))
                        .pluck("id", "name")
                        .coerce_to("array")
                    }
                )
                .run(db.conn)
            )
        if not group:
            raise Error(
                "not_found",
                "Not found group_id " + group_id,
                traceback.format_exc(),
                description_code="group_not_found",
            )
        return group

    def GroupGetByNameCategory(self, group_name, category_id):
        with app.app_context():
            group = list(
                r.table("groups")
                .get_all(category_id, index="parent_category")
                .filter({"name": group_name})
                .run(db.conn)
            )
        if not group:
            raise Error(
                "not_found",
                "Not found group name " + group_name,
                traceback.format_exc(),
            )
        return group[0]

    def GroupsGet(self):
        with app.app_context():
            return list(
                r.table("groups")
                .order_by("name")
                .merge(
                    lambda group: {
                        "linked_groups_data": r.table("groups")
                        .get_all(r.args(group["linked_groups"]))
                        .pluck("id", "name")
                        .coerce_to("array"),
                    }
                )
                .run(db.conn)
            )

    def GroupDelete(self, group_id, agent_id):
        # Check the group exists
        self.GroupGet(group_id)
        change_group_items_owner("media", group_id)
        group_delete(agent_id, group_id)

    def EnrollmentAction(self, data):
        if data["action"] == "disable":
            with app.app_context():
                r.table("groups").get(data["id"]).update(
                    {"enrollment": {data["role"]: False}}
                ).run(db.conn)
            return True
        if data["action"] == "reset":
            chars = digits + ascii_lowercase
        code = False
        while code == False:
            code = "".join([random.choice(chars) for i in range(6)])
            if self.enrollment_code_check(code) == False:
                with app.app_context():
                    r.table("groups").get(data["id"]).update(
                        {"enrollment": {data["role"]: code}}
                    ).run(db.conn)
                return code
        raise Error(
            "internal_server",
            "Unable to generate enrollment code",
            traceback.format_exc(),
            description_code="unable_to_gen_enrollment_code",
        )

    def enrollment_code_check(self, code):
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"manager": code}}).run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "manager",
                "category": category,
                "group": found[0]["id"],
            }
        with app.app_context():
            found = list(
                r.table("groups")
                .filter({"enrollment": {"advanced": code}})
                .run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "advanced",
                "category": category,
                "group": found[0]["id"],
            }
        with app.app_context():
            found = list(
                r.table("groups").filter({"enrollment": {"user": code}}).run(db.conn)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "user",
                "category": category,
                "group": found[0]["id"],
            }
        return False

    def RoleGet(self, role=None):
        if role == "manager":
            with app.app_context():
                return list(
                    r.table("roles")
                    .order_by("sortorder")
                    .pluck("id", "name", "description")
                    .filter(lambda doc: doc["id"] != "admin")
                    .run(db.conn)
                )
        else:
            with app.app_context():
                return list(
                    r.table("roles")
                    .order_by("sortorder")
                    .pluck("id", "name", "description")
                    .run(db.conn)
                )

    def Secrets(self):
        with app.app_context():
            return list(r.table("secrets").run(db.conn))

    def UpdateGroupQuota(
        self, group, quota, propagate, role=False, user_role="manager"
    ):
        category = self.CategoryGet(group["parent_category"], True)
        # Managers can't update a group quota with a higher value than its category quota
        if user_role == "manager":
            if category["quota"] != False:
                for k, v in category["quota"].items():
                    if quota and quota.get(k) and v < quota[k]:
                        raise Error(
                            "precondition_required",
                            "Can't update "
                            + group["name"]
                            + " "
                            + k
                            + " quota value with a higher value than its category quota",
                            traceback.format_exc(),
                        )

        # Can't update a group quota with a higher value than its category limit
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if quota and quota.get(k) and v < quota[k]:
                    raise Error(
                        "precondition_required",
                        "Can't update "
                        + group["name"]
                        + " "
                        + k
                        + " quota value with a higher value than its category limit",
                        traceback.format_exc(),
                    )

        if not role:
            with app.app_context():
                r.table("groups").get(group["id"]).update({"quota": quota}).run(db.conn)

        if propagate or role:
            query = r.table("users").get_all(group["id"], index="group")
            if role:
                query = query.filter({"role": role})
            with app.app_context():
                query.update({"quota": quota}).run(db.conn)

    def UpdateCategoryQuota(self, category_id, quota, propagate, role=False):
        if not role:
            with app.app_context():
                r.table("categories").get(category_id).update({"quota": quota}).run(
                    db.conn
                )
        if propagate or role:
            with app.app_context():
                groups = list(
                    r.table("groups")
                    .get_all(category_id, index="parent_category")
                    .run(db.conn)
                )
            for group in groups:
                self.UpdateGroupQuota(group, quota, propagate, role, "admin")

    def UpdateGroupLimits(self, group, limits):
        category = self.CategoryGet(group["parent_category"], True)
        # Can't update a group limits with a higher value than its category limits
        if category["limits"] != False:
            for k, v in category["limits"].items():
                if limits and limits.get(k) and v < limits[k]:
                    raise Error(
                        "precondition_required",
                        "Can't update "
                        + group["name"]
                        + " "
                        + k
                        + " limits value with a higher value than its category limits",
                        traceback.format_exc(),
                    )

        with app.app_context():
            r.table("groups").get(group["id"]).update({"limits": limits}).run(db.conn)

    def UpdateSecondaryGroups(self, action, data):
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

        with app.app_context():
            query.run(db.conn)

    def UpdateCategoryLimits(self, category_id, limits, propagate):
        with app.app_context():
            r.table("categories").get(category_id).update({"limits": limits}).run(
                db.conn
            )
        if propagate:
            with app.app_context():
                r.table("groups").get_all(category_id, index="parent_category").update(
                    {"limits": limits}
                ).run(db.conn)

    def WebappDesktops(self, user_id):
        self.Get(user_id)
        with app.app_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .order_by("name")
                .without("xml", "history_domain", "allowed")
                .run(db.conn)
            )
        return [
            d
            for d in desktops
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]

    def WebappTemplates(self, user_id):
        with app.app_context():
            templates = list(
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")
                .without("viewer", "xml", "history_domain")
                .run(db.conn)
            )
        return templates

    def groups_users_count(self, groups, user_id):
        query_groups = (
            r.table("users").get_all(r.args(groups), index="group").pluck("id")["id"]
        )
        query_secondary_groups = (
            r.table("users")
            .get_all(r.args(groups), index="secondary_groups")
            .pluck("id")["id"]
        )

        with app.app_context():
            total_groups = (
                list(query_groups.run(db.conn))
                + list(query_secondary_groups.run(db.conn))
                + [user_id]
            )

        return len(list(set(total_groups)))

    def check_secondary_groups_category(self, category, secondary_groups):
        for group in secondary_groups:
            group = self.GroupGet(group)
            if group["parent_category"] != category:
                category = self.CategoryGet(category)["name"]
                raise Error(
                    "forbidden",
                    "Group "
                    + group["name"]
                    + " does not belong to category "
                    + category,
                    traceback.format_exc(),
                )

    def check_group_category(self, data):
        with app.app_context():
            return list(
                r.table("groups")
                .get_all(r.args[data["groups"]], index="id")
                .filter({"parent_category": data["category"]})
                .run(db.conn)
            )

    def change_user_language(self, user_id, lang):
        with app.app_context():
            r.table("users").get(user_id).update({"lang": lang}).run(db.conn)

    def get_user_policy(self, subtype, category, role, user_id=None):
        if user_id:
            with app.app_context():
                user = (
                    r.table("users").get(user_id).pluck("category", "role").run(db.conn)
                )
            category = user["category"]
            role = user["role"]

        with app.app_context():
            policies = list(
                r.table("authentication")
                .filter(
                    (r.row["category"] in [category, "all"])
                    | (r.row["role"] in [role, "all"])
                )
                .run(db.conn)
            )
        matching_policies = []
        for policy in policies:
            if policy["category"] == category and policy["role"] == role:
                return policy.get(subtype)
            elif policy["category"] == category and policy["role"] == "all":
                matching_policies.append({"priority": 0, "policy": policy.get(subtype)})
            elif policy["category"] == "all" and policy["role"] == role:
                matching_policies.append({"priority": 1, "policy": policy.get(subtype)})
            elif policy["category"] == "all" and policy["role"] == "all":
                matching_policies.append({"priority": 2, "policy": policy.get(subtype)})

        matching_policies.sort(key=lambda x: x["priority"])
        if matching_policies:
            return matching_policies[0]["policy"]
        else:
            return False

    def get_user_password_policy(self, category=None, role=None, user_id=None):
        return self.get_user_policy("password", category, role, user_id)

    def get_email_policy(self, category=None, role=None, user_id=None):
        return self.get_user_policy("email_verification", category, role, user_id)

    def change_password(self, password, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("category", "role", "password_history")
                .run(db.conn)
            )

        p = Password()
        policy = self.get_user_password_policy(user["category"], user["role"])

        p.check_policy(password, policy, user_id)
        password = p.encrypt(password)

        if policy["old_passwords"] == 0:
            password_history = []
        else:
            password_history = user["password_history"]
            password_history.append(password)
            password_history = password_history[-policy["old_passwords"] :]

        with app.app_context():
            r.table("users").get(user_id).update(
                {
                    "password_history": password_history,
                    "password_last_updated": int(time.time()),
                    "password": password,
                }
            ).run(db.conn)

    def check_password_expiration(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("category", "role", "password_last_updated", "provider")
                .run(db.conn)
            )
        if user["provider"] != "local":
            return False
        policy = self.get_user_password_policy(
            category=user["category"], role=user["role"]
        )
        if not policy:
            return False

        if not policy["expiration"] or policy["expiration"] == 0:
            return False
        return (
            True
            if not user.get("password_last_updated")
            else (
                datetime.fromtimestamp(user["password_last_updated"])
                + timedelta(days=policy["expiration"])
                < datetime.now()
            )
        )

    def verify_password(self, user_id, password):
        p = Password()
        with app.app_context():
            user_password = r.table("users").get(user_id)["password"].run(db.conn)
        if not p.valid(password, user_password):
            raise Error(
                "forbidden",
                "Wrong password entered",
                description_code="wrong_password_entered",
            )
        else:
            return True

    def check_verified_email(self, user_id):
        if not os.environ.get("NOTIFY_EMAIL"):
            return True
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("email_verified", "category", "role", "provider")
                .run(db.conn)
            )
        if user["provider"] != "local":
            return True
        policy = self.get_email_policy(user["category"], user["role"])
        if not policy:
            return True
        else:
            return user.get("email_verified")

    def check_acknowledged_disclaimer(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("role", "category", "lang", "disclaimer_acknowledged")
                .run(db.conn)
            )
        if user.get("disclaimer_acknowledged"):
            return False

        policy = self.get_user_policy("disclaimer", "all", user["role"], user_id)
        if policy:
            return True
        else:
            return False

    def get_lang(self, user_id):
        with app.app_context():
            lang = r.table("users").get(user_id).run(db.conn).get("lang")
        return lang

    def get_user_by_email_and_category(self, email, category):
        with app.app_context():
            users = list(
                r.table("users")
                .get_all(category, index="category")
                .filter(
                    lambda user: (user["email"].eq(email))
                    & (user["email_verified"].ne(None))
                )
                .pluck("id")["id"]
                .run(db.conn)
            )
        if len(users) == 1:
            return users[0]
        else:
            raise Error("internal_server", "Error retrieving user data")

    def reset_vpn(self, user_id):
        with app.app_context():
            r.table("users").get(user_id).update(
                {"vpn": {"wireguard": {"keys": False}}}
            ).run(db.conn)

    def bulk_user_check(self, payload, user, item_type):
        if item_type == "csv":
            user = _validate_item("user_from_csv", user)
        elif item_type == "generate":
            pass
        else:
            raise Error(
                "bad_request",
                f"Item type {item_type} not allowed",
                description_code="item_type_not_allowed",
            )

        user["username"] = user["username"].replace(" ", "")

        match = CategoryNameGroupNameMatch(user["category"], user["group"])
        user["category_id"] = match["category_id"]
        user["group_id"] = match["group_id"]

        ownsCategoryId(payload, user["category_id"])

        user_id = self.GetByProviderCategoryUID(
            "local", user["category_id"], user["username"]
        )
        if user_id:
            raise Error(
                "bad_request",
                f"User already exists",
                description_code="user_already_exists",
            )

        # Check if the role is valid
        if payload["role_id"] == "manager":
            if user["role"] not in ["manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    f"Role not in manager, advanced or user",
                    description_code="role_not_allowed",
                )
        else:
            if user["role"] not in ["admin", "manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    f"Role not in admin, manager, advanced or user",
                    description_code="role_not_allowed",
                )

        p = Password()
        if item_type == "csv":
            policy = self.get_user_password_policy(user["category_id"], user["role"])
            user["password"] = p.generate_password(policy)
        elif item_type == "generate":
            policy = self.get_user_password_policy(match["category_id"], user["role"])
            p.check_policy(user["password"], policy, username=user["username"])

        return user

    def register_migration(self, migration_token, origin_user_id):
        """

        Registers a user migration in the database. If a migration already exists for the user, it updates it with the new token.

        :param migration_token: The migration token
        :type migration_token: str
        :param origin_user_id: The origin user id
        :type origin_user_id: str
        :param exp_time: The expiration time
        :type exp_time: int

        """
        with app.app_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(origin_user_id, index="origin_user")
                .run(db.conn)
            )
        if user_migration:
            if len(user_migration) > 1:
                raise Error(
                    "forbidden",
                    "Multiple migrations found for the same user",
                    description_code="multiple_migrations_found_origin_user",
                )
            with app.app_context():
                r.table("users_migrations").get_all(
                    origin_user_id, index="origin_user"
                ).filter(
                    lambda migration: ~migration["status"].match("migrated")
                ).replace(
                    r.row.without({"import_time": True, "target_user": True}).merge(
                        {
                            "status": "exported",
                            "export_time": int(time.time()),
                            "origin_user": origin_user_id,
                            "token": migration_token,
                        }
                    )
                ).run(
                    db.conn
                )
        else:
            with app.app_context():
                r.table("users_migrations").insert(
                    {
                        "token": migration_token,
                        "status": "exported",
                        "created": int(time.time()),
                        "origin_user": origin_user_id,
                    }
                ).run(db.conn)

    def get_user_migration(self, migration_token):
        """

        Gets a user migration based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        :return: The user migration data

        """
        with app.app_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .filter(lambda migration: ~migration["status"].match("revoked|failed"))
                .run(db.conn)
            )
        if user_migration:
            if len(user_migration) > 1:
                raise Error(
                    "internal_server",
                    "Multiple migrations found for token",
                    description_code="multiple_migrations_found",
                )

            return user_migration[0]
        else:
            raise Error(
                "not_found",
                "Migration not found",
                description_code="migration_not_found",
            )

    def get_migrations(self):
        query = r.table("users_migrations")

        # Origin user data
        query = query.outer_join(
            r.table("users"),
            lambda migration, user: user["id"] == migration["origin_user"],
        )
        query = query.map(
            lambda migration: {
                "left": migration["left"],
                "right": {
                    "origin_user": r.branch(
                        migration.has_fields("right"),
                        migration["right"].pluck("name", "category"),
                        None,
                    )
                },
            }
        ).zip()

        # Target user data
        query = query.outer_join(
            r.table("users"),
            lambda migration, user: r.branch(
                migration.has_fields("target_user"),
                user["id"] == migration["target_user"],
                None,
            ),
        )
        query = query.map(
            lambda migration: {
                "left": migration["left"],
                "right": {
                    "target_username": r.branch(
                        migration["left"]
                        .has_fields("target_user")
                        .and_(migration.has_fields("right")),
                        migration["right"].pluck("name")["name"],
                        migration["left"]
                        .has_fields("target_user")
                        .and_(r.not_(migration.has_fields("right"))),
                        "[DELETED]",
                        None,
                    ),
                    "target_category": r.branch(
                        migration["left"]
                        .has_fields("target_user")
                        .and_(migration.has_fields("right")),
                        migration["right"].pluck("category")["category"],
                        None,
                    ),
                },
            }
        ).zip()

        # Category data
        query = query.outer_join(
            r.table("categories"),
            lambda migration, category: r.branch(
                migration.has_fields("origin_user").and_(
                    migration["origin_user"].has_fields("category")
                ),
                category["id"] == migration["origin_user"]["category"],
                migration.has_fields("target_category").and_(
                    migration["target_category"].ne(None)
                ),
                category["id"] == migration["target_category"],
                None,
            ),
        )
        query = query.map(
            lambda migration: {
                "left": migration["left"],
                "right": {
                    "category": r.branch(
                        migration.has_fields("right"),
                        migration["right"].pluck("name")["name"],
                        None,
                    )
                },
            }
        ).zip()

        # Origin username
        query = query.merge(
            lambda migration: {
                "origin_username": r.branch(
                    migration["origin_user"].and_(
                        migration["origin_user"].has_fields("name")
                    ),
                    migration["origin_user"]["name"],
                    "[DELETED]",
                )
            }
        )

        with app.app_context():
            return list(query.run(db.conn))

    def check_user_migration(self, migration_token, target_user_id):
        """

        Check if the user migration exists and if the migration is valid based on the migration token. If it doesn't it raises an error.

        :param migration_token: The migration token
        :type migration_token: str
        """

        migration = self.get_user_migration(migration_token)
        errors = self.check_valid_migration(migration["origin_user"], target_user_id)
        return errors

    def get_user_migration_by_target_user(self, target_user_id):
        """

        Gets a user migration based on the target user id

        :param target_user_id: The target user id
        :type target_user_id: str
        :return: The user migration data

        """

        with app.app_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(target_user_id, index="target_user")
                .filter(
                    lambda migration: ~migration["status"].match(
                        "migrated|revoked|failed"
                    )
                )
                .run(db.conn)
            )
        if len(user_migration) > 1:
            raise Error(
                "forbidden",
                "Multiple migrations found for the same target user",
                description_code="multiple_migrations_found_target_user",
            )
        if user_migration:
            return user_migration[0]
        else:
            raise Error(
                "not_found",
                "Migration not found",
                description_code="migration_not_found",
            )

    def update_user_migration(
        self,
        migration_token,
        status=None,
        target_user_id=None,
        migration_start_time=False,
        migration_end_time=False,
        migrated_items=None,
        migrated_desktops=False,
        migrated_templates=False,
        migrated_media=False,
        migrated_deployments=False,
    ):
        """
        Updates a user migration status based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        :param status: The migration status
        :type status: str
        :param target_user_id: The target user id
        :type target_user_id: str
        :param migration_start_time: Whether to set the migration start time
        :type migration_start_time: bool
        :param migration_end_time: Whether to set the migration end time
        :type migration_end_time: bool
        :param migrated_items: The migrated items
        :type migrated_items: dict
        :param migrated_desktops: Whether the desktops were migrated
        :type migrated_desktops: bool
        :param migrated_templates: Whether the templates were migrated
        :type migrated_templates: bool
        :param migrated_media: Whether the media was migrated
        :type migrated_media: bool
        :param migrated_deployments: Whether the deployments were migrated
        :type migrated_deployments: bool
        """
        data = {
            "status": status if status else None,
            "target_user": target_user_id,
            "import_time": int(time.time()) if status == "imported" else None,
            "migration_start_time": int(time.time()) if migration_start_time else None,
            "migration_end_time": int(time.time()) if migration_end_time else None,
            "migrated_items": migrated_items,
            "migrated_desktops": migrated_desktops if migrated_desktops else None,
            "migrated_templates": migrated_templates if migrated_templates else None,
            "migrated_media": migrated_media if migrated_media else None,
            "migrated_deployments": (
                migrated_deployments if migrated_deployments else None
            ),
        }
        data = {k: v for k, v in data.items() if v is not None}
        with app.app_context():
            total = (
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .count()
                .run(db.conn)
            )
        if total > 1:
            raise Error(
                "forbidden",
                "Multiple migrations found for the same token",
                description_code="multiple_migrations_found_token",
            )
        else:
            with app.app_context():
                r.table("users_migrations").get_all(
                    migration_token, index="token"
                ).update(data).run(db.conn)

    def delete_user_migration(self, migration_token):
        """
        Deletes a user migration based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        """
        with app.app_context():
            result = (
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .delete()
                .run(db.conn)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "internal_server",
                "No migration found when deleting",
                description_code="migration_not_found",
            )

    def reset_imported_user_migration_by_target_user(self, target_user_id):
        """
        Reset as exported all the imported migrations from the given target user id (remove the import_time and target_user fields too).

        :param target_user_id: The target user id
        :type target_user_id: str
        """
        with app.app_context():
            r.table("users_migrations").get_all(
                target_user_id, index="target_user"
            ).filter({"status": "imported"}).replace(
                r.row.without({"import_time": True, "target_user": True}).merge(
                    {"status": "exported"}
                )
            ).run(
                db.conn
            )

    def process_migrate_user(self, user_id, target_user_id):
        user_data = get_new_user_data(target_user_id)
        try:
            self.migrate_user(user_id, user_data)
            notify_admins(
                "user_action",
                {"action": "migrate", "count": 1, "status": "completed"},
                category=user_data["new_user"]["category"],
            )
        except Error as e:
            app.logger.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "user_action",
                {
                    "action": "migrate",
                    "count": 1,
                    "msg": error_message,
                    "status": "failed",
                },
                category=user_data["new_user"]["category"],
            )
        except Exception:
            app.logger.error(traceback.format_exc())
            notify_admins(
                "user_action",
                {
                    "action": "migrate",
                    "count": 1,
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    def migrate_user(self, user_id, user_data):
        user_resources = self.get_user_resources(user_id)
        if user_resources["desktops"]:
            change_owner_desktops(user_resources["desktops"], user_data, user_id)
        if user_resources["templates"]:
            change_owner_templates(user_resources["templates"], user_data)
        if user_resources["media"]:
            change_owner_medias(user_resources["media"], user_data)
        change_owner_deployments(user_resources["deployments"], user_data, user_id)
        rb_ids = get_user_recycle_bin_ids(user_id, "recycled")
        for rb_id in rb_ids:
            rb_delete_queue.enqueue({"recycle_bin_id": rb_id, "user_id": user_id})

    def process_automigrate_user(self, user_id, target_user_id, migration_token):
        user_data = get_new_user_data(target_user_id)
        self.update_user_migration(
            migration_token, "migrating", migration_start_time=True
        )
        result = self.automigrate_user(user_id, user_data, migration_token)
        if any(
            s in result
            for s in [
                "desktops_error",
                "templates_error",
                "media_error",
                "deployments_error",
            ]
        ):
            self.update_user_migration(
                migration_token, "failed", migration_end_time=True
            )
        else:
            self.update_user_migration(
                migration_token, "migrated", migration_end_time=True
            )
            with app.app_context():
                provider_migration_config = (
                    r.table("config")
                    .get(1)["auth"][user_data["payload"]["provider"]]
                    .run(db.conn)
                )
            action_after_migrate = provider_migration_config.get("migration", {}).get(
                "action_after_migrate", ""
            )
            if action_after_migrate == "delete":
                self.Delete(user_id, user_id, True)
            elif action_after_migrate == "disable":
                self.Update([user_id], {"active": False})
        return result

    def automigrate_user(self, user_id, user_data, migration_token):
        """

        Migrates a user based on the user data and migration token

        :param user_id: The user id to migrate
        :type user_id: str
        :param user_data: The user data to migrate to
        :type user_data: dict
        :param migration_token: The migration token
        :type migration_token: str

        """
        progress = {}

        user_resources = self.get_user_resources(user_id)
        self.update_user_migration(migration_token, migrated_items=user_resources)

        if user_resources["desktops"]:
            try:
                change_owner_desktops(user_resources["desktops"], user_data, user_id)
            except Error as e:
                progress["migrated_desktops"] = False
                progress["desktops_error"] = str(e)
                notify_custom(
                    "migration_progress",
                    {"migrated_desktops": False, "desktops_error": str(e)},
                    "/userspace",
                    user_id,
                )
            except:
                progress["migrated_desktops"] = False
                progress["desktops_error"] = "unknown"
                notify_custom(
                    "migration_progress",
                    {"migrated_desktops": False, "desktops_error": "unknown"},
                    "/userspace",
                    user_id,
                )
            else:
                self.update_user_migration(migration_token, migrated_desktops=True)
                progress["migrated_desktops"] = True
                notify_custom(
                    "migration_progress",
                    {"migrated_desktops": True},
                    "/userspace",
                    user_id,
                )

        if user_resources["templates"]:
            try:
                change_owner_templates(user_resources["templates"], user_data)
            except Error as e:
                progress["migrated_templates"] = False
                progress["templates_error"] = str(e)
                notify_custom(
                    "migration_progress",
                    {"migrated_templates": False, "templates_error": str(e)},
                    "/userspace",
                    user_id,
                )
            except:
                progress["migrated_templates"] = False
                progress["templates_error"] = "unknown"
                notify_custom(
                    "migration_progress",
                    {"migrated_templates": False, "templates_error": "unknown"},
                    "/userspace",
                    user_id,
                )
            else:
                self.update_user_migration(migration_token, migrated_templates=True)
                progress["migrated_templates"] = True
                notify_custom(
                    "migration_progress",
                    {"migrated_templates": True},
                    "/userspace",
                    user_id,
                )

        if user_resources["media"]:
            try:
                change_owner_medias(user_resources["media"], user_data)
            except Error as e:
                progress["migrated_media"] = False
                progress["media_error"] = str(e)
                notify_custom(
                    "migration_progress",
                    {"migrated_media": False, "media_error": str(e)},
                    "/userspace",
                    user_id,
                )
            except:
                progress["migrated_media"] = False
                progress["media_error"] = "unknown"
                notify_custom(
                    "migration_progress",
                    {"migrated_media": False, "media_error": "unknown"},
                    "/userspace",
                    user_id,
                )
            else:
                self.update_user_migration(migration_token, migrated_media=True)
                progress["migrated_media"] = True
                notify_custom(
                    "migration_progress",
                    {"migrated_media": True},
                    "/userspace",
                    user_id,
                )

        if user_resources["deployments"]:
            try:
                change_owner_deployments(
                    user_resources["deployments"], user_data, user_id
                )
            except Error as e:
                progress["migrated_deployments"] = False
                progress["deployments_error"] = str(e)
                notify_custom(
                    "migration_progress",
                    {"migrated_deployments": False, "deployments_error": str(e)},
                    "/userspace",
                    user_id,
                )
            except:
                progress["migrated_deployments"] = False
                progress["deployments_error"] = "unknown"
                notify_custom(
                    "migration_progress",
                    {"migrated_deployments": False, "deployments_error": "unknown"},
                    "/userspace",
                    user_id,
                )
            else:
                self.update_user_migration(migration_token, migrated_deployments=True)
                progress["migrated_deployments"] = True
                notify_custom(
                    "migration_progress",
                    {"migrated_deployments": True},
                    "/userspace",
                    user_id,
                )

        rb_ids = get_user_recycle_bin_ids(user_id, "recycled")
        for rb_id in rb_ids:
            rb_delete_queue.enqueue({"recycle_bin_id": rb_id, "user_id": user_id})
        progress["rb_deleted"] = True
        notify_custom(
            "migration_progress",
            {"rb_deleted": True},
            "/userspace",
            user_id,
        )

        # TODO: only use ws once they are implemented in frontend
        return progress

    def check_valid_migration(self, origin_user_id, target_user_id, check_quotas=False):
        """

        Checks if the user migration is valid based on the role, category and quotas

        :param origin_user_id: The user id to migrate
        :param target_user_id: The user id to migrate to
        :return: A list of errors if the migration is not valid

        """
        errors = []
        if origin_user_id == target_user_id:
            errors.append(
                {
                    "description": "Can't migrate to the same user.",
                    "description_code": "same_user_migration",
                }
            )

        user_resources = self.get_user_resources(origin_user_id)
        errors += self.check_user_category_role_migration(
            origin_user_id, target_user_id, user_resources
        )
        if errors:
            return errors
        if get_user_migration_config()["check_quotas"] or check_quotas:
            errors += self.check_target_user_quotas_migration(
                target_user_id, user_resources
            )
        return errors

    def check_user_category_role_migration(
        self, origin_user_id, target_user_id, user_resources=None
    ):
        """

        Checks if the user migration is valid based on the following rules:
        - Can't migrate to a different category
        - Can't migrate to an admin role
        - If the old role is advanced, manager or admin and the origin user has templates, media or deployments the new role can't be user

        :param origin_user_id: The user id to migrate
        :param target_user_id: The user id to migrate to
        :param user_resources: The user resources to check if the user has templates, media or deployments
        :return: A list of errors if the migration is not valid

        """
        errors = []
        origin_user = self.Get(origin_user_id)
        target_user = self.Get(target_user_id)

        if origin_user["category"] != target_user["category"]:
            errors.append(
                {
                    "description": "Can't migrate to a different category.",
                    "description_code": "different_category_migration",
                }
            )

        if origin_user["role"] == "admin" and target_user["role"] != "admin":
            errors.append(
                {
                    "description": "Can't migrate to an admin role.",
                    "description_code": "role_migration_admin",
                }
            )
        # If the old role is advanced, manager or admin and the origin user has templates, media or deployments the new role can't be user
        if (
            origin_user["role"] in ["advanced", "manager", "admin"]
            and target_user["role"] == "user"
            and (
                user_resources["templates"]
                or user_resources["media"]
                or user_resources["deployments"]
            )
        ):
            errors.append(
                {
                    "description": "Can't migrate to a user role. Users only can have desktops. Change templates, media and deployments ownership or delete them first.",
                    "description_code": "role_migration_user",
                }
            )
        return errors

    def check_target_user_quotas_migration(self, target_user_id, user_resources):
        """

        Checks if the target user quotas are surpassed based on the following rules:
        - The new user can't surpass the desktops, templates, media or deployments quotas

        :param target_user_id: The user id to migrate to
        :param user_resources: The user resources to check if the user has templates, media or deployments
        :return: A list of errors if the quotas are surpassed

        """
        errors = []
        # Deployment desktops must be ignored when checking the new user quotas
        with app.app_context():
            user_desktops = list(
                r.table("domains")
                .get_all(r.args(user_resources["desktops"]), index="id")
                .pluck("id", "tag")
                .run(db.conn)
            )
        not_deployment_desktops = list(
            filter(lambda desktop: (desktop.get("tag") in [None, False]), user_desktops)
        )
        try:
            quotas.desktop_create(target_user_id, len(not_deployment_desktops))
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_desktop_quota_error",
                }
            )

        try:
            quotas.template_create(
                target_user_id,
                len(user_resources["templates"]),
            )
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_template_quota_error",
                }
            )

        try:
            quotas.media_create(target_user_id, quantity=len(user_resources["media"]))
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_media_quota_error",
                }
            )

        try:
            quotas.deployment_create(
                [], target_user_id, len(user_resources["deployments"])
            )
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_deployments_quota_error",
                }
            )

        return errors

    def get_user_migration_status(self, migration_id):
        with app.app_context():
            return (
                r.table("users_migrations")
                .get(migration_id)
                .pluck("status")
                .run(db.conn)["status"]
            )

    def revoke_user_migration(self, migration_id):
        try:
            status = self.get_user_migration_status(migration_id)
        except ReqlNonExistenceError:
            pass

        if status in ["exported", "imported", "migrating"]:
            with app.app_context():
                r.table("users_migrations").get(migration_id).update(
                    {"status": "revoked"}
                ).run(db.conn)
        else:
            raise Error(
                "bad_request",
                description=f'Migrations in status "{status}" cannot be revoked.',
            )


def validate_email_jwt(user_id, email, minutes=60):
    return {
        "jwt": jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(minutes=minutes),
                "kid": "isardvdi",
                "type": "email-verification",
                "user_id": user_id,
                "email": email,
            },
            os.environ.get("API_ISARDVDI_SECRET"),
            algorithm="HS256",
        )
    }


"""
PASSWORDS MANAGER
"""
import random
import string

import bcrypt


class Password(object):
    def __init__(self):
        None

    def valid(self, plain_password, enc_password):
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), enc_password.encode("utf-8")
        )

    def encrypt(self, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def generate_human(self, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))

    def generate_password(self, policy):
        if not policy:
            raise ValueError("No policy provided")

        length = policy.get("length")
        min_uppercase = policy.get("uppercase")
        min_lowercase = policy.get("lowercase")
        min_digits = policy.get("digits")
        min_special = policy.get("special_characters")

        password_characters = []
        if min_uppercase:
            password_characters.extend(
                random.choices(string.ascii_uppercase, k=min_uppercase)
            )
        if min_lowercase:
            password_characters.extend(
                random.choices(string.ascii_lowercase, k=min_lowercase)
            )
        if min_digits:
            password_characters.extend(random.choices(string.digits, k=min_digits))
        if min_special:
            password_characters.extend(
                random.choices("!@#$%^&*()-_=+[]{}|;:'\",.<>/?", k=min_special)
            )

        remaining_length = length - len(password_characters)
        if remaining_length > 0:
            all_characters = string.ascii_letters + string.digits + string.punctuation
            password_characters.extend(
                random.choices(all_characters, k=remaining_length)
            )

        random.shuffle(password_characters)

        return "".join(password_characters)

    def check_policy(self, password, policy, user_id=None, username=None):
        if len(password) < policy["length"]:
            raise Error(
                "bad_request",
                "Password must be at least "
                + str(policy["length"])
                + " characters long",
                description_code="password_character_length",
                params={"num": policy["length"]},
            )

        if policy["uppercase"] > 0 and not any(char.isupper() for char in password):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["uppercase"])
                + " uppercase characters",
                description_code="password_uppercase",
                params={"num": policy["uppercase"]},
            )

        if policy["lowercase"] > 0 and not any(char.islower() for char in password):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["lowercase"])
                + " lowercase characters",
                description_code="password_lowercase",
                params={"num": policy["lowercase"]},
            )

        if policy["digits"] > 0 and not any(char.isdigit() for char in password):
            raise Error(
                "bad_request",
                "Password must have at least " + str(policy["digits"]) + " numbers",
                description_code="password_digits",
                params={"num": policy["digits"]},
            )

        special_characters = "!@#$%^&*()-_=+[]{}|;:'\",.<>/?"
        if policy["special_characters"] > 0 and not any(
            char in special_characters for char in password
        ):
            raise Error(
                "bad_request",
                "Password must have at least "
                + str(policy["special_characters"])
                + " special characters: !@#$%^&*()-_=+[]{}|;:'\",.<>/?",
                description_code="password_special_characters",
                params={"num": policy["special_characters"]},
            )

        if user_id:  # new users do not have user_id
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("username", "password_history")
                    .run(db.conn)
                )
            username = user["username"]

            if policy["old_passwords"]:
                old_passwords = user["password_history"][
                    -min(policy["old_passwords"], len(user["password_history"])) :
                ]
                for pw in old_passwords:
                    if self.valid(password, pw):
                        raise Error(
                            "bad_request",
                            "This password has already been used in the past",
                            description_code="password_already_used",
                        )
        if policy["not_username"] and username.lower() in password.lower():
            raise Error(
                "bad_request",
                "Password can not contain the username",
                description_code="password_username",
            )

        return True
