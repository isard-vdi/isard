#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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
import logging as log
import os
import secrets
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from math import ceil

from cachetools import cached
from cachetools.keys import hashkey
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.connections.user_storage_providers.nextcloud import (
    Helpers as NextcloudHelpers,
)
from isardvdi_common.connections.user_storage_providers.nextcloud import NextcloudApi
from isardvdi_common.helpers.api_notify import notify_admins
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r

ISARD_SHARE_FOLDER = "IsardVDI"


isard_groups_cache = SynchronizedTTLCache(maxsize=10, ttl=5)
cache_provider = SynchronizedTTLCache(maxsize=10, ttl=5)

_isard_user_storage_get_users_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=10, ttl=5
)

# The login-auth watcher is one-at-a-time: a fresh
# ``isard_user_storage_provider_login_auth`` call signals the previous
# watcher to stop via the ``Event`` and joins it before starting a new
# thread. Replaces a ``login_thread = gevent.spawn(...)`` /
# ``login_thread.kill()`` pattern that was unsafe under apiv4.
_login_thread: "threading.Thread | None" = None
_login_thread_stop: threading.Event = threading.Event()


def _spawn_daemon(target, *args, **kwargs) -> threading.Thread:
    """Fire-and-forget a sync ``target`` on a daemon thread.

    Replaces the prior ``gevent.spawn(target, *args, **kwargs)`` pattern.
    Under apiv4 (FastAPI on uvicorn/asyncio) the gevent Hub was never
    driven by the asyncio worker, so spawned greenlets silently never
    ran — the same root cause as the SIGSEGV documented in
    ``APIV4_THREADING_INCIDENT_ANALYSIS.md``. A daemon thread runs the
    target on its own OS thread, doesn't block process exit, and is
    framework-agnostic (works under sync Flask/waitress, asyncio, and
    plain CLI scripts alike).

    Exceptions raised by the target are surfaced via stderr by the
    threading runtime; we deliberately do not wrap with try/except
    here because the original ``gevent.spawn`` semantics also did not
    intercept the target's exception.
    """
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread


def _spawn_daemon_later(
    delay_seconds: float, target, *args, **kwargs
) -> threading.Timer:
    """Fire-and-forget a sync ``target`` on a daemon ``Timer`` thread
    after ``delay_seconds``.

    Replaces ``gevent.spawn_later(delay_seconds, target, *args, **kwargs)``.
    The returned ``Timer`` is started and marked daemon; callers that
    need to cancel the pending fire can keep the reference and call
    ``.cancel()``.
    """
    timer = threading.Timer(delay_seconds, target, args=args, kwargs=kwargs)
    timer.daemon = True
    timer.start()
    return timer


def _run_batches_in_pool(
    target, batches, *args, max_workers: int = 10, **kwargs
) -> None:
    """Run ``target(batch, *args, **kwargs)`` over ``batches`` in a
    bounded ``ThreadPoolExecutor``, blocking until all batches finish.

    Replaces the prior ``[gevent.spawn(target, batch, …) for batch in
    batches]; gevent.joinall(jobs)`` fan-out pattern. Under apiv4
    (FastAPI on uvicorn/asyncio) ``gevent.joinall`` blocked the
    asyncio loop on libev's ``ev_run`` and was the most likely UAF
    trigger documented in ``APIV4_THREADING_INCIDENT_ANALYSIS.md``.

    Exceptions raised by individual batches are logged and swallowed
    here (matching the prior ``gevent.joinall(raise_error=False)``
    semantics — callers do not handle per-batch failures and we don't
    want one bad batch to abort the rest).
    """
    if not batches:
        return
    workers = min(max_workers, len(batches))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(target, batch, *args, **kwargs) for batch in batches]
        for future in futures:
            try:
                future.result()
            except Exception:
                log.error(
                    "USER_STORAGE batch %s raised: %s",
                    target.__name__,
                    traceback.format_exc(),
                )


class UserStorage(RethinkSharedConnection):

    ########################
    # IsardVDI Interface   #
    ########################

    ## GET

    @classmethod
    @cached(cache=_isard_user_storage_get_users_cache)
    def isard_user_storage_get_users(cls):
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )
        for pu in provider_users:
            pu["group_name"] = cls._get_isard_group_provider_name(pu["group"])
            pu["category_name"] = cls._get_isard_category_name(pu["category"])
        return provider_users

    @classmethod
    def clear_isard_user_storage_get_users_cache(cls):
        _isard_user_storage_get_users_cache.clear()

    ## ADD
    @classmethod
    def isard_user_storage_add_user(cls, user_id):
        try:
            cls.user_storage_add_user_th_later(
                user_id,
                provider_id=cls._get_isard_user_provider_id(user_id),
                create_groups=False,
                webdav_folder=True,
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error adding user {user_id} to user_storage provider"
            )

    @classmethod
    def isard_user_storage_add_group(cls, group_id):
        try:
            cls.user_storage_add_group_th(
                group_id,
                cls._get_isard_group_provider_id(group_id),
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error adding group {group_id} to user_storage provider"
            )

    @classmethod
    def isard_user_storage_add_category(cls, category_id):
        try:
            cls.user_storage_add_category_th(
                category_id,
                cls._get_isard_category_provider_id(category_id),
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error adding category {category_id} to user_storage provider"
            )

    ## ENABLE
    @classmethod
    def isard_user_storage_enable_users(cls, users):
        for user in users:
            try:
                cls.user_storage_enable_user_th(
                    user["id"],
                    True,
                    cls._get_isard_category_provider_id(user["category"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling user {user['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_enable_groups(cls, groups):
        for group in groups:
            try:
                cls.user_storage_enable_group_th(
                    group["id"],
                    True,
                    cls._get_isard_category_provider_id(group["parent_category"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling group {group['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_enable_categories(cls, categories):
        for category in categories:
            try:
                cls.user_storage_enable_category_th(
                    category["id"],
                    True,
                    cls._get_isard_category_provider_id(category["id"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling category {category['id']} in user_storage provider"
                )

    ## DISABLE
    @classmethod
    def isard_user_storage_disable_users(cls, users):
        for user in users:
            try:
                cls.user_storage_enable_user_th(
                    user["id"],
                    False,
                    cls._get_isard_category_provider_id(user["category"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling user {user['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_disable_groups(cls, groups):
        for group in groups:
            try:
                cls.user_storage_enable_group_th(
                    group["id"],
                    False,
                    cls._get_isard_category_provider_id(group["parent_category"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling group {group['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_disable_categories(cls, categories):
        for category in categories:
            try:
                cls.user_storage_enable_category_th(
                    category["id"],
                    False,
                    cls._get_isard_category_provider_id(category["id"]),
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error enabling category {category['id']} in user_storage provider"
                )

    ## REMOVE
    @classmethod
    def isard_user_storage_remove_users(cls, users):
        for user in users:
            try:
                cls.user_storage_remove_user_th(
                    user["id"], cls._get_isard_category_provider_id(user["category"])
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error removing user {user['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_remove_groups(cls, groups):
        for group in groups:
            try:
                cls.user_storage_remove_group_th(
                    group["id"],
                    cls._get_isard_category_provider_id(group["parent_category"]),
                    cascade=True,
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error removing group {group['id']} in user_storage provider"
                )

    @classmethod
    def isard_user_storage_remove_categories(cls, categories, groups):
        for category in categories:
            try:
                cls.user_storage_remove_category_th(
                    category,
                    groups,
                    cls._get_isard_category_provider_id(category["id"]),
                    cascade=True,
                )
            except Exception as e:
                log.error(
                    f"USER_STORAGE - Error removing category {category['id']} in user_storage provider"
                )

    ## UPDATE
    @classmethod
    def isard_user_storage_update_user(
        cls,
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
                cls.user_storage_update_user_th(
                    user_id,
                    password=password,
                    quota_MB=quota_MB,
                    email=email,
                    displayname=displayname,
                    role=role,
                )
            if enabled != None:
                cls.user_storage_enable_user_th(user_id, enabled)
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating user {user_id} in user_storage provider"
            )

    @classmethod
    def isard_user_storage_update_group(cls, group_id, group_name):
        try:
            cls.user_storage_update_group_th(
                group_id,
                cls._get_isard_group_category_name(group_id) + "--" + group_name,
                cls._get_isard_group_provider_id(group_id),
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating group {group_id} in user_storage provider"
            )

    @classmethod
    def isard_user_storage_update_category(cls, category_id, category_name):
        try:
            cls.user_storage_update_category_th(
                category_id,
                category_name,
                cls._get_isard_category_provider_id(category_id),
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating category {category_id} in user_storage provider"
            )

    @classmethod
    def isard_user_storage_update_user_quota(cls, user_id):
        # Now it is only updated when user logins (frontend gets Config)
        # TODO: Think where we can also update it...
        try:
            cls.user_storage_update_user_quota_th(user_id)
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating user {user_id} quota in user_storage provider"
            )

    ## ADMIN SYNCS
    @classmethod
    def isard_user_storage_sync_users(cls, provider_id):
        cls.user_storage_provider_users_sync(provider_id)

    @classmethod
    def isard_user_storage_sync_groups(cls, provider_id):
        cls.user_storage_provider_groups_sync(provider_id)

    ## ADMIN PROVIDERS

    @classmethod
    def isard_user_storage_get_provider(cls, provider_id):
        if not provider_id:
            return None
        try:
            with cls._rdb_context():
                provider = (
                    r.table("user_storage").get(provider_id).run(cls._rdb_connection)
                )
            if provider:
                provider["authorization"] = bool(provider.get("password"))
                provider.pop("password", None)
            return provider
        except Exception:
            return None

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=1, ttl=3))
    def isard_user_storage_get_providers(cls):
        with cls._rdb_context():
            providers = list(r.table("user_storage").run(cls._rdb_connection))
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
    @classmethod
    def get_ws_connection_status(cls, provider):
        try:
            cls.isard_user_storage_provider_basic_auth_test(
                provider["provider"],
                "pepito",
                provider["urlprefix"],
                provider["user"],
                provider["password"],
                provider["verify_cert"],
            )
            provider["connection"] = True
        except Exception as e:
            log.debug(
                f"USER_STORAGE - Error testing connection to provider {provider['id']}: {e}"
            )
            log.error(
                f"USER_STORAGE - Error testing connection to provider {provider['id']}"
            )
            provider["connection"] = False
        notify_admins(
            "user_storage_provider",
            {
                "id": provider["id"],
                "connection": provider["connection"],
            },
        )
        if provider["connection"]:
            new_users, deleted_users = cls.get_users_inconsistency(provider["id"])
            new_groups, deleted_groups = cls.get_groups_inconsistency(provider["id"])
            new_categories, deleted_categories = cls.get_categories_inconsistency(
                provider["id"]
            )
            new_groups = new_groups + new_categories
            deleted_groups = deleted_groups + deleted_categories
            notify_admins(
                "user_storage_provider",
                {
                    "id": provider["id"],
                    "new_users": len(new_users),
                    "deleted_users": len(deleted_users),
                    "new_groups": len(new_groups),
                    "deleted_groups": len(deleted_groups),
                },
            )

    @classmethod
    def isard_user_storage_get_providers_ws(cls):
        with cls._rdb_context():
            providers = list(r.table("user_storage").run(cls._rdb_connection))
        new_providers = []
        for provider in providers:
            if provider["access"] == []:
                provider["category_names"] = []
            else:
                with cls._rdb_context():
                    provider["category_names"] = (
                        r.table("categories")
                        .get_all(r.args(provider["access"]))["name"]
                        .coerce_to("array")
                        .run(cls._rdb_connection)
                    )
            if not provider.get("password"):
                provider["authorization"] = False
                provider["connection"] = False
            else:
                provider["authorization"] = True
                # Check connection Thread
                _spawn_daemon_later(0.5, cls.get_ws_connection_status, provider.copy())
            provider.pop("password", None)
            new_providers.append(provider)
        return new_providers

    @classmethod
    def isard_user_storage_provider_reset(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        cls.process_user_storage_remove_user_batches(
            data_batch=cls._get_provider_users_array(provider_id),
            provider_id=provider_id,
        )
        provider_groups = cls._get_provider_groups(
            provider_id
        ) + cls._get_provider_categories(provider_id)
        cls.process_user_storage_remove_group_batches(
            data_batch=provider_groups, provider_id=provider_id
        )

        for category_id in provider["cfg"]["access"]:
            provider["conn"].remove_group(category_id)

        # Get users from db that matches this provider access
        query = r.table("users")
        if provider["cfg"]["access"] != []:
            query = query.get_all(r.args(provider["cfg"]["access"]), index="category")
        with cls._rdb_context():
            query.replace(r.row.without("user_storage")).run(cls._rdb_connection)

    @classmethod
    def isard_user_storage_provider_delete(cls, provider_id):
        try:
            cls.isard_user_storage_provider_reset(provider_id)
        except Exception:
            pass
        with cls._rdb_context():
            r.table("user_storage").get(provider_id).delete().run(
                cls._rdb_connection
            ).get("deleted")

    @classmethod
    def isard_user_storage_reset_all(cls):
        users = []
        groups = []
        provider_id = None
        for provider_db in cls.isard_user_storage_get_providers():
            provider = cls._get_provider(provider_db["id"])
            conn = provider.get("conn") if provider else None
            if conn is None:
                continue
            users = list(set(users + conn.get_users()))
            groups = list(set(groups + conn.get_groups()))
            provider_id = provider_db["id"]
        if provider_id is None:
            return
        cls.process_user_storage_remove_user_batches(users, provider_id)
        cls.process_user_storage_remove_group_batches(groups, provider_id)

    @classmethod
    def isard_user_storage_provider_basic_auth_test(
        cls, provider, domain, urlprefix, user, password, verify_cert
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

    @classmethod
    def isard_user_storage_provider_auto_register_auth(
        cls, domain, user, password, intra_docker, verify_cert
    ):
        provider_id = [
            p["id"]
            for p in cls.isard_user_storage_get_providers()
            if p["url"] == domain
        ]
        if provider_id:
            with cls._rdb_context():
                r.table("user_storage").get(provider_id[0]).update(
                    {
                        "user": user,
                        "password": password,
                        "intra_docker": intra_docker,
                        "verify_cert": verify_cert,
                    }
                ).run(cls._rdb_connection)
            return provider_id[0]
        with cls._rdb_context():
            provider_id = (
                r.table("user_storage")
                .insert(
                    {
                        "provider": "nextcloud",
                        "name": domain,
                        "description": "Connection to Nextcloud instance inside IsardVDI containers",
                        "url": domain,
                        "urlprefix": "/isard-nc",
                        "access": [],
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
                .run(cls._rdb_connection)["changes"][0]["new_val"]["id"]
            )
        return provider_id

    @classmethod
    def isard_user_storage_provider_basic_auth_add(
        cls,
        provider,
        name,
        description,
        domain,
        urlprefix,
        access,
        quota,
        verify_cert,
    ):
        with cls._rdb_context():
            provider_id = (
                r.table("user_storage")
                .insert(
                    {
                        "provider": provider,
                        "name": name,
                        "description": description,
                        "url": domain,
                        "urlprefix": urlprefix,
                        "access": (
                            access
                            if type(access) == list
                            else [access] if access != "*" else []
                        ),
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
                .run(cls._rdb_connection)["changes"][0]["new_val"]["id"]
            )
        return provider_id

    @classmethod
    def isard_user_storage_provider_login_auth_socketio(
        cls,
        provider_id,
        stop_event: "threading.Event | None" = None,
    ):
        """Poll the ``user_storage`` row until the admin sets a
        password (i.e. authorises the provider) or the 5-minute
        deadline expires.

        Originally this used ``gevent.Timeout(5 * 60)`` around a
        rethinkdb ``.changes()`` feed; under apiv4's asyncio worker
        the gevent Hub never ran, so the watcher silently never fired.
        The poll-with-deadline pattern is framework-agnostic — it
        works under apiv4 (called from a daemon ``threading.Thread``),
        webapp (Flask + waitress), and CLI scripts alike. See
        APIV4_THREADING_INCIDENT_ANALYSIS.md §3 Tier-C / §5.7.
        """
        deadline = time.monotonic() + 5 * 60
        log.info("USER_STORAGE - Waiting for admin to authorize provider")
        while time.monotonic() < deadline:
            if stop_event is not None and stop_event.is_set():
                log.info(
                    "USER_STORAGE - Login-auth watcher for %s cancelled",
                    provider_id,
                )
                return
            try:
                with cls._rdb_context():
                    row = (
                        r.table("user_storage")
                        .get(provider_id)
                        .pluck("password")
                        .run(cls._rdb_connection)
                    )
            except Exception:
                row = None
            if row and row.get("password"):
                notify_admins(
                    "user_storage_provider",
                    {
                        "id": provider_id,
                        "authorization": True,
                        "connection": True,
                    },
                )
                log.info(f"USER_STORAGE - Admin authorized provider {provider_id}")
                return
            # Honour cancellation during the sleep too.
            if stop_event is not None:
                if stop_event.wait(timeout=2):
                    return
            else:
                time.sleep(2)
        log.warning(
            f"USER_STORAGE - Timeout when waiting for admin to authorize provider {provider_id}"
        )

    @classmethod
    def isard_user_storage_provider_login_auth(
        cls,
        provider_id,
    ):
        global _login_thread, _login_thread_stop
        if _login_thread is not None and _login_thread.is_alive():
            # Signal the previous watcher to exit and wait briefly for
            # it to finish; replaces the unsafe ``login_thread.kill()``
            # call which under gevent could leave libev watchers in a
            # half-freed state under apiv4 (see incident analysis).
            _login_thread_stop.set()
            _login_thread.join(timeout=5)
        _login_thread_stop = threading.Event()
        _login_thread = threading.Thread(
            target=cls.isard_user_storage_provider_login_auth_socketio,
            args=(provider_id, _login_thread_stop),
            daemon=True,
        )
        _login_thread.start()
        return NextcloudHelpers.start_login_auth(provider_id)

    ####################
    # GENERIC QUERIES #
    ####################

    ## Users generic queries

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=50, ttl=5))
    def _get_isard_user_info(cls, user_id):
        with cls._rdb_context():
            return (
                r.table("users")
                .get(user_id)
                .pluck(
                    "id", "name", "role", "group", "category", "user_storage", "email"
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def _get_isard_user_name(cls, user_id):
        return cls._get_isard_user_info(user_id)["name"]

    @classmethod
    def _get_isard_user_email(cls, user_id):
        return cls._get_isard_user_info(user_id)["email"]

    @classmethod
    def _get_isard_user_role(cls, user_id):
        return cls._get_isard_user_info(user_id)["role"]

    @classmethod
    def _get_isard_user_group_id(cls, user_id):
        return cls._get_isard_user_info(user_id)["group"]

    @classmethod
    def _get_isard_user_category_id(cls, user_id):
        return cls._get_isard_user_info(user_id)["category"]

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_isard_users_array(cls, provider_id=None):
        provider = cls._get_provider(provider_id)
        if provider["cfg"]["access"] != []:
            with cls._rdb_context():
                return (
                    r.table("users")
                    .get_all(r.args(provider["cfg"]["access"]), index="category")
                    .pluck("id")["id"]
                    .coerce_to("array")
                    .run(cls._rdb_connection)
                )
        else:
            with cls._rdb_context():
                return (
                    r.table("users")
                    .pluck("id")["id"]
                    .coerce_to("array")
                    .run(cls._rdb_connection)
                )

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_provider_users_array(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        if provider["cfg"]["access"] == []:
            return provider["conn"].get_users()
        group_members = []
        for category_id in provider["cfg"]["access"]:
            group_members += provider["conn"].get_group_members(category_id)
        return group_members

    ## Groups generic queries

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_isard_group_info(cls, group_id):
        with cls._rdb_context():
            group = r.table("groups").get(group_id).run(cls._rdb_connection)
        with cls._rdb_context():
            category_name = (
                r.table("categories")
                .get(group["parent_category"])["name"]
                .run(cls._rdb_connection)
            )
        return {
            "id": group["id"],
            "name": group["name"],
            "parent_category": group["parent_category"],
            "category_name": category_name,
        }

    @classmethod
    def _get_isard_group_category_name(cls, group_id):
        return cls._get_isard_group_info(group_id)["category_name"]

    @classmethod
    def _get_isard_group_provider_name(cls, group_id):
        return (
            cls._get_isard_group_category_name(group_id)
            + "--"
            + cls._get_isard_group_info(group_id)["name"]
        )

    @classmethod
    @cached(isard_groups_cache)
    def _get_isard_groups_array(cls, provider_id):
        provider = cls._get_provider(provider_id)
        query = r.table("groups")
        if provider["cfg"]["access"] != []:
            query = query.get_all(
                r.args(provider["cfg"]["access"]), index="parent_category"
            )
        with cls._rdb_context():
            return list(
                query.pluck("id")["id"].coerce_to("array").run(cls._rdb_connection)
            )

    ## Categories generic queries

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_isard_category_name(cls, category_id):
        with cls._rdb_context():
            return (
                r.table("categories").get(category_id)["name"].run(cls._rdb_connection)
            )

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_isard_categories_array(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if provider["cfg"]["access"] != []:
            return provider["cfg"]["access"]
        with cls._rdb_context():
            return (
                r.table("categories")
                .pluck("id")["id"]
                .coerce_to("array")
                .run(cls._rdb_connection)
            )

    ########################
    # PROVIDERS MANAGEMENT #
    ########################

    @classmethod
    @cached(cache_provider)
    def _get_provider(cls, provider_id, user_id=None):
        provider_cfg = cls.isard_user_storage_get_provider(provider_id)
        if not provider_cfg:
            return None
        if not provider_cfg.get("enabled"):
            log.debug("USER_STORAGE - User storage provider not enabled in system.")
            return None
        if not provider_cfg.get("password"):
            log.debug("USER_STORAGE - User storage provider not authorized yet.")
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
                user = cls._get_isard_user_info(user_id)
                if user.get("user_storage", {}).get("password"):
                    provider.set_webdav_auth(
                        user["user_storage"]["user_id"],
                        user["user_storage"]["password"],
                    )
            return {"cfg": provider_cfg, "conn": provider}
        return None

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _get_isard_category_provider_id(cls, category_id):
        with cls._rdb_context():
            # Get provider that has category_id in access field array
            providers_cfgs = list(
                r.table("user_storage")
                .filter(lambda doc: doc["access"].contains(category_id))
                .run(cls._rdb_connection)
            )
        if len(providers_cfgs):
            # Should be only one, and should be controlled in the UI
            provider_cfg = providers_cfgs[0]
        else:
            provider_cfg = None
            with cls._rdb_context():
                provider = list(
                    r.table("user_storage")
                    .filter({"access": []})
                    .run(cls._rdb_connection)
                )
            if len(provider):
                provider_cfg = provider[0]

        if not provider_cfg:
            return None
        return provider_cfg["id"]

    @classmethod
    def _get_isard_group_provider_id(cls, group_id):
        return cls._get_isard_category_provider_id(
            cls._get_isard_group_info(group_id)["parent_category"]
        )

    @classmethod
    def _get_isard_user_provider_id(cls, user_id):
        return cls._get_isard_category_provider_id(
            cls._get_isard_user_info(user_id)["category"]
        )

    ### BATCH Add/Remove Users in batches with greenlets threads

    @classmethod
    def get_users_inconsistency(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        isard_users = cls._get_isard_users_array(provider_id)
        provider_users = cls._get_provider_users_array(provider_id)

        new_users = [iu for iu in isard_users if iu not in provider_users]
        removed_users = [pu for pu in provider_users if pu not in isard_users]
        return new_users, removed_users

    @classmethod
    def process_user_storage_add_user_batch(
        cls, data_batch, provider_id, create_groups, webdav_folder
    ):
        for item_id in data_batch:
            cls.user_storage_add_user(
                user_id=item_id,
                provider_id=provider_id,
                create_groups=create_groups,
                webdav_folder=webdav_folder,
            )

    @classmethod
    def process_user_storage_add_user_batches(
        cls, data_batch, provider_id, create_groups, webdav_folder
    ):
        if not len(data_batch):
            log.debug("USER_STORAGE - No users to add to provider")
            return

        if create_groups:
            cls.user_storage_add_provider_categories_th(provider_id)
            cls.process_user_storage_add_group_batches(
                data_batch=cls._get_isard_groups_array(provider_id),
                provider_id=provider_id,
                skip_if_exists=True,
            )

        # Number of simultaneous users that can be created
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> ADD %s USERS TO PROVIDER IN %s BATCHES OF %s USERS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_add_user_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
            create_groups=False,
            webdav_folder=webdav_folder,
        )

    @classmethod
    def process_user_storage_enable_user_batch(cls, data_batch, enabled, provider_id):
        # Spawn a greenlet for each item in the batch
        for item_id in data_batch:
            cls.user_storage_enable_user(
                user_id=item_id,
                enabled=enabled,
                provider_id=provider_id,
            )

    @classmethod
    def process_user_storage_enable_user_batches(cls, data_batch, enabled, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No users to disable")
            return
        # Number of simultaneous users that can be disabled
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> DISABLE %s USERS IN PROVIDER IN %s BATCHES OF %s USERS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_enable_user_batch,
            batches,
            enabled,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def process_user_storage_remove_user_batch(cls, data_batch, provider_id):
        # Spawn a greenlet for each item in the batch
        for item_id in data_batch:
            cls.user_storage_remove_user(
                user_id=item_id,
                provider_id=provider_id,
            )

    @classmethod
    def process_user_storage_remove_user_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No users to remove to provider")
            return
        # Number of simultaneous users that can be removed
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> REMOVE %s USERS IN PROVIDER IN %s BATCHES OF %s USERS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_remove_user_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def process_user_storage_add_user_subadmin_batch(cls, data_batch, provider_id):
        provider = cls._get_provider(provider_id)
        for item_id in data_batch:
            try:
                provider["conn"].add_subadmin(user_id=item_id[0], group_id=item_id[1])
            except Exception:
                log.error(
                    f"USER_STORAGE - Error adding subadmin user {item_id[0]} in group {item_id[1]} in user_storage provider",
                )
                notify_admins(
                    "personal_unit",
                    {
                        "action": "Add subadmin",
                        "name": item_id[0],
                        "status": False,
                        "msg": "Error adding subadmin",
                    },
                )

    @classmethod
    def process_user_storage_add_user_subadmin_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No subadins to add to user")
            return
        # Number of simultaneous groups that can be removed
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> ADD %s SUBADMINS TO USER IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_add_user_subadmin_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def process_user_storage_delete_subadmin_batch(cls, data_batch, provider_id):
        provider = cls._get_provider(provider_id)
        for item_id in data_batch:
            try:
                provider["conn"].delete_subadmin(
                    user_id=item_id[0], group_id=item_id[1]
                )
            except Exception:
                log.error(
                    f"USER_STORAGE - Error deleting subadmin user {item_id[0]} in group {item_id[1]} in user_storage provider",
                )
                notify_admins(
                    "personal_unit",
                    {
                        "action": "Delete subadmin",
                        "name": item_id[0],
                        "status": False,
                        "msg": "Error deleting subadmin",
                    },
                )

    @classmethod
    def process_user_storage_delete_subadmin_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No subadmins to delete from user")
            return
        # Number of simultaneous groups that can be removed
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> DELETE %s SUBADMINS FROM USER IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_delete_subadmin_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def user_storage_provider_users_sync(cls, provider_id):
        new_users, removed_users = cls.get_users_inconsistency(provider_id)
        cls.process_user_storage_add_user_batches(
            data_batch=new_users,
            provider_id=provider_id,
            create_groups=True,
            webdav_folder=True,
        )
        cls.process_user_storage_remove_user_batches(
            data_batch=removed_users, provider_id=provider_id
        )

    ### BATCH Add/Update/Remove Groups in batches with greenlets threads

    @classmethod
    def get_groups_inconsistency(cls, provider_id):
        # Get groups from provider
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        provider_groups = cls._get_provider_groups(provider_id)
        isard_groups = cls._get_isard_groups_array(provider_id)
        new_groups = [ig for ig in isard_groups if ig not in provider_groups]
        removed_groups = [pg for pg in provider_groups if pg not in isard_groups]
        log.debug(
            f"USER_STORAGE - GET GROUPS INCONSISTENDY - NEW GROUPS {new_groups} - REMOVED GROUPS {removed_groups}"
        )
        return new_groups, removed_groups

    @classmethod
    def get_categories_inconsistency(cls, provider_id):
        # Get groups from provider
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        provider_categories = cls._get_provider_categories(provider_id)
        isard_categories = cls._get_isard_categories_array(provider_id)
        new_categories = [
            ig for ig in isard_categories if ig not in provider_categories
        ]
        removed_categories = [
            pg for pg in provider_categories if pg not in isard_categories
        ]
        log.debug(
            f"USER_STORAGE - GET CATEGORIES INCONSISTENDY - NEW CATEGORIES {new_categories} - REMOVED CATEGORIES {removed_categories}"
        )
        return new_categories, removed_categories

    @classmethod
    def process_user_storage_add_group_batch(
        cls, data_batch, provider_id, skip_if_exists=False
    ):
        for item_id in data_batch:
            cls.user_storage_add_group(
                group_id=item_id,
                provider_id=provider_id,
                skip_if_exists=skip_if_exists,
            )

    @classmethod
    def process_user_storage_add_group_batches(
        cls, data_batch, provider_id, skip_if_exists=False
    ):
        if not len(data_batch):
            log.debug("USER_STORAGE - No groups to add to provider")
            return
        # Number of simultaneous groups that can be created
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> ADD %s GROUPS TO PROVIDER IN %s BATCHES OF %s GROUPS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_add_group_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
            skip_if_exists=skip_if_exists,
        )

    @classmethod
    def process_user_storage_update_group_batch(cls, data_batch, provider_id):
        for item_id in data_batch:
            cls.user_storage_update_group(
                group_id=item_id[0],
                new_group_name=item_id[1],
                provider_id=provider_id,
            )

    @classmethod
    def process_user_storage_update_group_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No groups to update to provider")
            return
        # Number of simultaneous groups that can be created
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> UPDATE %s GROUPS TO PROVIDER IN %s BATCHES OF %s GROUPS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_update_group_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def process_user_storage_remove_group_batch(cls, data_batch, provider_id):
        for item_id in data_batch:
            cls.user_storage_remove_group(group_id=item_id, provider_id=provider_id)

    @classmethod
    def process_user_storage_remove_group_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No groups to remove to provider")
            return
        # Number of simultaneous groups that can be removed
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> REMOVE %s GROUPS IN PROVIDER IN %s BATCHES OF %s GROUPS EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_remove_group_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    @classmethod
    def user_storage_provider_groups_sync(cls, provider_id):
        cls.user_storage_add_provider_categories_th(provider_id)
        new_groups, removed_groups = cls.get_groups_inconsistency(provider_id)
        cls.process_user_storage_add_group_batches(
            data_batch=new_groups, provider_id=provider_id
        )

        cls.process_user_storage_remove_group_batches(
            data_batch=removed_groups, provider_id=provider_id
        )

    ### BATCH Add Categories in batches with greenlets threads

    @classmethod
    def process_user_storage_add_category_batch(cls, data_batch, provider_id):
        for item_id in data_batch:
            cls.user_storage_add_category(
                category_id=item_id,
                provider_id=provider_id,
            )

    @classmethod
    def process_user_storage_add_category_batches(cls, data_batch, provider_id):
        if not len(data_batch):
            log.debug("USER_STORAGE - No categories to add to provider")
            return
        # Number of simultaneous categories that can be created
        max_batch_threads = 10
        batch_size = ceil(len(data_batch) / max_batch_threads)

        batches = [
            data_batch[i : i + batch_size]
            for i in range(0, len(data_batch), batch_size)
        ]

        log.info(
            "USER_STORAGE ==> ADD %s CATEGORIES TO PROVIDER IN %s BATCHES OF %s CATEGORIES EACH"
            % (len(data_batch), len(batches), batch_size)
        )

        _run_batches_in_pool(
            cls.process_user_storage_add_category_batch,
            batches,
            provider_id,
            max_workers=max_batch_threads,
        )

    ########################
    #   USERS MANAGEMENT   #
    ########################

    ## Add/Update/Remove users

    @classmethod
    def user_storage_add_user_th_later(
        cls, user_id, provider_id=None, create_groups=False, webdav_folder=True
    ):
        # Wait 1 second before adding to let user be in database for sure
        _spawn_daemon_later(
            1,
            cls.user_storage_add_user,
            user_id,
            provider_id,
            create_groups,
            webdav_folder,
        )

    @classmethod
    def user_storage_add_user_th(
        cls, user_id, provider_id=None, create_groups=False, webdav_folder=True
    ):
        # This is the function to be called when adding a new user through the web interface, to not block the creation
        _spawn_daemon(
            cls.user_storage_add_user,
            user_id,
            provider_id,
            create_groups,
            webdav_folder,
        )

    @classmethod
    def user_storage_add_user(
        cls, user_id, provider_id, create_groups=False, webdav_folder=True
    ):
        # This function is called when adding a new user in bulk, as it blocks the calling loop
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        if create_groups:
            cls.user_storage_add_group(
                group_id=cls._get_isard_user_group_id(user_id),
                provider_id=provider_id,
                skip_if_exists=True,
            )

        password = secrets.token_urlsafe(20)
        log.info("USER_STORAGE ==> ADD USER %s TO PROVIDER %s" % (user_id, provider_id))
        try:
            provider["conn"].add_user(
                user_id,
                password,
                provider["cfg"]["quota"].get(cls._get_isard_user_role(user_id)),
                groups=[
                    cls._get_isard_user_category_id(user_id),
                    cls._get_isard_user_group_id(user_id),
                ],
                email=cls._get_isard_user_email(user_id),
                displayname=cls._get_isard_user_name(user_id),
            )
            cls.user_storage_update_user_subadmin(
                user_id, cls._get_isard_user_role(user_id), provider_id
            )
            user_storage = {
                "user_id": user_id,
                "password": password,
                "web": "https://"
                + provider["cfg"]["url"]
                + provider["cfg"]["urlprefix"],
                "dav": provider["cfg"]["url"]
                + provider["cfg"]["urlprefix"]
                + "/remote.php/webdav/"
                + ISARD_SHARE_FOLDER,
                "tls": True,
                "verify_cert": provider["cfg"]["verify_cert"],
                "provider_id": provider["cfg"]["id"],
                "quota": provider["cfg"]["quota"].get(
                    cls._get_isard_user_role(user_id)
                ),
                "provider_quota": provider["conn"].get_user_quota(user_id),
            }
            if not webdav_folder:
                with cls._rdb_context():
                    r.table("users").get(user_id).update(
                        {"user_storage": user_storage}
                    ).run(cls._rdb_connection)
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
            with cls._rdb_context():
                r.table("users").get(user_id).update(
                    {"user_storage": user_storage}
                ).run(cls._rdb_connection)

            notify_admins(
                "personal_unit",
                {
                    "action": "Add user",
                    "name": user_id,
                    "status": True,
                    "msg": "Added user",
                },
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error adding user {user_id} in user_storage provider",
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user",
                },
            )

    @classmethod
    def user_storage_remove_user_th(cls, user_id, provider_id):
        _spawn_daemon(cls.user_storage_remove_user, user_id, provider_id)

    @classmethod
    def user_storage_remove_user(cls, user_id, provider_id):
        # The isard database user removal should be be done before this
        if user_id == "admin":
            return
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        try:
            provider["conn"].remove_user(user_id)
            notify_admins(
                "personal_unit",
                {
                    "action": "Delete user",
                    "name": user_id,
                    "status": True,
                    "msg": "Deleted user",
                },
            )
        except Error as e:
            if e.status_code == 404:
                log.error(
                    f"USER_STORAGE - User storage remove user {user_id} not found in user_storage provider"
                )
        except Exception:
            log.error(
                f"USER_STORAGE - User storage remove user {user_id} in user_storage provider internal error"
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Delete user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error deleting user",
                },
            )

    @classmethod
    def user_storage_update_user_th(
        cls,
        user_id,
        password=None,
        quota_MB=None,
        email=None,
        displayname=None,
        role=None,
    ):
        _spawn_daemon(
            cls.user_storage_update_user,
            user_id,
            password=password,
            quota_MB=quota_MB,
            email=email,
            displayname=displayname,
            role=role,
        )

    @classmethod
    def user_storage_update_user(
        cls,
        user_id,
        password=None,
        quota_MB=None,
        email=None,
        displayname=None,
        role=None,
    ):
        provider = cls._get_provider(cls._get_isard_user_provider_id(user_id))
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
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating user: {user_id} in user_storage provider",
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Update user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error updating user",
                },
            )

        cls.user_storage_update_user_subadmin(user_id, role, provider["cfg"]["id"])

        notify_admins(
            "personal_unit",
            {
                "action": "Update user",
                "name": user_id,
                "status": True,
                "msg": "Updated user",
            },
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

        with cls._rdb_context():
            r.table("users").get(user_id).update({"user_storage": user_storage}).run(
                cls._rdb_connection
            )

    @classmethod
    def user_storage_enable_user_th(cls, user_id, enabled, provider_id=None):
        _spawn_daemon(cls.user_storage_enable_user, user_id, enabled, provider_id)

    @classmethod
    def user_storage_enable_user(cls, user_id, enabled, provider_id=None):
        if provider_id:
            provider = cls._get_provider(provider_id)
        else:
            # We will return as there are no providers defined in system
            return
        try:
            if enabled == False:
                provider["conn"].disable_user(user_id)
            if enabled == True:
                provider["conn"].enable_user(user_id)
        except Exception as e:
            log.debug(f"USER_STORAGE - Error enabling user: {e}")
            log.error(
                f"USER_STORAGE - Error enabling user: {user_id} in user_storage provider",
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Enable user",
                    "name": user_id,
                    "status": False,
                    "msg": "Error enabling user",
                },
            )

        notify_admins(
            "personal_unit",
            {
                "action": "Enable user",
                "name": user_id,
                "status": True,
                "msg": "Enabled user",
            },
        )

    @classmethod
    def user_storage_update_user_subadmin(cls, user_id, role, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        user_subadmin_groups = provider["conn"].get_user(user_id).get("subadmin", [])
        groups_add = []
        groups_delete = []
        if role == "admin":
            # We should add user to all groups and categories
            for group_id in cls._get_provider_categories(provider_id):
                if group_id not in user_subadmin_groups:
                    groups_add.append([user_id, group_id])
            for group_id in cls._get_provider_groups(provider_id):
                if group_id not in user_subadmin_groups:
                    groups_add.append([user_id, group_id])
        if role == "manager":
            category_id = cls._get_isard_user_category_id(user_id)
            # We should remove user from groups and categories if his category does not match
            # the user_subadmin_groups
            if category_id not in user_subadmin_groups:
                for group_id in user_subadmin_groups:
                    groups_delete.append([user_id, group_id])
            # We should add user to his category and and to this category groups
            if (
                provider["cfg"]["access"] == []
                or category_id in provider["cfg"]["access"]
            ):
                groups_add.append([user_id, category_id])
                for group_id in cls._get_provider_groups(provider_id):
                    if group_id not in user_subadmin_groups:
                        groups_add.append([user_id, group_id])
        if role not in ["admin", "manager"]:
            for group_id in user_subadmin_groups:
                try:
                    groups_delete.append([user_id, group_id])
                except Exception:
                    pass

        if len(groups_delete) > 0:
            log.debug(
                f"USER_STORAGE - DELETING SUBADMINS: {groups_delete} for user {user_id}"
            )
            cls.process_user_storage_delete_subadmin_batches(groups_delete, provider_id)
        if len(groups_add) > 0:
            log.debug(
                f"USER_STORAGE - ADDING SUBADMINS: {groups_add} for user {user_id}"
            )
            cls.process_user_storage_add_user_subadmin_batches(groups_add, provider_id)

    ## Users quota

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def user_storage_quota(cls, user_id):
        provider = cls._get_provider(cls._get_isard_user_provider_id(user_id))
        if not provider:
            # We will return as there are no providers defined in system
            return

        return provider["conn"].get_user_quota(user_id)

    @classmethod
    def user_storage_update_user_quota_th(cls, user_id):
        _spawn_daemon(cls.user_storage_update_user_quota, user_id)

    @classmethod
    def user_storage_update_user_quota(cls, user_id):
        provider = cls._get_provider(cls._get_isard_user_provider_id(user_id))
        if not provider:
            # We will return as there are no providers defined in system
            return
        try:
            provider_quota = provider["conn"].get_user_quota(user_id)
        except Exception as e:
            # "not_found" means the user does not exist yet in the provider; skip
            # silently. Any other exception must propagate — swallowing them
            # hides real provider outages.
            is_not_found = (isinstance(e, Error) and e.status_code == 404) or (
                e.args and e.args[0] == "not_found"
            )
            if is_not_found:
                ## TODO: User does not exist yet in provider, we should add it here?
                return
            raise
        with cls._rdb_context():
            r.table("users").get(user_id).update(
                {"user_storage": {"provider_quota": provider_quota}}
            ).run(cls._rdb_connection)

    @classmethod
    def user_storage_quota_update(cls, user_id):
        user_storage_quota = cls.user_storage_quota(user_id)
        if not user_storage_quota:
            # We will return as there are no providers defined in system
            return
        with cls._rdb_context():
            r.table("users").get(user_id).update(
                {"user_storage": {"provider_quota": user_storage_quota}}
            ).run(cls._rdb_connection)
        return user_storage_quota

    ## Users folders

    @classmethod
    def user_storage_add_user_folder(cls, user_id, folder=ISARD_SHARE_FOLDER):
        provider = cls._get_provider(cls._get_isard_user_provider_id(user_id))
        user = cls._get_isard_user_info(user_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        # Add user folder
        try:
            provider["conn"].add_user_folder(
                user_id, user["user_storage"]["password"], folder
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add user folder",
                    "name": user_id,
                    "status": True,
                    "msg": "Added user folder",
                },
            )
        except Exception:
            notify_admins(
                "personal_unit",
                {
                    "action": "Add user folder",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user folder",
                },
            )

    @classmethod
    def user_storage_add_user_share_folder(cls, user_id, folder=ISARD_SHARE_FOLDER):
        provider = cls._get_provider(cls._get_isard_user_provider_id(user_id))
        user = cls._get_isard_user_info(user_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        try:
            data = provider["conn"].add_user_share_folder(
                user["id"], user["user_storage"]["password"], folder
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add user share folder",
                    "name": user["id"],
                    "status": True,
                    "msg": "Added user share folder",
                },
            )
        except Exception:
            notify_admins(
                "personal_unit",
                {
                    "action": "Add user share folder",
                    "name": user_id,
                    "status": False,
                    "msg": "Error adding user share folder: the folder does not exist.",
                },
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
        with cls._rdb_context():
            r.table("users").get(user_id).update({"user_storage": user_storage}).run(
                cls._rdb_connection
            )

        notify_admins(
            "personal_unit",
            {
                "action": "Add user",
                "name": user_id,
                "status": True,
                "msg": "Finished",
            },
        )

    ########################
    #   GROUPS MANAGEMENT  #
    ########################

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=10, ttl=5))
    def _provider_groups(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        # In provider get_groups we have all groups, including categories nextcloud has only groups)
        groups = provider["conn"].get_groups()
        if provider["cfg"]["access"] == []:
            groups.remove("admin")
        return groups

    @classmethod
    def _get_provider_groups(cls, provider_id):
        # Remove categories (as they won't be in isard groups)
        return [
            g
            for g in cls._provider_groups(provider_id)
            if g in cls._get_isard_groups_array(provider_id) and g != "admin"
        ]

    @classmethod
    def _get_provider_categories(cls, provider_id):
        # Remove categories (as they won't be in isard groups)
        return [
            g
            for g in cls._provider_groups(provider_id)
            if g in cls._get_isard_categories_array(provider_id)
        ]

    @classmethod
    def _get_category_groups(cls, category_id):
        provider = cls._get_provider(cls._get_isard_category_provider_id(category_id))
        groups = provider["conn"].get_group_members(category_id)
        log.error(groups)
        if "admin" in groups:
            groups.remove("admin")
        log.error(groups)

        return groups

    @classmethod
    def user_storage_add_group_th(cls, group_id, provider_id):
        _spawn_daemon(
            cls.user_storage_add_group,
            group_id,
            provider_id,
        )

    @classmethod
    def user_storage_add_group(cls, group_id, provider_id=None, skip_if_exists=False):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        try:
            provider["conn"].add_group(group_id, skip_if_exists=skip_if_exists)
            provider["conn"].update_group(
                group_id, cls._get_isard_group_provider_name(group_id)
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add group",
                    "name": group_id,
                    "status": True,
                    "msg": "Added group",
                },
            )
        except Exception as e:
            log.debug(
                f"USER_STORAGE - Error adding group {group_id} in user_storage provider: {traceback.format_exc()}"
            )
            log.error(
                "USER_STORAGE - Add group. Error adding group {}".format(group_id)
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error adding group",
                },
            )

    @classmethod
    def user_storage_update_group_th(cls, group_id, new_group_name, provider_id):
        _spawn_daemon(
            cls.user_storage_update_group,
            group_id,
            new_group_name,
            provider_id,
        )

    @classmethod
    def user_storage_update_group(cls, group_id, new_group_name, provider_id):
        if cls._get_isard_group_provider_name(group_id) == new_group_name:
            log.debug(
                "USER_STORAGE - Group name is the same, nothing to do: {} {}".format(
                    cls._get_isard_group_provider_name(group_id), new_group_name
                )
            )
            return
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        log.debug(
            "USER_STORAGE - Renaming group {} to {}".format(group_id, new_group_name)
        )
        # Update group
        try:
            provider["conn"].update_group(group_id, new_group_name)
            notify_admins(
                "personal_unit",
                {
                    "action": "Update group",
                    "name": group_id,
                    "status": True,
                    "msg": "Updated group",
                },
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error updating group {group_id} in user_storage provider",
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Update group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error updating group",
                },
            )

    @classmethod
    def user_storage_enable_group_th(cls, group_id, enabled, provider_id=None):
        _spawn_daemon(cls.user_storage_enable_group, group_id, enabled, provider_id)

    @classmethod
    def user_storage_enable_group(cls, group_id, enabled, provider_id=None):
        if not provider_id:
            # We will return as there are no providers defined in system
            return
        provider_group_users = cls._provider_group_members(group_id, provider_id)
        cls.process_user_storage_enable_user_batches(
            data_batch=provider_group_users, enabled=enabled, provider_id=provider_id
        )

    @classmethod
    def user_storage_remove_group_th(cls, group_id, provider_id, cascade=False):
        _spawn_daemon(cls.user_storage_remove_group, group_id, provider_id, cascade)

    @classmethod
    def user_storage_remove_group(cls, group_id, provider_id, cascade=False):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        if cascade:
            provider_group_users = cls._provider_group_members(group_id, provider_id)
            cls.process_user_storage_remove_user_batches(
                data_batch=provider_group_users, provider_id=provider_id
            )

        try:
            provider["conn"].remove_group(group_id)
            notify_admins(
                "personal_unit",
                {
                    "action": "Delete group",
                    "name": group_id,
                    "status": True,
                    "msg": "Deleted group",
                },
            )
        except Exception:
            notify_admins(
                "personal_unit",
                {
                    "action": "Delete group",
                    "name": group_id,
                    "status": False,
                    "msg": "Error deleting group",
                },
            )

    @classmethod
    def _provider_group_members(cls, group_id, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        return provider["conn"].get_group_members(group_id)

    ########################
    #   CATEGORY MANAGEMENT  #
    ########################

    @classmethod
    def user_storage_add_category_th(cls, category_id, provider_id):
        _spawn_daemon(
            cls.user_storage_add_category,
            category_id,
            provider_id,
        )

    @classmethod
    def user_storage_add_category(cls, category_id, provider_id=None):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        try:
            provider["conn"].add_group(category_id)
            provider["conn"].update_group(
                category_id, cls._get_isard_category_name(category_id)
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add category",
                    "name": category_id,
                    "status": True,
                    "msg": "Added group",
                },
            )
        except Exception:
            log.error(
                f"USER_STORAGE - Error adding category {category_id} in user_storage provider",
            )
            notify_admins(
                "personal_unit",
                {
                    "action": "Add category",
                    "name": category_id,
                    "status": False,
                    "msg": "Error adding group",
                },
            )

    @classmethod
    def user_storage_add_provider_categories_th(cls, provider_id):
        _spawn_daemon(cls.user_storage_add_provider_categories, provider_id)

    @classmethod
    def user_storage_add_provider_categories(cls, provider_id):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        if provider["cfg"]["access"] == []:
            categories = cls._get_isard_categories_array(provider_id)
        else:
            categories = provider["cfg"]["access"]
        log.info(
            "USER_STORAGE - Adding categories %s for provider %s"
            % (categories, provider_id)
        )
        cls.process_user_storage_add_category_batches(
            categories,
            provider_id=provider_id,
        )

    @classmethod
    def user_storage_enable_category_th(cls, category_id, enabled, provider_id=None):
        _spawn_daemon(
            cls.user_storage_enable_category, category_id, enabled, provider_id
        )

    @classmethod
    def user_storage_enable_category(cls, group_id, enabled, provider_id=None):
        if not provider_id:
            # We will return as there are no providers defined in system
            return
        provider_group_users = cls._provider_group_members(group_id, provider_id)
        cls.process_user_storage_enable_user_batches(
            data_batch=provider_group_users, enabled=enabled, provider_id=provider_id
        )

    @classmethod
    def user_storage_remove_category_th(
        cls, category, groups, provider_id, cascade=False
    ):
        _spawn_daemon(
            cls.user_storage_remove_category,
            category,
            groups,
            provider_id,
            cascade=cascade,
        )

    @classmethod
    def user_storage_remove_category(cls, category, groups, provider_id, cascade=False):
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return

        if cascade:
            cls.process_user_storage_remove_user_batches(
                data_batch=cls._provider_group_members(category["id"], provider_id),
                provider_id=provider_id,
            )
            cls._get_provider_users_array.cache_clear()
            ## Should only be groups in category_id!!
            cls.process_user_storage_remove_group_batches(
                data_batch=groups,
                provider_id=provider_id,
            )
        provider["conn"].remove_group(category["id"])

    @classmethod
    def user_storage_update_category_th(
        cls, category_id, new_category_name, provider_id
    ):
        _spawn_daemon(
            cls.user_storage_update_category,
            category_id,
            new_category_name,
            provider_id,
        )

    @classmethod
    def user_storage_update_category(cls, category_id, new_category_name, provider_id):
        cls._get_isard_category_name.cache_clear()
        category_name = cls._get_isard_category_name(category_id)
        if category_name == new_category_name:
            log.debug(
                "USER_STORAGE - Category name is the same, nothing to do: {} {}".format(
                    category_name, new_category_name
                )
            )
            return
        provider = cls._get_provider(provider_id)
        if not provider:
            # We will return as there are no providers defined in system
            return
        log.debug(
            "USER_STORAGE - Renaming category {} to {}".format(
                category_name, new_category_name
            )
        )

        groups = cls._get_category_groups(category_id)
        groups_batch = []
        for group_id in groups:
            new_group_name = cls._get_isard_group_provider_name(group_id).replace(
                category_name, new_category_name
            )
            groups_batch.append([group_id, new_group_name])
        cls.process_user_storage_update_group_batches(groups_batch, provider_id)
        provider["conn"].update_group(category_id, new_category_name)
