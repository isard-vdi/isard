#
#   Copyright © 2017-2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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
from functools import wraps

from flask import request
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from ..libv2 import api_sessions
from ..libv2.caches import get_document

r = RethinkDB()
import traceback

from flask import abort, request

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from cachetools import TTLCache, cached
from isardvdi_common.tokens import (
    Error,
    get_auto_register_jwt_payload,
    get_header_jwt_payload,
    get_jwt_payload,
    get_token_auth_header,
    get_unverified_external_jwt_payload,
    verify_external_jwt,
)

from ..libv2.api_allowed import ApiAllowed, get_all_linked_groups
from ..libv2.maintenance import Maintenance

api_allowed = ApiAllowed()


@cached(TTLCache(maxsize=100, ttl=15))
def get_category_maintenance(category_id):
    category_maintenance = get_document("categories", category_id, ["maintenance"])
    if category_maintenance is None:
        return None
    return category_maintenance


@cached(cache=TTLCache(maxsize=500, ttl=120))
def get_user_api_key(user_id):
    with app.app_context():
        user = (
            r.table("users")
            .get(user_id)
            .default({})
            .pluck("api_key", "active")
            .run(db.conn)
        )
    if user.get("api_key") is None:
        raise Error(
            "not_found",
            "User api_key not found for user_id " + user_id,
            traceback.format_exc(),
        )
    if not user.get("active"):
        raise Error(
            "forbidden",
            f"User is not active. User_id: {user_id}",
            traceback.format_exc(),
        )
    return user["api_key"]


def check_user_api_key(user_id):
    user_api_key = get_user_api_key(user_id)
    header_api_key = get_token_auth_header()
    if header_api_key != user_api_key:
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )


def maintenance(category_id=None):
    if Maintenance.enabled:
        abort(503)
    elif category_id:
        if get_category_maintenance(category_id):
            abort(503)


def has_password_reset_required_or_password_reset_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") in ["password-reset-required", "password-reset"]:
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    return decorated


def has_disclaimer_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") == "disclaimer-acknowledgement-required":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Token not valid for this operation.",
            traceback.format_exc(),
        )

    return decorated


def has_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        if get_jwt_payload().get("session_id", "") != "api-key":
            api_sessions.get(
                get_jwt_payload().get("session_id", ""), get_remote_addr(request)
            )
        else:
            # Check if the API key token is the one in the db
            check_user_api_key(payload["user_id"])

        if payload.get("role_id") != "admin":
            maintenance(payload.get("category_id"))
        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def has_token_maintenance(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def has_viewer_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()

        if payload.get("role_id") != "admin":
            maintenance(payload.get("category_id"))
        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def is_register(f):  # TODO
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") == "register":
            maintenance(payload["category_id"])
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Invalid register type token",
            traceback.format_exc(),
        )

    return decorated


def is_auto_register(f):  # TODO
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_auto_register_jwt_payload()
        if payload.get("type", "") == "register":
            maintenance(payload["category_id"])
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Invalid auto register type token",
            traceback.format_exc(),
        )

    return decorated


def has_migration_required_or_login_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        payload_type = payload.get("type", "")

        if payload_type == "user-migration-required":
            kwargs["payload"] = payload
            return f(*args, **kwargs)

        elif payload_type not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )

        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

        maintenance()
        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def is_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        if get_jwt_payload().get("session_id", "") != "api-key":
            api_sessions.get(
                get_jwt_payload().get("session_id", ""), get_remote_addr(request)
            )
        else:
            # Check if the API key token is the one in the db
            check_user_api_key(payload["user_id"])

        if payload["role_id"] == "admin":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )

    return decorated


def is_admin_or_manager(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        if get_jwt_payload().get("session_id", "") != "api-key":
            api_sessions.get(
                get_jwt_payload().get("session_id", ""), get_remote_addr(request)
            )
        else:
            # Check if the API key token is the one in the db
            check_user_api_key(payload["user_id"])

        if payload.get("role_id") != "admin":
            maintenance(payload["category_id"])
        if payload["role_id"] == "admin" or payload["role_id"] == "manager":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )

    return decorated


def is_not_user(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload.get("type", "") not in ["login", ""]:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        if get_jwt_payload().get("session_id", "") != "api-key":
            api_sessions.get(
                get_jwt_payload().get("session_id", ""), get_remote_addr(request)
            )
        else:
            # Check if the API key token is the one in the db
            header_api_key = get_token_auth_header()
            check_user_api_key(payload["user_id"])
        if payload.get("role_id") != "admin":
            maintenance(payload["category_id"])
        if payload["role_id"] != "user":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )

    return decorated


def is_hyper(f):  # TODO
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] in ["hypervisor", "admin"]:
            return f(*args, **kwargs)
        raise Error(
            {"error": "forbidden", "description": "Not enough rights" " token."}, 403
        )

    return decorated


def owns_table_item_id(fn):
    @wraps(fn)
    def decorated_view(table, *args, **kwargs):
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin":
            return fn(payload, table, *args, **kwargs)
        try:
            myargs = request.get_json(force=True)
        except:
            myargs = request.form.to_dict()
        try:
            id = kwargs["id"]
        except:
            try:
                id = myargs["pk"]
            except:
                id = myargs["id"]

        if table == "users":
            ownsUserId(payload, id)
        if table == "domains":
            ownsDomainId(payload, id)
        if table == "categories":
            ownsCategoryId(payload, id)
        if table == "deployments":
            ownsDeploymentId(payload, id)
        return fn(payload, table, *args, **kwargs)

    return decorated_view


### Helpers
def get_remote_addr(request):
    return request.headers.get("X-Forwarded-For", request.remote_addr).split(",")[0]


def ownsUserId(payload, user_id):
    if payload["role_id"] == "admin":
        return True
    if payload["role_id"] == "manager":
        user = get_document("users", user_id, ["category", "role"])
        if user is None:
            raise Error(
                "not_found",
                f"User {user_id} not found",
                traceback.format_exc(),
            )
        if user["category"] == payload["category_id"] and user["role"] != "admin":
            return True
    if payload["user_id"] == user_id:
        return True
    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + str(user_id),
        traceback.format_exc(),
    )


def ownsExternalUserId(payload, user_id):
    provider = get_document("users", user_id, ["provider"])
    if provider is None:
        raise Error(
            "not_found",
            "User not found",
            traceback.format_exc(),
        )
    if provider != "external_" + payload.get("kid", ""):
        raise Error(
            "forbidden",
            "Not enough access rights for this user_id " + str(user_id),
            traceback.format_exc(),
        )

    if payload["role_id"] == "admin":
        return True
    if payload["role_id"] == "manager":
        user = get_document("users", user_id, ["category", "role"])
        if user is None:
            raise Error(
                "not_found",
                f"User {user_id} not found",
                traceback.format_exc(),
            )
        if user["category"] == payload["category_id"] and user["role"] != "admin":
            return True

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + str(user_id),
        traceback.format_exc(),
    )


def ownsCategoryId(payload, category_id):
    if payload["role_id"] == "admin":
        return True
    if payload["role_id"] == "manager" and category_id == payload["category_id"]:
        return True
    raise Error(
        "forbidden",
        "Not enough access rights for this category_id: " + str(category_id),
        traceback.format_exc(),
    )


@cached(TTLCache(maxsize=100, ttl=10))
def CategoryNameGroupNameMatch(category_name, group_name):
    with app.app_context():
        category = list(
            r.table("categories")
            .get_all(category_name.strip(), index="name")
            .run(db.conn)
        )
    if not len(category):
        raise Error(
            "bad_request",
            "Category name " + category_name + " not found",
            traceback.format_exc(),
        )

    with app.app_context():
        group = list(
            r.table("groups")
            .get_all(category[0]["id"], index="parent_category")
            .filter({"name": group_name.strip()})
            .run(db.conn)
        )

    if not len(group):
        raise Error(
            "bad_request",
            "Group name " + group_name + " not found in category " + category_name,
            traceback.format_exc(),
        )

    if group[0]["parent_category"] == category[0]["id"]:
        return {
            "category_id": category[0]["id"],
            "category": category[0]["name"],
            "group_id": group[0]["id"],
            "group": group[0]["name"],
        }

    raise Error(
        "bad_request",
        "Category name "
        + category_name
        + " does not have child group name "
        + group_name,
        traceback.format_exc(),
    )


def ownsDomainId(payload, domain_id):
    # User is admin
    if payload.get("role_id", "") == "admin":
        return True

    domain = get_document("domains", domain_id, ["user", "category", "tag"])
    if domain is None:
        raise Error(
            "not_found", "Desktop not found", traceback.format_exc(), "not_found"
        )

    # User is owner
    if domain["user"] == payload["user_id"]:
        return True

    # User is advanced and the desktop is from one of its deployments
    if payload.get("role_id", "") == "advanced" and domain.get("tag", False):
        ownsDeploymentId(payload, domain["tag"])
        return True

    # User is manager and the desktop is from its categories
    if payload["role_id"] == "manager":
        if payload.get("category_id", "") == domain["category"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights to access this domain_id " + str(domain_id),
        traceback.format_exc(),
        description_code="not_enough_rights_desktop" + str(domain_id),
    )


def ownsMediaId(payload, media_id):
    # User is admin
    if payload.get("role_id", "") == "admin":
        return True
    media = get_document("media", media_id, ["user", "category"])
    if media is None:
        raise Error(
            "not_found",
            f"Media {media_id} not found",
            traceback.format_exc(),
            "not_found",
        )
    # User is owner
    if media["user"] == payload["user_id"]:
        return True

    # User is manager and the media is from its categories
    if payload["role_id"] == "manager":
        if payload.get("category_id", "") == media["category"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights to access this media_id " + str(media_id),
        traceback.format_exc(),
        description_code="not_enough_rights_media" + str(media_id),
    )


def ownsDeploymentId(payload, deployment_id, check_co_owners=True):
    if payload["role_id"] == "admin":
        return True
    deployment = get_document("deployments", deployment_id, ["user", "co_owners"])
    if deployment is None:
        raise Error(
            "not_found",
            f"Deployment {deployment_id} not found",
            traceback.format_exc(),
            "not_found",
        )
    if check_co_owners:
        if (
            deployment["user"] == payload["user_id"]
            or payload["user_id"] in deployment["co_owners"]
        ):
            return True
    else:
        if deployment["user"] == payload["user_id"]:
            return True
    if payload["role_id"] == "manager":
        deployment_category = get_document("users", deployment["user"], ["category"])
        if deployment_category is None:
            raise Error(
                "not_found",
                f"Deployment user {deployment['user']} not found",
                traceback.format_exc(),
            )
        if deployment_category == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights to access this deployment_id " + str(deployment_id),
        traceback.format_exc(),
    )


def ownsDeploymentDesktopId(payload, desktop_id, check_co_owners=True):
    desktop = get_document("domains", desktop_id)
    if desktop is None:
        raise Error(
            "not_found",
            f"Desktop {desktop_id} not found",
            traceback.format_exc(),
            "not_found",
        )

    if payload.get("role_id", "user") != "user" and desktop.get("tag"):
        try:
            ownsDeploymentId(payload, desktop["tag"], check_co_owners=check_co_owners)
        except:
            return False
        return True
    return False


def ownsStorageId(payload, storage_id):
    if payload["role_id"] == "admin":
        return True
    storage_user_id = get_document("storage", storage_id, ["user_id"])
    if storage_user_id is None:
        raise Error(
            "not_found",
            f"Storage {storage_id} not found",
            traceback.format_exc(),
            "not_found",
        )

    if storage_user_id == payload["user_id"]:
        return True

    if payload["role_id"] == "manager":
        category_id = get_document("users", payload["user_id"], ["category"])
        if category_id is None:
            raise Error(
                "not_found",
                f"User {payload['user_id']} not found",
                traceback.format_exc(),
            )
        if category_id == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        traceback.format_exc(),
    )


def ownsBookingId(payload, bookings_id):
    if payload["role_id"] == "admin":
        return True

    bookings_user_id = get_document("bookings", bookings_id, ["user_id"])
    if bookings_user_id is None:
        raise Error(
            "not_found",
            f"Booking {bookings_id} not found",
            traceback.format_exc(),
        )
    if bookings_user_id == payload["user_id"]:
        return True

    if payload["role_id"] == "manager":
        booking_category_id = get_document("users", bookings_user_id, ["category"])
        if booking_category_id is None:
            raise Error(
                "not_found",
                f"Booking user {bookings_user_id} not found",
                traceback.format_exc(),
            )
        if booking_category_id == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        traceback.format_exc(),
    )


def ownsRecycleBinId(payload, recycle_bin_id):
    if payload["role_id"] == "admin":
        return True

    recycle_bin_user_id = get_document("recycle_bin", recycle_bin_id, ["owner_id"])
    if recycle_bin_user_id is None:
        raise Error(
            "not_found",
            f"Recycle bin {recycle_bin_id} not found",
            traceback.format_exc(),
        )
    if recycle_bin_user_id == payload["user_id"]:
        return True

    if payload["role_id"] == "manager":
        recycle_bin_category_id = get_document(
            "recycle_bin", recycle_bin_user_id, ["owner_category_id"]
        )
        if recycle_bin_category_id is None:
            raise Error(
                "not_found",
                f"Recycle bin user {recycle_bin_user_id} not found",
                traceback.format_exc(),
            )
        if recycle_bin_category_id == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        traceback.format_exc(),
    )


def itemExists(item_table, item_id):
    item = get_document(item_table, item_id)
    if item is None:
        raise Error(
            "not_found",
            item_table + " not found id: " + item_id,
            traceback.format_exc(),
        )
    return True


def userNotExists(uid, category_id, provider="local"):
    if list(
        r.table("users")
        .get_all([uid, category_id, provider], index="uid_category_provider")
        .run(db.conn)
    ):
        raise Error(
            "bad_request",
            "UID " + uid + " already exists in category_id " + category_id,
            traceback.format_exc(),
        )


def checkDuplicate(
    item_table,
    item_name,
    category=False,
    user=False,
    item_id=None,
    ignore_deleted=False,
):
    query = (
        r.table(item_table)
        .get_all(item_name, index="name")
        .filter(lambda item: (item["id"] != item_id))
    )

    ## check duplicate in the same category
    if category:
        if item_table == "groups":
            query = query.filter({"parent_category": category})

        else:
            query = query.filter({"category": category})

    ## check duplicate in the same user
    elif user:
        query = query.filter({"user": user})

    ## do not check deleted items
    if ignore_deleted:
        query = query.filter(lambda item: item["status"] != "deleted")

    with app.app_context():
        item = list(query.run(db.conn))

    if item:
        raise Error(
            "conflict",
            "Item with this name: " + item_name + " already exists in " + item_table,
            traceback.format_exc(),
            description_code="duplicated_name",
        )


def checkDuplicates(
    item_table, item_names, user, item_id=None, ignore_deleted=False, raise_error=True
):
    query = (
        r.table(item_table)
        .get_all(r.args(item_names), index="name")
        .filter(lambda item: (item["id"] != item_id))
    )
    if user:
        query = query.filter({"user": user})
    if ignore_deleted:
        query = query.filter(lambda item: item["status"] != "deleted")
    with app.app_context():
        items = list(query.run(db.conn))
    if items and raise_error:
        raise Error(
            "conflict",
            'Items with these names: "'
            + ", ".join([item["name"] for item in items])
            + '" already exist in '
            + item_table,
            traceback.format_exc(),
            description_code="duplicated_name",
        )
    return items


def checkDuplicatesDomains(
    kind, domain_names, user, item_id=None, ignore_deleted=False, raise_error=True
):
    query = (
        r.table("domains")
        .get_all([r.args(domain_names), user], index="name_user")
        .filter(lambda item: (item["id"] != item_id) and item["kind"] == kind)
    )
    if user:
        query = query.filter({"user": user})
    if ignore_deleted:
        query = query.filter(lambda item: item["status"] != "deleted")
    with app.app_context():
        items = list(query.run(db.conn))
    if items and raise_error:
        raise Error(
            "conflict",
            'Items with these names: "'
            + ", ".join([item["name"] for item in items])
            + '" already exist in domains',
            traceback.format_exc(),
            description_code="duplicated_name",
        )
    return items


def checkDuplicateUser(item_uid, category, provider):
    query = r.table("users").get_all(
        [item_uid, category, provider], index="uid_category_provider"
    )

    item = list(query.run(db.conn))

    if item:
        raise Error(
            "conflict",
            "User with this username: "
            + item_uid
            + " already exists in this category.",
            traceback.format_exc(),
        )


def checkDuplicateCustomURL(custom_url, category_id=None):
    query = (
        r.table("categories")
        .get_all(custom_url, index="custom_url_name")
        .filter(lambda item: (item["id"] != category_id))
    )

    if len(list(query.run(db.conn))) > 0:
        raise Error(
            "conflict", "Custom URL name already exists", traceback.format_exc()
        )


def checkDuplicateUID(uid, category_id=None):
    query = (
        r.table("categories")
        .get_all(uid, index="uid")
        .filter(lambda item: (item["id"] != category_id))
        .count()
    )
    with app.app_context():
        if query.run(db.conn) > 0:
            raise Error(
                "conflict", "Category UID already exists", traceback.format_exc()
            )


def checkDuplicateBastionDomains(domains, category_id=None, target_id=None):
    """Validate multiple bastion domains for uniqueness and correctness."""
    if not domains:
        return

    if not isinstance(domains, list):
        raise Error(
            "bad_request",
            "Domains must be a list",
            traceback.format_exc(),
        )

    try:
        system_domain = os.getenv("DOMAIN")
        bastion_domain = get_document("config", 1, ["bastion"]).get("domain")

        for domain in domains:
            # Explicit validation - reject empty/invalid domains instead of silently skipping
            if not domain or not isinstance(domain, str):
                raise Error(
                    "bad_request",
                    "Empty or invalid domains are not allowed in the domains list",
                    traceback.format_exc(),
                )

            domain = domain.strip()
            if not domain:
                raise Error(
                    "bad_request",
                    "Whitespace-only domains are not allowed",
                    traceback.format_exc(),
                )

            if domain == system_domain:
                raise Error(
                    "conflict",
                    "Bastion domain is the same as the default domain",
                    traceback.format_exc(),
                )

            if domain == bastion_domain:
                raise Error(
                    "conflict",
                    "Bastion domain is the same as the default domain",
                    traceback.format_exc(),
                )

            query = (
                r.table("categories")
                .get_all(domain, index="bastion_domain")
                .filter(lambda item: (item["id"] != category_id))
                .count()
            )
            with app.app_context():
                if query.run(db.conn) > 0:
                    raise Error(
                        "conflict",
                        "Bastion domain already exists in another category",
                        traceback.format_exc(),
                    )

            query = (
                r.table("targets")
                .get_all(domain, index="domains")
                .filter(lambda item: (item["id"] != target_id))
                .count()
            )
            with app.app_context():
                if query.run(db.conn) > 0:
                    raise Error(
                        "conflict",
                        "Bastion domain is already assigned to another target",
                        traceback.format_exc(),
                    )

    except Error:
        raise Error(
            "conflict",
            "Bastion domain already exists",
            traceback.format_exc(),
            description_code="bastion_domain_exists",
        )
    except Exception:
        raise Error(
            "conflict",
            "Error checking bastion domain",
            traceback.format_exc(),
        )


# Backward compatibility wrapper for single domain
def checkDuplicateBastionDomain(domain, category_id=None, target_id=None):
    if domain is None:
        return
    checkDuplicateBastionDomains([domain], category_id, target_id)


def allowedTemplateId(payload, template_id):
    template = get_document("domains", template_id, ["user", "allowed", "category"])
    if template is None:
        raise Error(
            "not_found",
            "Template not found",
            traceback.format_exc(),
            "not_found",
        )
    if payload["user_id"] == template["user"]:
        return True
    alloweds = template["allowed"]
    if payload["role_id"] == "admin":
        return True
    if (
        payload["role_id"] == "manager"
        and payload["category_id"] == template["category"]
    ):
        return True
    if alloweds["roles"] != False:
        if alloweds["roles"] == []:
            return True
        if payload["role_id"] in alloweds["roles"]:
            return True
    if alloweds["categories"] != False:
        if alloweds["categories"] == []:
            return True
        if payload["category_id"] in alloweds["categories"]:
            return True
    if alloweds["groups"] != False:
        if alloweds["groups"] == []:
            return True
        if payload["group_id"] in alloweds["groups"]:
            return True
        secondary_groups = get_document(
            "users", payload["user_id"], ["secondary_groups"]
        )
        if secondary_groups is not None and secondary_groups:
            for group in get_all_linked_groups(
                [payload["group_id"]] + secondary_groups
            ):
                if group in alloweds["groups"]:
                    return True
    if alloweds["users"] != False:
        if alloweds["users"] == []:
            return True
        if payload["user_id"] in alloweds["users"]:
            return True
    raise Error(
        "forbidden",
        "Not enough access rights for this template_id " + str(template_id),
        traceback.format_exc(),
    )


def allowed_deployment_action(payload, domain_id, action):
    ownsDomainId(payload, domain_id)

    if payload.get("role_id", "") in ["admin", "manager", "advanced"]:
        return True

    domain_tag = get_document("domains", domain_id, ["tag"])
    user_permissions = get_document("deployments", domain_tag, ["user_permissions"])
    if user_permissions is None:
        user_permissions = []

    if action in user_permissions:
        return True

    raise Error(
        "unauthorized",
        f"Not enough rights to perform action {action} on domain_id {domain_id}",
        traceback.format_exc(),
        description_code=f"not_enough_rights_action_{action}_{domain_id}",
    )


def bastion_enabled():
    if (os.environ.get("BASTION_ENABLED", "false")).lower() == "true" and get_document(
        "config", 1, ["bastion"]
    ).get("enabled"):
        return True
    return False


def can_use_bastion(payload):
    if not bastion_enabled():
        return False

    bastion_allowed = get_document("config", 1, ["bastion"])
    if bastion_allowed is None:
        return False

    return api_allowed.is_allowed(payload, bastion_allowed, "config", True)


def can_use_bastion_individual_domains(payload):
    if not can_use_bastion(payload):
        return False

    bastion_allowed = get_document("config", 1, ["bastion"]).get("individual_domains")
    if bastion_allowed is None:
        return False

    return api_allowed.is_allowed(payload, bastion_allowed, "config", True)


def operations_api_enabled(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        operations_api_enabled = os.getenv("OPERATIONS_API_ENABLED")
        if operations_api_enabled is None:
            operations_api_enabled = False
        else:
            operations_api_enabled = operations_api_enabled.lower() == "true"

        if operations_api_enabled:
            return f(*args, **kwargs)

        raise Error(
            "precondition_required",
            "Operations API is not enabled",
            traceback.format_exc(),
        )

    return decorated


def has_external_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        jwt_data = get_unverified_external_jwt_payload()
        secret_data = get_document("secrets", jwt_data.get("kid"))
        if not secret_data:
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        if (
            not secret_data.get("id") == jwt_data.get("kid")
            or not secret_data.get("domain") == jwt_data.get("domain")
            or not secret_data.get("category_id") == jwt_data.get("category_id")
            or not secret_data.get("role_id") == jwt_data.get("role_id")
        ):
            raise Error(
                "forbidden",
                "Token not valid for this operation.",
                traceback.format_exc(),
            )
        kwargs["payload"] = verify_external_jwt(
            jwt_data.get("token"), secret_data.get("secret")
        )
        return f(*args, **kwargs)

    return decorated
