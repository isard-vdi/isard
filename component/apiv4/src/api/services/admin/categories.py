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

import html
import traceback

from api.services.error import Error
from api.services.login_config_cache import clear_login_config_cache, clear_logo_cache
from isardvdi_common.configuration import Configuration
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.category import Category
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.users.categories.categories import CategoriesProcessed

_PROVIDER_SENSITIVE_KEYS = ("password", "client_secret")
_KNOWN_PROVIDERS = ("local", "ldap", "google", "saml")


class AdminCategoryService:
    """Service for per-category branding, authentication, and login notification."""

    # ── Permission Checks ────────────────────────────────────────────────

    @staticmethod
    def _check_owns_and_permission(
        payload: dict, category_id: str, permission: str
    ) -> None:
        """Verify ownership and manager-level permission for a category."""
        Helpers.owns_category_id(payload, category_id)
        if payload["role_id"] == "admin":
            return
        perms = Category(category_id).manager_permissions or {}
        if not perms.get(permission):
            raise Error(
                "forbidden",
                f"Manager lacks '{permission}' permission for this category",
                description_code="insufficient_permissions",
            )

    # ── Branding ─────────────────────────────────────────────────────────

    @staticmethod
    def get_branding(payload: dict, category_id: str) -> dict:
        """Get category branding (domain + logo with injected data URL)."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "branding"
        )
        return Category(category_id).branding or {}

    @staticmethod
    def update_branding(payload: dict, category_id: str, data: dict) -> None:
        """Update category branding and surface relevant HAProxy sync failures.

        Persists the new branding via :class:`Category` (handles logo save +
        domain uniqueness validation), then triggers
        :meth:`Bastion.sync_category_branding_domains` and inspects the gRPC
        response. ACME failures matching the just-updated domain are raised
        as ``internal_server`` so the caller learns why their custom domain
        is not serving (silent swallow used to hide DNS-01 / TLS-ALPN
        misconfigurations behind a 200 OK). Failures on *other* categories'
        domains are logged but not surfaced — they're not this caller's
        responsibility.
        """
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "branding"
        )
        try:
            Category(category_id).branding = data
        except ValueError as e:
            raise Error("bad_request", str(e), description_code="branding_invalid")

        try:
            sync_result = Bastion.sync_category_branding_domains()
        except Error:
            raise
        except Exception as exc:
            raise Error(
                "internal_server",
                f"HAProxy domain sync failed: {exc}",
                traceback.format_exc(),
                description_code="branding_sync_failed",
            )

        updated_domain = (Category(category_id).branding or {}).get("domain") or {}
        if updated_domain.get("enabled") and updated_domain.get("name"):
            target = updated_domain["name"]
            relevant = [
                f for f in (sync_result.failed_domains or []) if f.domain == target
            ]
            if relevant:
                details = ", ".join(
                    f"{f.domain}: {Bastion.readable_sync_error(f.error)}"
                    for f in relevant
                )
                raise Error(
                    "internal_server",
                    f"HAProxy domain sync reported failures: {details}",
                    description_code="branding_sync_failed",
                )

        clear_logo_cache()

    # ── Authentication ───────────────────────────────────────────────────

    @staticmethod
    def get_authentication(payload: dict, category_id: str) -> dict:
        """Get category authentication with secrets stripped."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "authentication"
        )
        auth = Category(category_id).authentication or {}
        return _strip_authentication_secrets(auth)

    @staticmethod
    def update_authentication(payload: dict, category_id: str, data: dict) -> None:
        """Update category authentication.

        Preserves omitted/empty secrets from the DB (raising when a required one
        is absent), enforces the apiv3 structural rules, then writes via the
        Category setter (API→DB conversion).
        """
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "authentication"
        )
        auth = data.get("authentication") if isinstance(data, dict) else None
        if not isinstance(auth, dict):
            raise Error(
                "bad_request",
                "Missing or invalid 'authentication' object",
                description_code="authentication_invalid",
            )
        _preserve_authentication_secrets(
            auth, Category(category_id).authentication or {}
        )
        _validate_category_authentication(auth)
        Category(category_id).authentication = auth

    # ── Login Notification ───────────────────────────────────────────────

    @staticmethod
    def update_login_notification(payload: dict, category_id: str, data: dict) -> None:
        """Update per-category login notification configuration.

        The ORM setter replaces the whole `login_notification` attribute, so
        merge the partial payload into the stored value before writing.
        """
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "login_notification"
        )
        current = Category(category_id).login_notification or {}

        changed = False
        for position, key in (
            ("cover", "notification_cover"),
            ("form", "notification_form"),
        ):
            position_data = data.get(position)
            if position_data is None:
                continue
            if "enabled" not in position_data:
                position_data["enabled"] = current.get(key, {}).get("enabled", False)
            current[key] = position_data
            changed = True

        if not changed:
            return

        Category(category_id).login_notification = current

        clear_login_config_cache()

    @staticmethod
    def enable_login_notification(
        payload: dict, category_id: str, notification_type: str, enabled: bool
    ) -> None:
        """Enable or disable a specific category login notification type."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "login_notification"
        )
        current = Category(category_id).login_notification or {}
        key = f"notification_{notification_type}"
        notif = current.get(key, {})
        notif["enabled"] = enabled
        current[key] = notif
        Category(category_id).login_notification = current

        clear_login_config_cache()

    # ── Logo (public) ────────────────────────────────────────────────────

    @staticmethod
    def get_logo_by_domain(domain: str) -> str | None:
        """Get logo data URL for a domain. Falls back to default logo."""
        category = CategoriesProcessed.find_by_branding_domain(domain)
        if not category:
            return None
        return AdminCategoryService.get_logo_by_category(category["id"])

    @staticmethod
    def get_logo_by_category(category_id: str) -> str | None:
        """Get the branding logo data URL for a category, or None when disabled."""
        try:
            branding = Category(category_id).branding or {}
            logo = branding.get("logo", {})
            if logo.get("enabled") and logo.get("data"):
                return logo["data"]
        except Exception:
            pass
        return None

    @staticmethod
    def get_logo_collapsed_by_domain(domain: str) -> str | None:
        """Get the collapsed logo data URL for a domain, or None."""
        category = CategoriesProcessed.find_by_branding_domain(domain)
        if not category:
            return None
        return AdminCategoryService.get_logo_collapsed_by_category(category["id"])

    @staticmethod
    def get_logo_collapsed_by_category(category_id: str) -> str | None:
        """Get the collapsed branding logo data URL for a category, or None."""
        try:
            branding = Category(category_id).branding or {}
            logo = branding.get("logo_collapsed", {})
            if logo.get("enabled") and logo.get("data"):
                return logo["data"]
        except Exception:
            pass
        return None

    # ── Per-category login config ────────────────────────────────────────

    @staticmethod
    def get_login_config_for_category(category_id: str) -> dict:
        """Get login configuration for a category, merging global + category.

        Returns the same fields as ``GET /item/login-config``
        (``LoginConfigResponse``) but with ``notification_cover`` and
        ``notification_form`` as **lists** so the login page can render
        both the global notification and the category-specific one
        simultaneously. Pre-feature single-dict notifications are
        wrapped into 1-item lists.
        """
        login_config = Configuration().login or {}

        for key in ("notification_cover", "notification_form"):
            notification = login_config.get(key)
            if not notification:
                continue
            if not isinstance(notification, list):
                login_config[key] = [notification]

        try:
            category_login_config = Category(category_id).login_notification or {}
        except Exception:
            category_login_config = {}

        if category_login_config:
            login_config = {
                **login_config,
                **category_login_config,
                **{
                    "notification_cover": [
                        *(login_config.get("notification_cover") or []),
                        category_login_config.get("notification_cover"),
                    ],
                    "notification_form": [
                        *(login_config.get("notification_form") or []),
                        category_login_config.get("notification_form"),
                    ],
                },
            }

        for key in ("notification_cover", "notification_form"):
            notification = login_config.get(key)
            if not notification:
                continue
            for notification_item in notification:
                if not notification_item:
                    continue
                for field in ("title", "description"):
                    if notification_item.get(field) is not None:
                        notification_item[field] = html.unescape(
                            notification_item[field]
                        )
                button = notification_item.get("button")
                if isinstance(button, dict):
                    for field in ("text", "url"):
                        if button.get(field) is not None:
                            button[field] = html.unescape(button[field])

        return login_config

    @staticmethod
    def admin_get_login_config(category_id: str | None = None) -> dict:
        """Admin-only raw read of login config for editing.

        Returns the **unmerged** payload — global config when no category
        is supplied, the category's own ``login_notification`` row when
        a category id is given. Used by the webapp admin "Edit login
        notification" modal which needs to display the raw current
        state, not the merged user-facing view.
        """
        if category_id and Category.exists(category_id):
            login_config = Category(category_id).login_notification or {}
        else:
            login_config = Configuration().login or {}

        for key in ("notification_cover", "notification_form"):
            notification = login_config.get(key)
            if not isinstance(notification, dict):
                continue
            for field in ("title", "description"):
                if notification.get(field) is not None:
                    notification[field] = html.unescape(notification[field])
            button = notification.get("button")
            if isinstance(button, dict):
                for field in ("text", "url"):
                    if button.get(field) is not None:
                        button[field] = html.unescape(button[field])

        return login_config


def _strip_authentication_secrets(auth: dict) -> dict:
    """Strip sensitive keys from authentication config, replacing with _set booleans."""
    for provider_data in auth.values():
        if not isinstance(provider_data, dict):
            continue
        for config in provider_data.values():
            if not isinstance(config, dict):
                continue
            for key in _PROVIDER_SENSITIVE_KEYS:
                if key in config:
                    config[f"{key}_set"] = bool(config.pop(key))
    return auth


def _preserve_authentication_secrets(new_auth: dict, existing_auth: dict) -> dict:
    """Preserve existing sensitive fields when the caller omitted or left them empty.

    For every provider in ``new_auth`` (e.g. ``ldap``, ``google``), walks each
    nested config dict (e.g. ``ldap_config``) and, for each sensitive key
    (``password``, ``client_secret``), keeps the existing value from
    ``existing_auth`` when the new payload provides an empty / falsy value.
    If the payload omits the key entirely, this is left untouched so the
    caller's intent is preserved. Mirrors apiv3: an empty secret with no
    stored value to fall back on is rejected as required.
    """
    for provider_name, provider_data in new_auth.items():
        if not isinstance(provider_data, dict):
            continue
        for config_key, config_data in provider_data.items():
            if not isinstance(config_data, dict):
                continue
            for secret_key in _PROVIDER_SENSITIVE_KEYS:
                if secret_key not in config_data:
                    continue
                if config_data[secret_key]:
                    continue
                existing_val = (
                    existing_auth.get(provider_name, {})
                    .get(config_key, {})
                    .get(secret_key)
                    if isinstance(existing_auth, dict)
                    else None
                )
                if existing_val:
                    config_data[secret_key] = existing_val
                else:
                    raise Error(
                        "bad_request",
                        f"{secret_key} is required",
                        description_code="authentication_secret_required",
                    )


def _validate_category_authentication(auth: dict) -> None:
    """Reject the same incomplete payloads as the apiv3 Cerberus schema.

    Mirrors v3's per-provider ``depends_if`` co-requirements (presence-based);
    unknown providers pass through for forward compatibility.
    """

    def _require(condition: bool, message: str) -> None:
        if not condition:
            raise Error(
                "bad_request", message, description_code="authentication_invalid"
            )

    for provider, provider_data in auth.items():
        if provider not in _KNOWN_PROVIDERS:
            continue
        _require(
            isinstance(provider_data, dict),
            f"'{provider}' authentication must be an object",
        )

        disabled = provider_data.get("disabled")
        _require(
            isinstance(disabled, bool), f"'{provider}' requires a boolean 'disabled'"
        )

        config_source = provider_data.get("config_source")
        edr = provider_data.get("email_domain_restriction")

        if disabled is False:
            _require(
                edr is not None and config_source is not None,
                f"'{provider}' requires 'email_domain_restriction' and "
                "'config_source' when enabled",
            )

        if config_source is not None:
            _require(
                config_source in ("global", "custom"),
                f"'{provider}' config_source must be 'global' or 'custom'",
            )

        if isinstance(edr, dict):
            _require(
                isinstance(edr.get("enabled"), bool),
                f"'{provider}' email_domain_restriction requires a boolean 'enabled'",
            )
            if edr["enabled"]:
                _require(
                    "allowed" in edr,
                    f"'{provider}' email_domain_restriction requires 'allowed' "
                    "when enabled",
                )

        config = provider_data.get(f"{provider}_config")
        config = config if isinstance(config, dict) else {}
        edr_enabled = isinstance(edr, dict) and edr.get("enabled") is True

        if provider == "google" and config_source == "custom":
            _require(
                "google_config" in provider_data,
                "'google' requires 'google_config' when config_source is custom",
            )

        if provider == "ldap":
            if config_source == "custom":
                _require(
                    "ldap_config" in provider_data,
                    "'ldap' requires 'ldap_config' when config_source is custom",
                )
            if edr_enabled:
                _require(
                    "field_email" in config,
                    "'ldap' requires 'ldap_config.field_email' when email domain "
                    "restriction is enabled",
                )
            if config.get("auto_register") and config.get("group_default", "") == "":
                _require(
                    "field_group" in config,
                    "'ldap' requires 'ldap_config.field_group' when auto-registering "
                    "without a default group",
                )

        if provider == "saml":
            if config_source == "custom":
                _require(
                    "metadata_url" in config or "metadata_file" in config,
                    "'saml' requires 'saml_config.metadata_url' or "
                    "'saml_config.metadata_file' when config_source is custom",
                )
            if edr_enabled:
                _require(
                    "field_email" in config,
                    "'saml' requires 'saml_config.field_email' when email domain "
                    "restriction is enabled",
                )
            if config.get("auto_register"):
                if config.get("group_default", "") == "":
                    _require(
                        "field_group" in config,
                        "'saml' requires 'saml_config.field_group' when "
                        "auto-registering without a default group",
                    )
                if config.get("role_default", "") == "":
                    _require(
                        "field_role" in config,
                        "'saml' requires 'saml_config.field_role' when "
                        "auto-registering without a default role",
                    )
