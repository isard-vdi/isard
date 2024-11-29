# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
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
)

from ..libv2.api_allowed import ApiAllowed, get_all_linked_groups
from ..libv2.maintenance import Maintenance

api_allowed = ApiAllowed()


@cached(TTLCache(maxsize=100, ttl=15))
def get_category_maintenance(category_id):
    with app.app_context():
        category = (
            r.table("categories").get(category_id).pluck("maintenance").run(db.conn)
        )
    return category.get("maintenance")


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
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

        if payload.get("role_id") != "admin":
            maintenance(payload.get("category_id"))
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
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

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
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

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


def is_admin_or_manager_or_advanced(f):
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

        if payload.get("role_id") != "admin":
            maintenance(payload["category_id"])
        if (
            payload["role_id"] == "admin"
            or payload["role_id"] == "manager"
            or payload["role_id"] == "advanced"
        ):
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
        api_sessions.get(
            get_jwt_payload().get("session_id", ""), get_remote_addr(request)
        )

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
        with app.app_context():
            user = r.table("users").get(user_id).pluck("category", "role").run(db.conn)
        if user["category"] == payload["category_id"] and user["role"] != "admin":
            return True
    if payload["user_id"] == user_id:
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
        "unauthorized",
        "Not enough access rights to access this domain_id " + str(domain_id),
        traceback.format_exc(),
        description_code="not_enough_rights_desktop" + str(domain_id),
    )


def ownsMediaId(payload, media_id):
    # User is admin
    if payload.get("role_id", "") == "admin":
        return True

    with app.app_context():
        media = r.table("media").get(media_id).pluck("user", "category").run(db.conn)

    # User is owner
    if media["user"] == payload["user_id"]:
        return True

    # User is manager and the media is from its categories
    if payload["role_id"] == "manager":
        with app.app_context():
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
    deployment = get_document("deployments", deployment_id)
    if check_co_owners:
        if deployment and (
            deployment["user"] == payload["user_id"]
            or payload["user_id"] in deployment["co_owners"]
        ):
            return True
    else:
        if deployment and deployment["user"] == payload["user_id"]:
            return True
    if payload["role_id"] == "manager":
        deployment_category = get_document("users", deployment["user"], ["category"])
        if deployment_category == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights to access this deployment_id " + str(deployment_id),
        traceback.format_exc(),
    )


def ownsDeploymentDesktopId(payload, desktop_id, check_co_owners=True):
    try:
        with app.app_context():
            desktop = (
                r.table("domains")
                .get(desktop_id)
                .pluck("user", "category", "tag")
                .run(db.conn)
            )
    except:
        raise Error(
            "not_found", "Desktop not found", traceback.format_exc(), "not_found"
        )

    if payload.get("role_id", "user") != "user" and desktop.get("tag"):
        try:
            ownsDeploymentId(payload, desktop["tag"], check_co_owners=check_co_owners)
        except:
            return False
        return True
    return False


def ownsStorageId(payload, storage_id):
    with app.app_context():
        storage = r.table("storage").get(storage_id).run(db.conn)
    if storage is None:
        raise Error(
            "not_found",
            f"Storage {storage_id} not found",
            traceback.format_exc(),
            "not_found",
        )
    if payload["role_id"] == "admin":
        return storage
    storage_user_id = storage.get("user_id")
    if storage_user_id is None:
        raise Error(
            "not_found",
            f"Storage {storage_id} missing user_id",
            traceback.format_exc(),
            "not_found",
        )

    if storage_user_id == payload["user_id"]:
        return storage

    if payload["role_id"] == "manager":
        with app.app_context():
            storage_category_id = (
                r.table("users")
                .get(storage_user_id)
                .pluck("category")["category"]
                .run(db.conn)
            )
        if storage_category_id == payload["category_id"]:
            return storage

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        traceback.format_exc(),
    )


def ownsBookingId(payload, bookings_id):
    if payload["role_id"] == "admin":
        return True

    with app.app_context():
        booking_user_id = (
            r.table("bookings")
            .get(bookings_id)
            .pluck("user_id")["user_id"]
            .run(db.conn)
        )
    if booking_user_id == payload["user_id"]:
        return True

    if payload["role_id"] == "manager":
        with app.app_context():
            booking_category_id = (
                r.table("users")
                .get(booking_user_id)
                .pluck("category")["category"]
                .run(db.conn)
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

    with app.app_context():
        recycle_bin_user_id = (
            r.table("recycle_bin")
            .get(recycle_bin_id)
            .pluck("owner_id")["owner_id"]
            .run(db.conn)
        )
    if recycle_bin_user_id == payload["user_id"]:
        return True

    if payload["role_id"] == "manager":
        with app.app_context():
            recycle_bin_category_id = (
                r.table("recycle_bin")
                .get(recycle_bin_id)
                .pluck("owner_category_id")["owner_category_id"]
                .run(db.conn)
            )
        if recycle_bin_category_id == payload["category_id"]:
            return True

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
        traceback.format_exc(),
    )


def itemExists(item_table, item_id):
    with app.app_context():
        try:
            item = r.table(item_table).get(item_id).run(db.conn)
            if not item:
                raise Error(
                    "not_found",
                    item_table + " not found id: " + item_id,
                    traceback.format_exc(),
                )
        except:
            raise Error(
                "bad_request",
                item_table + " is missing",
                traceback.format_exc(),
            )


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


def checkDuplicates(item_table, item_names, user, item_id=None, ignore_deleted=False):
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
    if items:
        raise Error(
            "conflict",
            'Items with these names: "'
            + ", ".join([item["name"] for item in items])
            + '" already exist in '
            + item_table,
            traceback.format_exc(),
            description_code="duplicated_name",
        )


def checkDuplicatesDomains(
    kind, domain_names, user, item_id=None, ignore_deleted=False
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
    if items:
        raise Error(
            "conflict",
            'Items with these names: "'
            + ", ".join([item["name"] for item in items])
            + '" already exist in domains',
            traceback.format_exc(),
            description_code="duplicated_name",
        )


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


def allowedTemplateId(payload, template_id):
    with app.app_context():
        template = (
            r.table("domains")
            .get(template_id)
            .pluck("user", "allowed", "category")
            .default(None)
            .run(db.conn)
        )
    if not template:
        raise Error(
            "not_found",
            "Not found template_id " + str(template_id),
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
        secondary_groups = (
            r.table("users")
            .get(payload["user_id"])
            .pluck("secondary_groups")
            .run(db.conn)
        )
        for group in get_all_linked_groups(
            [payload["group_id"]] + secondary_groups.get("secondary_groups", [])
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


def canPerformActionDeployment(payload, domain_id, action):
    ownsDomainId(payload, domain_id)

    if payload.get("role_id", "") in ["admin", "manager", "advanced"]:
        return True

    try:
        with app.app_context():
            domain = r.table("domains").get(domain_id).pluck("tag").run(db.conn)
            permissions = (
                r.table("deployments")
                .get(domain["tag"])
                .pluck("user_permissions")
                .run(db.conn)
            )
    except:
        permissions = []

    if payload.get("role_id", "") == "user":
        if action in permissions["user_permissions"]:
            return True

    raise Error(
        "unauthorized",
        f"Not enough rights to perform action {action} on domain_id {domain_id}",
        traceback.format_exc(),
        description_code=f"not_enough_rights_action_{action}_{domain_id}",
    )


def can_use_bastion(payload):
    bastion_enabled = (
        True
        if (os.environ.get("BASTION_ENABLED", "false")).lower() == "true"
        else False
    )
    if not bastion_enabled:
        return False

    bastion_alloweds = (
        r.table("config").get(1).pluck({"bastion": "allowed"}).run(db.conn)["bastion"]
    )

    return api_allowed.is_allowed(payload, bastion_alloweds, "config", True)
