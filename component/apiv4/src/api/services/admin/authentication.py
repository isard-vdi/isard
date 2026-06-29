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

from typing import Optional

from api.services.error import Error
from cachetools import cached
from html_sanitizer import Sanitizer
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.lib.users.users.authentication import UsersAuthenticationProcessed
from isardvdi_common.lib.users.users.user_policies import UserPolicies
from isardvdi_common.models.config import Config


def sanitize_href(href: str | None) -> str | None:
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

provider_config_cache: SynchronizedTTLCache = SynchronizedTTLCache(maxsize=10, ttl=30)


class AdminAuthenticationService:

    # ── Policies ──────────────────────────────────────────────────────────

    @staticmethod
    def add_policy(data: dict) -> None:
        if data.get("category") != "all" and data.get("disclaimer"):
            raise Error(
                "bad_request",
                "Disclaimer option only available for all categories",
            )
        if UsersAuthenticationProcessed.has_duplicate_policy(
            data["category"], data["role"], data["type"]
        ):
            raise Error(
                "conflict",
                data["type"] + " policy for this category and role already exists",
            )
        UsersAuthenticationProcessed.insert_policy(data)

    @staticmethod
    def get_policies() -> list:
        return UsersAuthenticationProcessed.list_policies_with_category_name()

    @staticmethod
    def get_policy(policy_id: str) -> dict:
        return UsersAuthenticationProcessed.get_policy(policy_id)

    @staticmethod
    def edit_policy(policy_id: str, data: dict) -> None:
        UsersAuthenticationProcessed.update_policy(policy_id, data)

    @staticmethod
    def delete_policy(policy_id: str) -> None:
        policy = UsersAuthenticationProcessed.get_policy(policy_id)
        if (
            policy["role"] == "all"
            and policy["category"] == "all"
            and policy["type"] == "local"
        ):
            raise Error("forbidden", "Can not delete default permissions")
        UsersAuthenticationProcessed.delete_policy(policy_id)

    # ── Providers ─────────────────────────────────────────────────────────

    @staticmethod
    def get_providers() -> dict:
        # Global availability is the admin-toggled DB config (config.auth.<provider>.enabled), the source the global auth page reads
        auth = (Config.get_config() or {}).get("auth", {})
        return {
            provider: bool(auth.get(provider, {}).get("enabled", provider == "local"))
            for provider in ("local", "google", "saml", "ldap")
        }

    # ── Force validate at login ───────────────────────────────────────────

    @staticmethod
    def force_policy_at_login(policy_id: str, policy_field: str) -> None:
        policy = UsersAuthenticationProcessed.get_policy(policy_id)
        UsersAuthenticationProcessed.force_policy_at_login(policy, policy_field)

    # ── Disclaimer ────────────────────────────────────────────────────────

    @staticmethod
    def get_disclaimer_template(user_id: str) -> Optional[dict]:
        user = UsersAuthenticationProcessed.get_user_disclaimer_fields(user_id)
        policy = UserPolicies.get_user_policy(
            "disclaimer", "all", user["role"], user["provider"], user_id
        )
        template_id = policy.get("template") if policy else None
        if template_id:
            disclaimer = UsersAuthenticationProcessed.get_notification_template(
                template_id
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

    @staticmethod
    @cached(provider_config_cache)
    def get_provider_config(provider: str) -> dict:
        config = Config.get_admin_provider_config(provider)
        # Strip secrets from response
        _PROVIDER_SENSITIVE_KEYS = ("password", "client_secret")
        for key, value in config.items():
            if isinstance(value, dict):
                for secret_key in _PROVIDER_SENSITIVE_KEYS:
                    value.pop(secret_key, None)
        return config

    @staticmethod
    def update_provider_config(provider: str, data: dict) -> None:
        # Validate URL schemes for redirect URLs
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        for url_field in ("logout_redirect_url", "redirect_uri"):
            url_val = data.get(url_field, "")
            if url_val:
                # validate_url_scheme is framework-agnostic so it raises
                # plain ValueError. Convert to a typed 400 so the admin
                # sees the actual rejection reason instead of a generic
                # 500. Same fix as the login_config helper applied in
                # the validate_url_scheme sweep.
                try:
                    validate_url_scheme(url_val)
                except ValueError as e:
                    raise Error(
                        "bad_request",
                        str(e),
                        description_code=f"provider_config_{url_field}_invalid",
                    )
        # Strip empty secret fields so existing DB values are preserved
        for key in ("password", "client_secret"):
            if key in data and not data[key]:
                del data[key]
            if isinstance(data.get(provider), dict):
                if key in data[provider] and not data[provider][key]:
                    del data[provider][key]
        # Normalise the legacy "none"/"" action sentinel to null so the stored
        # config matches the API contract (only "disable"/"delete" act on the
        # account).
        migration = data.get("migration")
        if isinstance(migration, dict) and "action_after_migrate" in migration:
            if migration["action_after_migrate"] not in ("disable", "delete"):
                migration["action_after_migrate"] = None
        Config.update_provider_config(provider, data)
        provider_config_cache.clear()
        Caches.clear_config_cache()

    # ── Migration exceptions ──────────────────────────────────────────────

    @staticmethod
    def get_migrations_exceptions() -> list:
        return UsersAuthenticationProcessed.list_migration_exceptions_with_item_name()

    @staticmethod
    def add_migration_exception(data: dict) -> None:
        existing_ids = (
            UsersAuthenticationProcessed.get_existing_migration_exception_ids(
                data["item_ids"]
            )
        )
        new_item_ids = [
            item_id for item_id in data["item_ids"] if item_id not in existing_ids
        ]
        UsersAuthenticationProcessed.insert_migration_exceptions(
            data["item_type"], new_item_ids
        )

    @staticmethod
    def delete_migration_exception(exception_id: str) -> None:
        UsersAuthenticationProcessed.delete_migration_exception(exception_id)
