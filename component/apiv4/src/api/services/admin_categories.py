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

from api.services.error import Error
from isardvdi_common.configuration import Configuration
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.category import Category
from isardvdi_common.helpers.helpers import Helpers

_PROVIDER_SENSITIVE_KEYS = ("password", "client_secret")


class AdminCategoryService:
    """Service for per-category branding, authentication, and login notification."""

    # ── Permission Checks ────────────────────────────────────────────────

    @staticmethod
    def _check_owns_and_permission(payload, category_id, permission):
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
    def get_branding(payload, category_id):
        """Get category branding (domain + logo with injected data URL)."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "branding"
        )
        return Category(category_id).branding or {}

    @staticmethod
    def update_branding(payload, category_id, data):
        """Update category branding. Category class handles logo save and domain validation."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "branding"
        )
        try:
            Category(category_id).branding = data
        except ValueError as e:
            raise Error("bad_request", str(e), description_code="branding_invalid")
        try:
            Bastion.sync_category_branding_domains()
        except Exception:
            import logging

            logging.getLogger(__name__).warning(
                "Failed to sync branding domains to HAProxy after update"
            )

        from api.routes.open import clear_logo_cache

        clear_logo_cache()

    # ── Authentication ───────────────────────────────────────────────────

    @staticmethod
    def get_authentication(payload, category_id):
        """Get category authentication with secrets stripped."""
        AdminCategoryService._check_owns_and_permission(
            payload, category_id, "authentication"
        )
        auth = Category(category_id).authentication or {}
        return _strip_authentication_secrets(auth)

    @staticmethod
    def update_authentication(payload, category_id, data):
        """Update category authentication.

        Checks the manager `authentication` permission, preserves any sensitive
        field (password, client_secret) that the caller omitted or left empty in
        the payload by reading the current value from the DB, then delegates to
        the Category setter which handles API→DB conversion of provider configs.
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
        Category(category_id).authentication = auth

    # ── Login Notification ───────────────────────────────────────────────

    @staticmethod
    def update_login_notification(payload, category_id, data):
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

        from api.routes.open import clear_login_config_cache

        clear_login_config_cache()

    @staticmethod
    def enable_login_notification(payload, category_id, notification_type, enabled):
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

        from api.routes.open import clear_login_config_cache

        clear_login_config_cache()

    # ── Logo (public) ────────────────────────────────────────────────────

    @staticmethod
    def get_logo_by_domain(domain):
        """Get logo data URL for a domain. Falls back to default logo."""
        from isardvdi_common.connections.rethink_connection_factory import (
            RethinkSharedConnection,
        )
        from rethinkdb import r

        try:
            with RethinkSharedConnection._rdb_context():
                categories = list(
                    r.table("categories")
                    .filter(
                        lambda cat: cat.has_fields({"branding": {"domain": True}})
                        & (cat["branding"]["domain"]["name"] == domain)
                        & (cat["branding"]["domain"]["enabled"] == True)
                    )
                    .limit(1)
                    .run(RethinkSharedConnection._rdb_connection)
                )
        except Exception:
            return None
        if categories:
            try:
                branding = Category(categories[0]["id"]).branding or {}
                logo = branding.get("logo", {})
                if logo.get("enabled") and logo.get("data"):
                    return logo["data"]
            except Exception:
                pass
        return None

    # ── Per-category login config ────────────────────────────────────────

    @staticmethod
    def get_login_config_for_category(category_id):
        """Get login configuration for a category, falling back to global.

        Returns the same flat shape as ``GET /item/login-config``
        (``LoginConfigResponse``) so the same frontend helpers can consume
        both endpoints.
        """
        try:
            login_notification = Category(category_id).login_notification
        except Exception:
            login_notification = None
        if login_notification:
            login_config = login_notification
        else:
            login_config = Configuration().login or {}

        for key in ("notification_cover", "notification_form"):
            notif = login_config.get(key)
            if not isinstance(notif, dict):
                continue
            for field in ("title", "description"):
                if notif.get(field) is not None:
                    notif[field] = html.unescape(notif[field])
            button = notif.get("button")
            if isinstance(button, dict):
                for field in ("text", "url"):
                    if button.get(field) is not None:
                        button[field] = html.unescape(button[field])

        return login_config


def _strip_authentication_secrets(auth):
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


def _preserve_authentication_secrets(new_auth, existing_auth):
    """Preserve existing sensitive fields when the caller omitted or left them empty.

    For every provider in ``new_auth`` (e.g. ``ldap``, ``google``), walks each
    nested config dict (e.g. ``ldap_config``) and, for each sensitive key
    (``password``, ``client_secret``), keeps the existing value from
    ``existing_auth`` when the new payload provides an empty / falsy value.
    If the payload omits the key entirely, this is left untouched so the
    caller's intent is preserved.
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
                    del config_data[secret_key]
