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

import json
import os
import secrets
import traceback
from math import ceil

import gevent
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .. import socketio
from .providers.Nextcloud import NextcloudApi, start_login_auth

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)
ISARD_SHARE_FOLDER = "IsardVDI"


def _clear_caches():
    None


########################
# IsardVDI Interface   #
########################

## GET


@cached(cache=TTLCache(maxsize=10, ttl=10))
def isard_user_storage_get_users():
    with app.app_context():
        provider_users = list(
            r.table("users")
            .has_fields("user_storage")
            .pluck(
                "id",
                "name",
                "role",
                "group",
                "category",
                {"user_storage": {"provider_id": True, "provider_quota": True}},
                "email",
            )
            .run(db.conn)
        )
    for pu in provider_users:
        pu["group_name"] = _get_isard_group_provider_name(pu["group"])
        pu["category_name"] = _get_isard_category_name(pu["category"])
    return provider_users


## ADD
def isard_user_storage_add_user(user_id):
    try:
        user_storage_add_user_th(
            user_id,
            provider_id=_get_isard_user_provider_id(user_id),
            create_groups=False,
            webdav_folder=True,
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error adding user {user_id} to user_storage provider"
        )


def isard_user_storage_add_group(group_id):
    try:
        user_storage_add_group_th(
            group_id,
            _get_isard_group_provider_id(group_id),
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error adding group {group_id} to user_storage provider"
        )


def isard_user_storage_add_category(category_id):
    try:
        user_storage_add_category_th(
            category_id,
            _get_isard_category_provider_id(category_id),
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error adding category {category_id} to user_storage provider"
        )


## REMOVE
def isard_user_storage_remove_user(user_id):
    try:
        user_storage_remove_user_th(user_id, _get_isard_user_provider_id(user_id))
    except:
        app.logger.error(
            f"USER_STORAGE - Error removing user {user_id} in user_storage provider"
        )


def isard_user_storage_remove_group(group_id, cascade=True):
    try:
        user_storage_remove_group_th(
            group_id,
            _get_isard_group_provider_id(group_id),
            cascade,
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error removing group {group_id} in user_storage provider"
        )


def isard_user_storage_remove_category(category_id, cascade=True):
    try:
        user_storage_remove_category_th(
            category_id,
            _get_isard_category_provider_id(category_id),
            cascade,
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error removing category {category_id} in user_storage provider"
        )


## UPDATE
def isard_user_storage_update_user(
    user_id,
    password=None,
    quota_MB=None,
    email=None,
    displayname=None,
    role=None,
    enabled=None,
):
    try:
        if (
            password != None
            or quota_MB != None
            or email != None
            or displayname != None
            or role != None
        ):
            user_storage_update_user_th(
                user_id,
                password=password,
                quota_MB=quota_MB,
                email=email,
                displayname=displayname,
                role=role,
            )
        if enabled != None:
            user_storage_enable_user_th(user_id, enabled)
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating user {user_id} in user_storage provider"
        )


def isard_user_storage_update_group(group_id, group_name):
    try:
        user_storage_update_group_th(
            group_id,
            _get_isard_group_category_name(group_id) + "--" + group_name,
            _get_isard_group_provider_id(group_id),
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating group {group_id} in user_storage provider"
        )


def isard_user_storage_update_category(category_id, category_name):
    try:
        user_storage_update_category_th(
            category_id,
            category_name,
            _get_isard_category_provider_id(category_id),
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating category {category_id} in user_storage provider"
        )


def isard_user_storage_update_user_quota(user_id):
    try:
        user_storage_update_user_quota_th(user_id)
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating user {user_id} quota in user_storage provider"
        )


## ADMIN SYNCS
def isard_user_storage_sync_users(provider_id):
    user_storage_provider_users_sync(provider_id)


def isard_user_storage_sync_groups(provider_id):
    user_storage_provider_groups_sync(provider_id)


## ADMIN PROVIDERS


def isard_user_storage_get_provider(provider_id):
    if not provider_id:
        return None
    with app.app_context():
        try:
            return r.table("user_storage").get(provider_id).run(db.conn)
        except:
            return None


@cached(TTLCache(maxsize=1, ttl=3))
def isard_user_storage_get_providers():
    with app.app_context():
        providers = list(
            r.table("user_storage")
            .merge(
                lambda user_storage: {
                    "category_name": r.table("categories")
                    .get(user_storage["access"])["name"]
                    .default("*")
                }
            )
            .run(db.conn)
        )
    new_providers = []
    for provider in providers:
        if not provider.get("password"):
            provider["authorization"] = False
        else:
            provider["authorization"] = True
        provider.pop("password", None)
        new_providers.append(provider)
    return new_providers


#### Get isard_user_storage_get_providers_th gevent delayed connection status
def get_ws_connection_status(provider):
    try:
        isard_user_storage_provider_basic_auth_test(
            provider["provider"],
            "pepito",
            provider["urlprefix"],
            provider["user"],
            provider["password"],
            provider["verify_cert"],
        )
        provider["connection"] = True
    except Exception as e:
        app.logger.debug(
            f"USER_STORAGE - Error testing connection to provider {provider['id']}: {e}"
        )
        app.logger.error(
            f"USER_STORAGE - Error testing connection to provider {provider['id']}"
        )
        provider["connection"] = False
    socketio.emit(
        "user_storage_provider",
        json.dumps(
            {
                "id": provider["id"],
                "connection": provider["connection"],
            }
        ),
        namespace="/administrators",
        room="admins",
    )
    if provider["connection"]:
        new_users, deleted_users = get_users_inconsistency(provider["id"])
        new_groups, deleted_groups = get_groups_inconsistency(provider["id"])
        socketio.emit(
            "user_storage_provider",
            json.dumps(
                {
                    "id": provider["id"],
                    "new_users": len(new_users),
                    "deleted_users": len(deleted_users),
                    "new_groups": len(new_groups),
                    "deleted_groups": len(deleted_groups),
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def isard_user_storage_get_providers_ws():
    with app.app_context():
        providers = list(
            r.table("user_storage")
            .merge(
                lambda user_storage: {
                    "category_name": r.table("categories")
                    .get(user_storage["access"])["name"]
                    .default("*")
                }
            )
            .run(db.conn)
        )
    new_providers = []
    for provider in providers:
        if not provider.get("password"):
            provider["authorization"] = False
            provider["connection"] = False
        else:
            provider["authorization"] = True
            # Check connection Thread
            gevent.spawn_later(0.5, get_ws_connection_status, provider.copy())
        provider.pop("password", None)
        new_providers.append(provider)
    return new_providers


def isard_user_storage_provider_reset(provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    process_user_storage_remove_user_batches(
        data_batch=_get_provider_users_array(provider_id), provider_id=provider_id
    )
    process_user_storage_remove_group_batches(
        data_batch=_get_provider_groups(provider_id), provider_id=provider_id
    )
    provider["conn"].remove_group(provider["cfg"]["access"])

    # Get users from db that matches this provider access
    query = r.table("users")
    if provider["cfg"]["access"] != "*":
        query = query.get_all(provider["cfg"]["access"], index="category")
    with app.app_context():
        query.replace(r.row.without("user_storage")).run(db.conn)


def isard_user_storage_provider_delete(provider_id):
    try:
        isard_user_storage_provider_reset(provider_id)
    except:
        pass
    with app.app_context():
        r.table("user_storage").get(provider_id).delete().run(db.conn).get("deleted")
    _clear_caches()


def isard_user_storage_reset_all():
    users = []
    groups = []
    for provider_db in isard_user_storage_get_providers():
        provider = _get_provider(provider_db["id"])
        users = list(set(users + provider["conn"].get_users()))
        groups = list(set(groups + provider["conn"].get_groups()))
        provider_id = provider_db["id"]
    process_user_storage_remove_user_batches(users, provider_id)
    process_user_storage_remove_group_batches(groups, provider_id)


def isard_user_storage_provider_basic_auth_test(
    provider, domain, urlprefix, user, password, verify_cert
):
    if provider == "nextcloud":
        if os.environ.get("NEXTCLOUD_INSTANCE", "") == "true":
            intra_docker = True
            verify_cert = False
        else:
            intra_docker = False
        provider = NextcloudApi(domain + urlprefix, verify_cert, intra_docker)
        provider.set_basic_auth(user, password)
        return provider.check_connection()


def isard_user_storage_provider_auto_register_auth(
    domain, user, password, intra_docker, verify_cert
):
    provider_id = [
        p["id"] for p in isard_user_storage_get_providers() if p["url"] == domain
    ]
    if provider_id:
        with app.app_context():
            r.table("user_storage").get(provider_id[0]).update(
                {
                    "user": user,
                    "password": password,
                    "intra_docker": intra_docker,
                    "verify_cert": verify_cert,
                }
            ).run(db.conn)
        return provider_id[0]
    with app.app_context():
        provider_id = (
            r.table("user_storage")
            .insert(
                {
                    "provider": "nextcloud",
                    "name": domain,
                    "description": "Connection to Nextcloud instance inside IsardVDI containers",
                    "url": domain,
                    "urlprefix": "/isard-nc",
                    "access": "*",
                    "quota": {
                        "admin": 500,
                        "advanced": 300,
                        "manager": 500,
                        "user": 100,
                    },
                    "user": user,
                    "password": password,
                    "tls": True,  # Engine takes this into account. Will set davs:// or dav:// on QMP guest agent command.
                    "verify_cert": verify_cert,  # Engine davs:// command and API ocs connections will take this into account.
                    "auth_protocol": "basic",
                    "intra_docker": intra_docker,  # API uses this to connect internally to http://isard-nc-nginx if set
                    "enabled": True,
                },
                return_changes=True,
            )
            .run(db.conn)["changes"][0]["new_val"]["id"]
        )
    return provider_id


def isard_user_storage_provider_basic_auth_add(
    provider,
    name,
    description,
    domain,
    urlprefix,
    access,
    quota,
    verify_cert,
):
    with app.app_context():
        provider_id = (
            r.table("user_storage")
            .insert(
                {
                    "provider": provider,
                    "name": name,
                    "description": description,
                    "url": domain,
                    "urlprefix": urlprefix,
                    "access": access,
                    "quota": quota,
                    "user": False,
                    "password": False,
                    "tls": True,
                    "verify_cert": verify_cert,
                    "auth_protocol": "basic",
                    "intra_docker": False,
                    "enabled": True,
                },
                return_changes=True,
            )
            .run(db.conn)["changes"][0]["new_val"]["id"]
        )
    _clear_caches()
    return provider_id


def isard_user_storage_provider_login_auth_socketio(
    provider_id,
):
    with app.app_context():
        try:
            # Wait for admin to authorize provider
            app.logger.info("USER_STORAGE - Waiting for admin to authorize provider")
            with gevent.Timeout(5 * 60):
                for data in (
                    r.table("user_storage")
                    .get(provider_id)
                    .changes()
                    .pluck({"new_val": {"password": True}})
                    .run(db.conn)
                ):
                    socketio.emit(
                        "user_storage_provider",
                        json.dumps(
                            {
                                "id": provider_id,
                                "authorization": True,
                                "connection": True,
                            }
                        ),
                        namespace="/administrators",
                        room="admins",
                    )
                    app.logger.info(
                        f"USER_STORAGE - Admin authorized provider {provider_id}"
                    )
                    return
        except:
            app.logger.warning(
                f"USER_STORAGE - Timeout when waiting for admin to authorize provider {provider_id}"
            )


login_thread = None


def isard_user_storage_provider_login_auth(
    provider_id,
):
    global login_thread
    if login_thread:
        login_thread.kill()
    login_thread = gevent.spawn(
        isard_user_storage_provider_login_auth_socketio, provider_id
    )
    return start_login_auth(provider_id)


####################
# GENERIC QUERIES #
####################

## Users generic queries
isard_users_info_cache = TTLCache(maxsize=10, ttl=240)


@cached(isard_users_info_cache)
def _get_isard_users_info(provider_id=None):
    provider = _get_provider(provider_id)
    if not provider or provider.get("cfg", {}).get("access") == "*":
        with app.app_context():
            return (
                r.table("users")
                .pluck(
                    "id", "name", "role", "group", "category", "user_storage", "email"
                )
                .group("id")
                .run(db.conn)
            )

    with app.app_context():
        return (
            r.table("users")
            .get_all(provider["cfg"]["access"], index="category")
            .pluck("id", "name", "role", "group", "category", "user_storage", "email")
            .group("id")
            .run(db.conn)
        )


def _get_isard_user_info(user_id):
    return _get_isard_users_info(_get_isard_user_provider_id(user_id))[user_id][0]


def _get_isard_user_name(user_id):
    return _get_isard_user_info(user_id)["name"]


def _get_isard_user_email(user_id):
    return _get_isard_user_info(user_id)["email"]


def _get_isard_user_role(user_id):
    return _get_isard_user_info(user_id)["role"]


def _get_isard_user_group_id(user_id):
    return _get_isard_user_info(user_id)["group"]


def _get_isard_user_category_id(user_id):
    return _get_isard_user_info(user_id)["category"]


isard_users_cache = TTLCache(maxsize=10, ttl=10)


@cached(isard_users_cache)
def _get_isard_users_array(provider_id=None):
    provider = _get_provider(provider_id)
    if provider["cfg"]["access"] != "*":
        with app.app_context():
            return (
                r.table("users")
                .get_all(provider["cfg"]["access"], index="category")
                .pluck("id")["id"]
                .coerce_to("array")
                .run(db.conn)
            )
    else:
        with app.app_context():
            return r.table("users").pluck("id")["id"].coerce_to("array").run(db.conn)


@cached(TTLCache(maxsize=10, ttl=10))
def _get_provider_users_array(provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    if provider["cfg"]["access"] == "*":
        return provider["conn"].get_users()
    return provider["conn"].get_group_members(provider["cfg"]["access"])


## Groups generic queries

isard_groups_info_cache = TTLCache(maxsize=100, ttl=10)


@cached(isard_groups_info_cache)
def _get_isard_groups_info(provider_id=None):
    if not provider_id:
        with app.app_context():
            return (
                r.table("groups")
                .pluck("id", "name", "parent_category")
                .merge(
                    lambda group: {
                        "category_name": r.table("categories").get(
                            group["parent_category"]
                        )["name"],
                    }
                )
                .group("id")
                .run(db.conn)
            )
    provider = _get_provider(provider_id)
    if provider["cfg"]["access"] != "*":
        with app.app_context():
            return (
                r.table("groups")
                .get_all(provider["cfg"]["access"], index="parent_category")
                .pluck("id", "name", "parent_category")
                .merge(
                    lambda group: {
                        "category_name": r.table("categories").get(
                            group["parent_category"]
                        )["name"],
                    }
                )
                .group("id")
                .run(db.conn)
            )
    with app.app_context():
        return (
            r.table("groups")
            .pluck("id", "name", "parent_category")
            .merge(
                lambda group: {
                    "category_name": r.table("categories").get(
                        group["parent_category"]
                    )["name"],
                }
            )
            .group("id")
            .run(db.conn)
        )


def _get_isard_group_info(group_id):
    return _get_isard_groups_info(_get_isard_group_provider_id(group_id))[group_id][0]


def _get_isard_group_category_name(group_id):
    return _get_isard_group_info(group_id)["category_name"]


def _get_isard_group_provider_name(group_id):
    return (
        _get_isard_group_category_name(group_id)
        + "--"
        + _get_isard_group_info(group_id)["name"]
    )


isard_groups_cache = TTLCache(maxsize=10, ttl=10)


@cached(isard_groups_cache)
def _get_isard_groups_array(provider_id=None):
    if not provider_id:
        with app.app_context():
            return r.table("groups").pluck("id")["id"].coerce_to("array").run(db.conn)
    provider = _get_provider(provider_id)
    if provider["cfg"]["access"] != "*":
        with app.app_context():
            return (
                r.table("groups")
                .get_all(provider["cfg"]["access"], index="parent_category")
                .pluck("id")["id"]
                .merge(r.row["parent_category"])
                .coerce_to("array")
                .run(db.conn)
            )
    else:
        with app.app_context():
            return (
                r.table("groups").pluck("id")["id"].coerce_to("array").run(db.conn)
            ) + (
                r.table("categories").pluck("id")["id"].coerce_to("array").run(db.conn)
            )


## Categories generic queries

isard_categories_info_cache = TTLCache(maxsize=10, ttl=10)


@cached(isard_categories_info_cache)
def _get_isard_categories_info(provider_id=None):
    provider = _get_provider(provider_id)
    if provider["cfg"]["access"] != "*":
        with app.app_context():
            return (
                r.table("categories")
                .get_all(provider["cfg"]["access"])
                .pluck("id", "name")
                .group("id")
                .run(db.conn)
            )
    with app.app_context():
        return r.table("categories").pluck("id", "name").group("id").run(db.conn)


def _get_isard_category_name(category_id):
    return _get_isard_categories_info(_get_isard_category_provider_id(category_id))[
        category_id
    ][0]["name"]


def _get_isard_categories_array(provider_id=None):
    provider = _get_provider(provider_id)
    if provider["cfg"]["access"] != "*":
        with app.app_context():
            return (
                r.table("categories")
                .get_all(provider["cfg"]["access"])
                .pluck("id")
                .coerce_to("array")
                .run(db.conn)
            )
    with app.app_context():
        return r.table("categories").pluck("id")["id"].coerce_to("array").run(db.conn)


########################
# PROVIDERS MANAGEMENT #
########################

cache_provider = TTLCache(maxsize=10, ttl=5)


@cached(cache_provider)
def _get_provider(provider_id, user_id=None):
    provider_cfg = isard_user_storage_get_provider(provider_id)
    if not provider_cfg:
        return None
    if not provider_cfg.get("enabled"):
        app.logger.debug("USER_STORAGE - User storage provider not enabled in system.")
        return None
    if not provider_cfg.get("password"):
        app.logger.debug("USER_STORAGE - User storage provider not authorized yet.")
        return None
    if provider_cfg["provider"] == "nextcloud":
        provider = NextcloudApi(
            provider_cfg["url"] + provider_cfg["urlprefix"],
            provider_cfg["verify_cert"],
            intra_docker=provider_cfg["intra_docker"],
        )
        if provider_cfg["auth_protocol"] == "basic":
            provider.set_basic_auth(provider_cfg["user"], provider_cfg["password"])
        if user_id:
            user = _get_isard_user_info(user_id)
            if user.get("user_storage", {}).get("password"):
                provider.set_webdav_auth(
                    user["user_storage"]["user_id"], user["user_storage"]["password"]
                )
        return {"cfg": provider_cfg, "conn": provider}
    return None


@cached(TTLCache(maxsize=10, ttl=10))
def _get_isard_category_provider_id(category_id):
    with app.app_context():
        providers_cfgs = list(
            r.table("user_storage").filter({"access": category_id}).run(db.conn)
        )
    if len(providers_cfgs):
        provider_cfg = providers_cfgs[0]
    else:
        provider_cfg = None
        with app.app_context():
            provider = list(
                r.table("user_storage").filter({"access": "*"}).run(db.conn)
            )
        if len(provider):
            provider_cfg = provider[0]

    if not provider_cfg:
        return None
    return provider_cfg["id"]


def _get_isard_group_provider_id(group_id):
    return _get_isard_category_provider_id(
        _get_isard_groups_info()[group_id][0]["parent_category"]
    )


def _get_isard_user_provider_id(user_id):
    return _get_isard_category_provider_id(
        _get_isard_users_info()[user_id][0]["category"]
    )


### BATCH Add/Remove Users in batches with greenlets threads


def get_users_inconsistency(provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    isard_users = _get_isard_users_array(provider_id)
    provider_users = _get_provider_users_array(provider_id)

    new_users = [iu for iu in isard_users if iu not in provider_users]
    removed_users = [pu for pu in provider_users if pu not in isard_users]
    return new_users, removed_users


def process_user_storage_add_user_batch(
    data_batch, provider_id, create_groups, webdav_folder
):
    for item_id in data_batch:
        user_storage_add_user(
            user_id=item_id,
            provider_id=provider_id,
            create_groups=create_groups,
            webdav_folder=webdav_folder,
        )


def process_user_storage_add_user_batches(
    data_batch, provider_id, create_groups, webdav_folder
):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No users to add to provider")
        return

    if create_groups:
        user_storage_add_provider_categories_th(provider_id)
        process_user_storage_add_group_batches(
            data_batch=_get_isard_groups_array(provider_id), provider_id=provider_id
        )

    # Number of simultaneous users that can be created
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> ADD %s USERS TO PROVIDER IN %s BATCHES OF %s USERS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(
                process_user_storage_add_user_batch,
                batch,
                provider_id,
                create_groups=False,
                webdav_folder=webdav_folder,
            )
        )
    gevent.joinall(jobs)


def process_user_storage_remove_user_batch(data_batch, provider_id):
    # Spawn a greenlet for each item in the batch
    for item_id in data_batch:
        user_storage_remove_user(
            user_id=item_id,
            provider_id=provider_id,
        )


def process_user_storage_remove_user_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No users to remove to provider")
        return
    # Number of simultaneous users that can be removed
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> REMOVE %s USERS IN PROVIDER IN %s BATCHES OF %s USERS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_remove_user_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


def process_user_storage_add_user_subadmin_batch(data_batch, provider_id):
    provider = _get_provider(provider_id)
    for item_id in data_batch:
        try:
            provider["conn"].add_subadmin(user_id=item_id[0], group_id=item_id[1])
        except:
            app.logger.error(
                f"USER_STORAGE - Error adding subadmin user {item_id[0]} in group {item_id[1]} in user_storage provider",
            )
            socketio.emit(
                "personal_unit",
                json.dumps(
                    {
                        "action": "Add subadmin",
                        "name": item_id[0],
                        "status": False,
                        "msg": "Error adding subadmin",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )


def process_user_storage_add_user_subadmin_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No subadins to add to user")
        return
    # Number of simultaneous groups that can be removed
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> ADD %s SUBADMINS TO USER IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(
                process_user_storage_add_user_subadmin_batch, batch, provider_id
            )
        )
    gevent.joinall(jobs)


def process_user_storage_delete_subadmin_batch(data_batch, provider_id):
    provider = _get_provider(provider_id)
    for item_id in data_batch:
        try:
            provider["conn"].delete_subadmin(user_id=item_id[0], group_id=item_id[1])
        except:
            app.logger.error(
                f"USER_STORAGE - Error deleting subadmin user {item_id[0]} in group {item_id[1]} in user_storage provider",
            )
            socketio.emit(
                "personal_unit",
                json.dumps(
                    {
                        "action": "Delete subadmin",
                        "name": item_id[0],
                        "status": False,
                        "msg": "Error deleting subadmin",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )


def process_user_storage_delete_subadmin_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No subadmins to delete from user")
        return
    # Number of simultaneous groups that can be removed
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> DELETE %s SUBADMINS FROM USER IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_delete_subadmin_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


def user_storage_provider_users_sync(provider_id):
    new_users, removed_users = get_users_inconsistency(provider_id)
    process_user_storage_add_user_batches(
        data_batch=new_users,
        provider_id=provider_id,
        create_groups=True,
        webdav_folder=True,
    )
    process_user_storage_remove_user_batches(
        data_batch=removed_users, provider_id=provider_id
    )


### BATCH Add/Update/Remove Groups in batches with greenlets threads


def get_groups_inconsistency(provider_id):
    # Get groups from provider
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    provider_groups = _get_provider_groups(provider_id)
    isard_groups = _get_isard_groups_array(provider_id)

    new_groups = [ig for ig in isard_groups if ig not in provider_groups]
    removed_groups = [pg for pg in provider_groups if pg not in isard_groups]
    return new_groups, removed_groups


def process_user_storage_add_group_batch(data_batch, provider_id):
    for item_id in data_batch:
        user_storage_add_group(
            group_id=item_id,
            provider_id=provider_id,
        )


def process_user_storage_add_group_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No groups to add to provider")
        return
    # Number of simultaneous groups that can be created
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> ADD %s GROUPS TO PROVIDER IN %s BATCHES OF %s GROUPS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_add_group_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


def process_user_storage_update_group_batch(data_batch, provider_id):
    for item_id in data_batch:
        user_storage_update_group(
            group_id=item_id[0],
            new_group_name=item_id[1],
            provider_id=provider_id,
        )


def process_user_storage_update_group_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No groups to update to provider")
        return
    # Number of simultaneous groups that can be created
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> UPDATE %s GROUPS TO PROVIDER IN %s BATCHES OF %s GROUPS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_update_group_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


def process_user_storage_remove_group_batch(data_batch, provider_id):
    for item_id in data_batch:
        user_storage_remove_group(group_id=item_id, provider_id=provider_id)


def process_user_storage_remove_group_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No groups to remove to provider")
        return
    # Number of simultaneous groups that can be removed
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> REMOVE %s GROUPS IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_remove_group_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


def user_storage_provider_groups_sync(provider_id):
    new_groups, removed_groups = get_groups_inconsistency(provider_id)
    process_user_storage_add_group_batches(
        data_batch=new_groups, provider_id=provider_id
    )

    process_user_storage_remove_group_batches(
        data_batch=removed_groups, provider_id=provider_id
    )
    user_storage_add_provider_categories_th(provider_id)


### BATCH Add Categories in batches with greenlets threads


def process_user_storage_add_category_batch(data_batch, provider_id):
    for item_id in data_batch:
        user_storage_add_category(
            category_id=item_id,
            provider_id=provider_id,
        )


def process_user_storage_add_category_batches(data_batch, provider_id):
    if not len(data_batch):
        app.logger.debug("USER_STORAGE - No categories to add to provider")
        return
    # Number of simultaneous categories that can be created
    max_batch_threads = 10
    batch_size = ceil(len(data_batch) / max_batch_threads)

    batches = [
        data_batch[i : i + batch_size] for i in range(0, len(data_batch), batch_size)
    ]

    app.logger.info(
        "USER_STORAGE ==> ADD %s CATEGORIES TO PROVIDER IN %s BATCHES OF %s CATEGORIES EACH"
        % (len(data_batch), len(batches), batch_size)
    )

    # Process each batch in a separate thread
    jobs = []
    for batch in batches:
        jobs.append(
            gevent.spawn(process_user_storage_add_category_batch, batch, provider_id)
        )
    gevent.joinall(jobs)


########################
#   USERS MANAGEMENT   #
########################

## Add/Update/Remove users


def user_storage_add_user_th(
    user_id, provider_id=None, create_groups=False, webdav_folder=True
):
    # This is the function to be called when adding a new user through the web interface, to not block the creation
    gevent.spawn(
        user_storage_add_user,
        user_id,
        provider_id,
        create_groups,
        webdav_folder,
    )


def user_storage_add_user(
    user_id, provider_id, create_groups=False, webdav_folder=True
):
    # This function is called when adding a new user in bulk, as it blocks the calling loop
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    if create_groups:
        user_storage_add_group(
            group_id=_get_isard_user_group_id(user_id), provider_id=provider_id
        )

    password = secrets.token_urlsafe(20)
    app.logger.info(
        "USER_STORAGE ==> ADD USER %s TO PROVIDER %s" % (user_id, provider_id)
    )
    try:
        provider["conn"].add_user(
            user_id,
            password,
            provider["cfg"]["quota"].get(_get_isard_user_role(user_id)),
            groups=[
                _get_isard_user_category_id(user_id),
                _get_isard_user_group_id(user_id),
            ],
            email=_get_isard_user_email(user_id),
            displayname=_get_isard_user_name(user_id),
        )
        user_storage_update_user_subadmin(
            user_id, _get_isard_user_role(user_id), provider_id
        )
        user_storage = {
            "user_id": user_id,
            "password": password,
            "web": "https://" + provider["cfg"]["url"] + provider["cfg"]["urlprefix"],
            "dav": provider["cfg"]["url"]
            + provider["cfg"]["urlprefix"]
            + "/remote.php/webdav/"
            + ISARD_SHARE_FOLDER,
            "tls": True,
            "verify_cert": provider["cfg"]["verify_cert"],
            "provider_id": provider["cfg"]["id"],
            "quota": provider["cfg"]["quota"].get(_get_isard_user_role(user_id)),
            "provider_quota": provider["conn"].get_user_quota(user_id),
        }
        if not webdav_folder:
            with app.app_context():
                r.table("users").get(user_id).update(
                    {"user_storage": user_storage}
                ).run(db.conn)
            return
        provider["conn"].add_user_folder(user_id, password)
        data = provider["conn"].add_user_share_folder(user_id, password)
        user_storage = {
            **user_storage,
            **{
                "token": data["token"],
                "token_web": "https://"
                + provider["cfg"]["url"]
                + provider["cfg"]["urlprefix"]
                + "/s/"
                + data["token"],
                "token_davs": "davs://"
                + data["token"]
                + "@"
                + provider["cfg"]["url"]
                + provider["cfg"]["urlprefix"]
                + "/public.php/webdav",
            },
        }
        with app.app_context():
            r.table("users").get(user_id).update({"user_storage": user_storage}).run(
                db.conn
            )

        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user",
                    "name": user_id,
                    "status": True,
                    "msg": "Added user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error adding user {user_id} in user_storage provider",
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_remove_user_th(user_id, provider_id=None):
    gevent.spawn(user_storage_remove_user, user_id, provider_id)


def user_storage_remove_user(user_id, provider_id=None):
    # The isard database user removal should be be done before this
    if user_id == "admin":
        return
    if not provider_id:
        provider = _get_provider(_get_isard_user_provider_id(user_id))
    else:
        provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    try:
        provider["conn"].remove_user(user_id)
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Delete user",
                    "name": user_id,
                    "status": True,
                    "msg": "Deleted user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
        with app.app_context():
            r.table("users").get(user_id).replace(r.row.without("user_storage")).run(
                db.conn
            )
    except Error as e:
        if e.status_code == 404:
            app.logger.error(
                f"USER_STORAGE - User storage remove user {user_id} not found in user_storage provider"
            )
    except:
        app.logger.error(
            f"USER_STORAGE - User storage remove user {user_id} in user_storage provider internal error"
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Delete user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error deleting user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_update_user_th(
    user_id, password=None, quota_MB=None, email=None, displayname=None, role=None
):
    gevent.spawn(
        user_storage_update_user,
        user_id,
        password=password,
        quota_MB=quota_MB,
        email=email,
        displayname=displayname,
        role=role,
    )


def user_storage_update_user(
    user_id, password=None, quota_MB=None, email=None, displayname=None, role=None
):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    if not provider:
        # We will return as there are no providers defined in system
        return
    # Update user
    try:
        provider["conn"].update_user(
            user_id,
            password=password,
            quota_MB=quota_MB,
            email=email,
            displayname=displayname,
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating user: {user_id} in user_storage provider",
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Update user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error updating user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )

    user_storage_update_user_subadmin(user_id, role, provider["cfg"]["id"])

    socketio.emit(
        "personal_unit",
        json.dumps(
            {
                "action": "Update user",
                "name": user_id,
                "status": True,
                "msg": "Updated user",
            }
        ),
        namespace="/administrators",
        room="admins",
    )

    user_storage = {}
    if password:
        user_storage["password"] = password
    if quota_MB:
        user_storage["quota"] = quota_MB
    if email:
        user_storage["email"] = email
    if displayname:
        user_storage["displayname"] = displayname

    with app.app_context():
        r.table("users").get(user_id).update({"user_storage": user_storage}).run(
            db.conn
        )


def user_storage_enable_user_th(user_id, enabled):
    gevent.spawn(user_storage_enable_user, user_id, enabled)


def user_storage_enable_user(user_id, enabled):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    if not provider:
        # We will return as there are no providers defined in system
        return
    try:
        if enabled == False:
            provider["conn"].disable_user(user_id)
        if enabled == True:
            provider["conn"].enable_user(user_id)
    except Exception as e:
        app.logger.debug(f"USER_STORAGE - Error enabling user: {e}")
        app.logger.error(
            f"USER_STORAGE - Error enabling user: {user_id} in user_storage provider",
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Enable user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error enabling user",
                }
            ),
            namespace="/administrators",
            room="admins",
        )

    socketio.emit(
        "personal_unit",
        json.dumps(
            {
                "action": "Enable user",
                "name": user_id,
                "status": True,
                "msg": "Enabled user",
            }
        ),
        namespace="/administrators",
        room="admins",
    )


def user_storage_update_user_subadmin(user_id, role, provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    user_subadmin_groups = provider["conn"].get_user(user_id).get("subadmin", [])
    groups_add = []
    groups_delete = []
    if role == "admin":
        # Now we are doing the same for admins and managers
        # TODO: admins should be added to all providers with all providers groups
        for group_id in _get_provider_groups(provider_id):
            if group_id not in user_subadmin_groups:
                groups_add.append([user_id, group_id])
        try:
            gevent.spawn(
                provider["conn"].add_subadmin,
                user_id,
                _get_isard_user_category_id(user_id),
            )
        except:
            pass
    if role == "manager":
        for group_id in _get_provider_groups(provider_id):
            if group_id not in user_subadmin_groups:
                groups_add.append([user_id, group_id])
        try:
            gevent.spawn(
                provider["conn"].add_subadmin,
                user_id,
                _get_isard_user_category_id(user_id),
            )
        except:
            pass

    if role not in ["admin", "manager"]:
        for group_id in user_subadmin_groups:
            try:
                groups_delete.append([user_id, group_id])
                provider["conn"].delete_subadmin(user_id, group_id)
            except:
                pass

    if len(groups_add) > 0:
        process_user_storage_add_user_subadmin_batches(groups_add, provider_id)
    if len(groups_delete) > 0:
        process_user_storage_delete_subadmin_batches(groups_delete, provider_id)


## Users quota


@cached(TTLCache(maxsize=10, ttl=10))
def user_storage_quota(user_id):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    if not provider:
        # We will return as there are no providers defined in system
        return

    return provider["conn"].get_user_quota(user_id)


def user_storage_update_user_quota_th(user_id):
    gevent.spawn(user_storage_update_user_quota, user_id)


def user_storage_update_user_quota(user_id):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    if not provider:
        # We will return as there are no providers defined in system
        return
    provider_quota = provider["conn"].get_user_quota(user_id)
    with app.app_context():
        r.table("users").get(user_id).update(
            {"user_storage": {"provider_quota": provider_quota}}
        ).run(db.conn)


def user_storage_quota_update(user_id):
    user_storage_quota = user_storage_quota(user_id)
    if not user_storage_quota:
        # We will return as there are no providers defined in system
        return
    with app.app_context():
        r.table("users").get(user_id).update(
            {"user_storage": {"provider_quota": user_storage_quota}}
        ).run(db.conn)
    return user_storage_quota


## Users folders


def user_storage_add_user_folder(user_id, folder=ISARD_SHARE_FOLDER):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    user = _get_isard_user_info(user_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    # Add user folder
    try:
        provider["conn"].add_user_folder(
            user_id, user["user_storage"]["password"], folder
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user folder",
                    "name": user_id,
                    "status": True,
                    "msg": "Added user folder",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user folder",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user folder",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_add_user_share_folder(user_id, folder=ISARD_SHARE_FOLDER):
    provider = _get_provider(_get_isard_user_provider_id(user_id))
    user = _get_isard_user_info(user_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    try:
        data = provider["conn"].add_user_share_folder(
            user["id"], user["user_storage"]["password"], folder
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user share folder",
                    "name": user["id"],
                    "status": True,
                    "msg": "Added user share folder",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add user share folder",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user share folder: the folder does not exist.",
                }
            ),
            namespace="/administrators",
            room="admins",
        )

    if data == False:
        return
    user_storage = {
        "token": data["token"],
        "token_web": "https://"
        + provider["cfg"]["url"]
        + provider["cfg"]["urlprefix"]
        + "/s/"
        + data["token"],
        "token_davs": "davs://"
        + data["token"]
        + "@"
        + provider["cfg"]["url"]
        + provider["cfg"]["urlprefix"]
        + "/public.php/webdav",
    }
    with app.app_context():
        r.table("users").get(user_id).update({"user_storage": user_storage}).run(
            db.conn
        )

    socketio.emit(
        "personal_unit",
        json.dumps(
            {
                "action": "Add user",
                "name": user_id,
                "status": True,
                "msg": "Finished",
            }
        ),
        namespace="/administrators",
        room="admins",
    )


########################
#   GROUPS MANAGEMENT  #
########################


# provider_list_groups = TTLCache(maxsize=10, ttl=60)


# @cached(provider_list_groups)
def _get_provider_groups(provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    groups = provider["conn"].get_groups()
    if provider["cfg"]["access"] == "*":
        groups.remove("admin")
        return groups
    return [
        g for g in groups if g in _get_isard_groups_array(provider_id) and g != "admin"
    ]


def user_storage_add_group_th(group_id, provider_id):
    gevent.spawn(
        user_storage_add_group,
        group_id,
        provider_id,
    )


def user_storage_add_group(group_id, provider_id=None):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    try:
        provider["conn"].add_group(group_id)
        provider["conn"].update_group(
            group_id, _get_isard_group_provider_name(group_id)
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add group",
                    "name": group_id,
                    "status": True,
                    "msg": "Added group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        app.logger.error(
            "USER_STORAGE - Add group. Error adding group {}".format(group_id)
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error adding group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_update_group_th(group_id, new_group_name, provider_id):
    gevent.spawn(
        user_storage_update_group,
        group_id,
        new_group_name,
        provider_id,
    )


def user_storage_update_group(group_id, new_group_name, provider_id):
    if _get_isard_group_provider_name(group_id) == new_group_name:
        app.logger.debug(
            "USER_STORAGE - Group name is the same, nothing to do: {} {}".format(
                _get_isard_group_provider_name(group_id), new_group_name
            )
        )
        return
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    app.logger.debug(
        "USER_STORAGE - Renaming group {} to {}".format(group_id, new_group_name)
    )
    # Update group
    try:
        provider["conn"].update_group(group_id, new_group_name)
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Update group",
                    "name": group_id,
                    "status": True,
                    "msg": "Updated group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error updating group {group_id} in user_storage provider",
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Update group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error updating group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_remove_group_th(group_id, provider_id, cascade=False):
    gevent.spawn(user_storage_remove_group, group_id, provider_id, cascade)


def user_storage_remove_group(group_id, provider_id, cascade=False):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    if cascade:
        provider_group_users = _provider_group_members(group_id, provider_id)
        process_user_storage_remove_user_batches(
            data_batch=provider_group_users, provider_id=provider_id
        )

    try:
        provider["conn"].remove_group(group_id)
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Delete group",
                    "name": group_id,
                    "status": True,
                    "msg": "Deleted group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Delete group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error deleting group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def _provider_group_members(group_id, provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    return provider["conn"].get_group_members(group_id)


########################
#   CATEGORY MANAGEMENT  #
########################


def user_storage_add_category_th(category_id, provider_id):
    gevent.spawn(
        user_storage_add_category,
        category_id,
        provider_id,
    )


def user_storage_add_category(category_id, provider_id=None):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    try:
        provider["conn"].add_group(category_id)
        provider["conn"].update_group(
            category_id, _get_isard_category_name(category_id)
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add category",
                    "name": category_id,
                    "status": True,
                    "msg": "Added group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )
    except:
        app.logger.error(
            f"USER_STORAGE - Error adding category {category_id} in user_storage provider",
        )
        socketio.emit(
            "personal_unit",
            json.dumps(
                {
                    "action": "Add category",
                    "name": category_id,
                    "status": False,
                    "msg": "Error adding group",
                }
            ),
            namespace="/administrators",
            room="admins",
        )


def user_storage_add_provider_categories_th(provider_id):
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return

    app.logger.info(
        "USER_STORAGE - Adding categories %s for provider %s"
        % (provider["cfg"]["access"], provider_id)
    )
    if provider["cfg"]["access"] != "*":
        gevent.spawn(user_storage_add_category, provider["cfg"]["access"], provider_id)
    else:
        process_user_storage_add_category_batches(
            _get_isard_categories_array(provider_id=provider_id),
            provider_id=provider_id,
        )


def user_storage_remove_category_th(category_id, cascade=False):
    gevent.spawn(user_storage_remove_category, category_id, cascade=cascade)


def user_storage_remove_category(category_id, cascade=False):
    provider_id = _get_isard_category_provider_id(category_id)
    provider = _get_provider(provider_id)
    if cascade:
        process_user_storage_remove_user_batches(
            data_batch=_provider_group_members(category_id, provider_id),
            provider_id=provider_id,
        )
        _get_provider_users_array.cache_clear()

        process_user_storage_remove_group_batches(
            data_batch=_get_provider_groups(provider_id), provider_id=provider_id
        )
    provider["conn"].remove_group(category_id)


def user_storage_update_category_th(category_id, new_category_name, provider_id):
    gevent.spawn(
        user_storage_update_category, category_id, new_category_name, provider_id
    )


def user_storage_update_category(category_id, new_category_name, provider_id):
    if _get_isard_category_name(category_id) == new_category_name:
        app.logger.debug(
            "USER_STORAGE - Category name is the same, nothing to do: {} {}".format(
                _get_isard_category_name(category_id), new_category_name
            )
        )
        return
    provider = _get_provider(provider_id)
    if not provider:
        # We will return as there are no providers defined in system
        return
    app.logger.debug(
        "USER_STORAGE - Renaming category {} to {}".format(
            _get_isard_category_name(category_id), new_category_name
        )
    )

    groups = _get_provider_groups(provider_id)
    groups_batch = []
    for group_id in groups:
        new_group_name = _get_isard_group_provider_name(group_id).replace(
            _get_isard_category_name(category_id), new_category_name
        )
        groups_batch.append([group_id, new_group_name])
    process_user_storage_update_group_batches(groups_batch, provider_id)
    provider["conn"].update_group(category_id, new_category_name)
