#
#   Copyright © 2025 IsardVDI
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
from typing import Optional

from api.services.error import Error
from cachetools import TTLCache, cached
from html_sanitizer import Sanitizer
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.lib.users.users.user_policies import UserPolicies
from rethinkdb import r


def sanitize_href(href):
    if href:
        scheme = href.strip().lower().split(":")[0] if ":" in href else ""
        if scheme in ("javascript", "data", "vbscript"):
            return None
    return href


sanitizer = Sanitizer(
    {
        "attributes": {"a": ("href", "name", "target", "title", "id", "rel", "class")},
        "tags": {
            "a",
            "h1",
            "h2",
            "h3",
            "h4",
            "strong",
            "em",
            "p",
            "ul",
            "ol",
            "li",
            "br",
            "sub",
            "sup",
            "hr",
        },
        "sanitize_href": sanitize_href,
    }
)

provider_config_cache = TTLCache(maxsize=10, ttl=30)


class AdminAuthenticationService(RethinkSharedConnection):

    _rdb_table = "authentication"

    # ── Policies ──────────────────────────────────────────────────────────

    @classmethod
    def add_policy(cls, data: dict) -> None:
        if data.get("category") != "all" and data.get("disclaimer"):
            raise Error(
                "bad_request",
                "Disclaimer option only available for all categories",
            )
        if not cls._check_duplicate_policy(
            data["category"], data["role"], data["type"]
        ):
            raise Error(
                "conflict",
                data["type"] + " policy for this category and role already exists",
            )
        with cls._rdb_context():
            r.table(cls._rdb_table).insert(data).run(cls._rdb_connection)

    @classmethod
    def get_policies(cls) -> list:
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .merge(
                    lambda policy: {
                        "category_name": (
                            r.branch(
                                policy["category"] == "all",
                                "all",
                                r.table("categories")
                                .get(policy["category"])
                                .default({"name": "[DELETED]"})["name"],
                            )
                        )
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_policy(cls, policy_id: str) -> dict:
        with cls._rdb_context():
            policy = r.table(cls._rdb_table).get(policy_id).run(cls._rdb_connection)
        if policy is None:
            # Without this every caller (delete_policy /
            # force_policy_at_login / edit_policy) crashes with
            # ``TypeError: 'NoneType' is not subscriptable`` and
            # surfaces as a generic 500 instead of a typed 404.
            raise Error(
                "not_found",
                f"Authentication policy {policy_id} not found",
                description_code="auth_policy_not_found",
            )
        return policy

    @classmethod
    def edit_policy(cls, policy_id: str, data: dict) -> None:
        with cls._rdb_context():
            r.table(cls._rdb_table).get(policy_id).update(data).run(cls._rdb_connection)

    @classmethod
    def delete_policy(cls, policy_id: str) -> None:
        policy = cls.get_policy(policy_id)
        if (
            policy["role"] == "all"
            and policy["category"] == "all"
            and policy["type"] == "local"
        ):
            raise Error("forbidden", "Can not delete default permissions")
        with cls._rdb_context():
            r.table(cls._rdb_table).get(policy_id).delete().run(cls._rdb_connection)

    @classmethod
    def _check_duplicate_policy(cls, category: str, role: str, type: str) -> bool:
        with cls._rdb_context():
            return (
                len(
                    list(
                        r.table(cls._rdb_table)
                        .get_all([category, role], index="category-role")
                        .filter({"type": type})
                        .run(cls._rdb_connection)
                    )
                )
                <= 0
            )

    # ── Providers ─────────────────────────────────────────────────────────

    @staticmethod
    def get_providers() -> dict:
        providers = {}
        providers["local"] = not (
            os.environ.get("AUTHENTICATION_AUTHENTICATION_LOCAL_ENABLED") == "false"
        )
        providers["google"] = (
            os.environ.get("AUTHENTICATION_AUTHENTICATION_GOOGLE_ENABLED") == "true"
        )
        providers["saml"] = (
            os.environ.get("AUTHENTICATION_AUTHENTICATION_SAML_ENABLED") == "true"
        )
        providers["ldap"] = (
            os.environ.get("AUTHENTICATION_AUTHENTICATION_LDAP_ENABLED") == "true"
        )
        return providers

    # ── Force validate at login ───────────────────────────────────────────

    @classmethod
    def force_policy_at_login(cls, policy_id: str, policy_field: str) -> None:
        policy = cls.get_policy(policy_id)
        query = r.table("users").get_all(policy["type"], index="provider")
        if policy["category"] != "all":
            query = query.filter({"category": policy["category"]})
        if policy["role"] != "all":
            query = query.filter({"role": policy["role"]})
        with cls._rdb_context():
            query.update({policy_field: None}).run(cls._rdb_connection)

    # ── Disclaimer ────────────────────────────────────────────────────────

    @classmethod
    def get_disclaimer_template(cls, user_id: str) -> Optional[dict]:
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("role", "lang", "provider")
                .run(cls._rdb_connection)
            )
        policy = UserPolicies.get_user_policy(
            "disclaimer", "all", user["role"], user["provider"], user_id
        )
        template_id = policy.get("template") if policy else None
        if template_id:
            with cls._rdb_context():
                disclaimer = (
                    r.table("notification_tmpls")
                    .get(template_id)
                    .run(cls._rdb_connection)
                )
            if disclaimer["lang"].get(user.get("lang")):
                texts = disclaimer["lang"][user["lang"]]
                return {
                    "title": texts["title"],
                    "body": sanitizer.sanitize(texts["body"]),
                    "footer": sanitizer.sanitize(texts["footer"]),
                }
            elif disclaimer["lang"].get(disclaimer["default"]):
                texts = disclaimer["lang"][disclaimer["default"]]
                return {
                    "title": texts["title"],
                    "body": sanitizer.sanitize(texts["body"]),
                    "footer": sanitizer.sanitize(texts["footer"]),
                }
            raise Error("not_found", "Unable to find disclaimer template")
        else:
            return None

    # ── Provider config ───────────────────────────────────────────────────

    @classmethod
    @cached(provider_config_cache)
    def get_provider_config(cls, provider: str) -> dict:
        try:
            with cls._rdb_context():
                config = (
                    r.table("config").get(1)["auth"][provider].run(cls._rdb_connection)
                )
        except Exception:
            raise Error("not_found", "Provider config not found")
        try:
            with cls._rdb_context():
                config["migration"]["notification_bar"]["template_name"] = (
                    r.table("notification_tmpls")
                    .get(config["migration"]["notification_bar"]["template"])["name"]
                    .run(cls._rdb_connection)
                )
        except r.ReqlNonExistenceError:
            config["template_name"] = "[DELETED]"
        # Strip secrets from response
        _PROVIDER_SENSITIVE_KEYS = ("password", "client_secret")
        for key, value in config.items():
            if isinstance(value, dict):
                for secret_key in _PROVIDER_SENSITIVE_KEYS:
                    value.pop(secret_key, None)
        return config

    @classmethod
    def update_provider_config(cls, provider: str, data: dict) -> None:
        # Validate URL schemes for redirect URLs
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        for url_field in ("logout_redirect_url", "redirect_uri"):
            url_val = data.get(url_field, "")
            if url_val:
                validate_url_scheme(url_val)
        # Strip empty secret fields so existing DB values are preserved
        for key in ("password", "client_secret"):
            if key in data and not data[key]:
                del data[key]
            if isinstance(data.get(provider), dict):
                if key in data[provider] and not data[provider][key]:
                    del data[provider][key]
        with cls._rdb_context():
            r.table("config").get(1).update(
                {"auth": {provider: r.row["auth"][provider].merge(data)}}
            ).run(cls._rdb_connection)
        provider_config_cache.clear()
        Caches.clear_config_cache()

    # ── Migration exceptions ──────────────────────────────────────────────

    @classmethod
    def get_migrations_exceptions(cls) -> list:
        with cls._rdb_context():
            return list(
                r.table("users_migrations_exceptions")
                .merge(
                    lambda exception: {
                        "item_name": r.table(exception["item_type"]).get(
                            exception["item_id"]
                        )["name"]
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def add_migration_exception(cls, data: dict) -> None:
        with cls._rdb_context():
            existing_ids = set(
                r.table("users_migrations_exceptions")
                .get_all(*data["item_ids"], index="item_id")["item_id"]
                .run(cls._rdb_connection)
            )
        new_items = [
            {
                "item_type": data["item_type"],
                "item_id": item_id,
                "created_at": r.now(),
            }
            for item_id in data["item_ids"]
            if item_id not in existing_ids
        ]
        if new_items:
            with cls._rdb_context():
                r.table("users_migrations_exceptions").insert(new_items).run(
                    cls._rdb_connection
                )

    @classmethod
    def delete_migration_exception(cls, exception_id: str) -> None:
        with cls._rdb_context():
            r.table("users_migrations_exceptions").get(exception_id).delete().run(
                cls._rdb_connection
            )
