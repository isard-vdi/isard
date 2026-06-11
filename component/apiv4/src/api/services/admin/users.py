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
import json
import logging as log
import time
import traceback
from typing import Optional, Union, get_args
from uuid import uuid4

from api.services.admin.tables import AdminTablesService
from api.services.error import Error
from api.services.templates import clear_templates_cache
from fastapi import BackgroundTasks
from isardvdi_common.connections.api_sessions import revoke_user_session
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.bastion import Bastion
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_vpn import IsardVpn
from isardvdi_common.helpers.password import Password
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.quotas_process import QuotasProcess
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.domains.domains import DomainsProcessed
from isardvdi_common.lib.storage.storage_pools.storage_pools import (
    StoragePoolsProcessed,
)
from isardvdi_common.lib.users.categories.categories import (
    CategoriesProcessed as CommonCategories,
)
from isardvdi_common.lib.users.groups.groups import GroupsProcessed as CommonGroups
from isardvdi_common.lib.users.users.user import UsersProcessed as CommonUsers
from isardvdi_common.lib.users.users.user_enrollment import (
    UserEnrollment as CommonEnrollment,
)
from isardvdi_common.lib.users.users.user_migrations import (
    UserMigrationsProcessed as CommonMigrations,
)
from isardvdi_common.lib.users.users.user_policies import (
    UserPolicies as CommonUserPolicies,
)
from isardvdi_common.models.category import Category as RethinkCategory
from isardvdi_common.models.group import Group as RethinkGroup
from isardvdi_common.models.roles import Roles as RethinkRole
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.schemas.user import USER_ROLE


class AdminUsersService:
    """
    Service for admin user management operations.
    """

    # Role hierarchy derived from USER_ROLE so the two can't drift; higher rank is more privileged.
    _ROLE_RANK = {role: rank for rank, role in enumerate(get_args(USER_ROLE))}

    # ── Ownership Checks ─────────────────────────────────────────────────

    @staticmethod
    def owns_user_id(payload: dict, user_id: str) -> None:
        """Check if the admin/manager owns the user."""
        Helpers.owns_user_id(payload, user_id)

    @staticmethod
    def owns_category_id(payload: dict, category_id: str) -> None:
        """Check if the admin/manager owns the category."""
        Helpers.owns_category_id(payload, category_id)

    # ── User CRUD ────────────────────────────────────────────────────────

    @staticmethod
    def get_impersonate_jwt(payload: dict, user_id: str) -> dict:
        """Generate an impersonation JWT, rejecting targets whose role
        outranks the caller's (equal rank is allowed)."""
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User {user_id} not found",
                description_code="not_found",
            )

        target = CommonUsers.get_user(user_id)
        target_role = target.get("role") if isinstance(target, dict) else None
        caller_role = payload.get("role_id", "")

        caller_rank = AdminUsersService._ROLE_RANK.get(caller_role, -1)
        target_rank = AdminUsersService._ROLE_RANK.get(target_role, -1)

        # Cannot impersonate a role above the caller's (e.g. manager→admin).
        if target_rank < 0 or caller_rank < target_rank:
            raise Error(
                "forbidden",
                f"Cannot impersonate user with role '{target_role}' from role '{caller_role}'",
                description_code="not_enough_rights",
            )

        log.warning(
            "Impersonation: user %s (%s) impersonating user %s (%s)",
            payload.get("user_id"),
            caller_role,
            user_id,
            target_role,
        )
        return CommonUsers.gen_impersonate_jwt(user_id)

    @staticmethod
    def user_exists(user_id: str) -> bool:
        """Check if a user exists."""
        return RethinkUser.exists(user_id)

    @staticmethod
    def get_user_full_data(user_id: str) -> dict:
        """Get full user data."""
        return CommonUsers.get_user_full_data(user_id)

    @staticmethod
    def get_user_raw(user_id: str) -> dict:
        """Get raw user data."""
        return CommonUsers.get_user(user_id)

    @staticmethod
    def list_users(
        nav: Optional[str] = None, category_id: Optional[str] = None
    ) -> list[dict]:
        """List users, optionally filtered by nav and category."""
        return CommonUsers.admin_list_users(nav, category_id)

    @staticmethod
    def create_user(payload: dict, data: dict) -> dict:
        """Create a new user."""
        # RethinkBase.init_document inserts the kwargs as-is; passing
        # id=None makes RethinkDB store a literal null instead of
        # auto-generating a key, then the follow-up cls(None) lookup
        # crashes. Generate the id up front (matches v3
        # ApiUsers.Create).
        data["id"] = str(uuid4())
        data["accessed"] = int(time.time())
        data["quota"] = False
        # New users are active by default; without this field
        # CommonMigrations.check_migrated_user crashes with KeyError
        # and the webapp shows the user as disabled with no toggle.
        data.setdefault("active", True)

        if data.get("bulk"):
            match = AdminUsersService._category_name_group_name_match(
                data["category"], data["group"]
            )
            data["category"] = CommonCategories.get_id_by_name(match["category"])
            data["group"] = CommonGroups.get_group_by_name_category(
                match["group"], data["category"]
            )["id"]

        data["username"] = data["username"].replace(" ", "")
        if data["provider"] == "local":
            data["uid"] = data["username"]

        AdminUsersService._check_duplicate_user(
            data["uid"], data["category"], data["provider"]
        )
        AdminUsersService.owns_category_id(payload, data["category"])

        if data.get("secondary_groups"):
            if len(data["secondary_groups"]) > 0:
                CommonGroups.check_secondary_groups_category(
                    data["category"], data["secondary_groups"]
                )

        if not RethinkCategory.exists(data["category"]):
            raise Error(
                "not_found",
                f"Category {data['category']} not found",
            )
        if not RethinkGroup.exists(data["group"]):
            raise Error(
                "not_found",
                f"Group {data['group']} not found",
            )

        group = Caches.get_document("groups", data["group"])
        if group["parent_category"] != data["category"]:
            raise Error(
                "bad_request",
                f"Group {data['group']} does not belong to category {data['category']}",
            )

        Quotas.UserCreate(category_id=data["category"], group_id=data["group"])

        password = data["password"]
        policy = CommonUserPolicies.get_user_policy(
            subtype="password",
            category_id=data["category"],
            role_id=data["role"],
            provider=data["provider"],
        )
        if policy:
            Password.check_policy(password, policy, username=data["username"])
        data["password"] = Password.encrypt(password)
        data["password_history"] = [data["password"]]
        data["password_last_updated"] = int(time.time())
        data["email_verification_token"] = None
        data["api_key"] = None

        RethinkUser.init_document(**data)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()
        # Strip the password before returning; the route JSON-serializes
        # the result and we never want it leaving the service.
        data.pop("password", None)
        data.pop("password_history", None)
        return data

    @staticmethod
    def _check_role_elevation(
        payload: dict, user_id: str, data: dict, current_role: str
    ) -> None:
        """Reject role mutations that elevate the target above the caller, or that change the caller's own role."""
        if "role" not in data or data["role"] is None:
            return

        new_role = data["role"]
        if new_role == current_role:
            return
        caller_role = payload.get("role_id", "")
        caller_rank = AdminUsersService._ROLE_RANK.get(caller_role, -1)
        new_rank = AdminUsersService._ROLE_RANK.get(new_role, -1)

        if new_rank < 0:
            raise Error(
                "bad_request",
                f"Unknown role '{new_role}'",
                description_code="bad_request",
            )

        # Block granting a role above the caller's own rank.
        if new_rank > caller_rank:
            raise Error(
                "forbidden",
                f"Cannot grant role '{new_role}' from role '{caller_role}'",
                description_code="not_enough_rights",
            )

        # Nobody may change their own role.
        if user_id == payload.get("user_id") and new_role != caller_role:
            raise Error(
                "forbidden",
                "Cannot mutate own role",
                description_code="not_enough_rights",
            )

    @staticmethod
    def update_user(payload: dict, user_id: str, data: dict) -> None:
        """Update a single user."""
        user = Caches.get_document("users", user_id)
        if "active" in data:
            CommonMigrations.enable_users_check(data["active"], payload, user=user)

        AdminUsersService.owns_user_id(payload, user_id)
        AdminUsersService.owns_category_id(payload, user["category"])

        AdminUsersService._check_role_elevation(
            payload, user_id, data, user.get("role")
        )

        if data.get("secondary_groups") is not None:
            if len(data["secondary_groups"]) > 0:
                CommonGroups.check_secondary_groups_category(
                    user["category"], data["secondary_groups"]
                )

        if data.get("bulk"):
            match = AdminUsersService._category_name_group_name_match(
                data["category"], data["group"]
            )
            data["category"] = CommonCategories.get_id_by_name(match["category"])
            data["group"] = CommonGroups.get_group_by_name_category(
                match["group"], data["category"]
            )["id"]

        if "quota" in data:
            if payload["role_id"] != "admin":
                category_quota = Quotas.GetCategoryQuota(payload["category_id"])[
                    "quota"
                ]
                if category_quota != False:
                    for k, v in category_quota.items():
                        if (
                            data.get("quota")
                            and data.get("quota").get(k)
                            and v < data.get("quota")[k]
                        ):
                            raise Error(
                                "precondition_required",
                                f"Can't update {user['name']} {k} quota value with a higher "
                                f"value than its category quota, {k} must be equal or lower than {v}",
                            )

        if data.get("password") and user_id != payload["user_id"]:
            data["password_last_updated"] = 0

        CommonUsers.update_user(user_id, data)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()

    @staticmethod
    def update_multiple_users(
        payload: dict, data: dict, background_tasks: BackgroundTasks
    ) -> None:
        """Update multiple users in bulk.

        The bulk update runs after the response is sent (FastAPI default
        thread pool). Originally v3 used a ``gevent.spawn`` wrapper
        (``CommonUsers.update_multiple_users_th``); under apiv4's
        asyncio worker that silently never ran. See
        APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.
        """
        user_ids = data.get("ids", [])

        for u_id in user_ids:
            user = Caches.get_document("users", u_id)
            if "active" in data:
                CommonMigrations.enable_users_check(data["active"], payload, user=user)
            AdminUsersService.owns_user_id(payload, u_id)
            AdminUsersService.owns_category_id(payload, user["category"])

            AdminUsersService._check_role_elevation(
                payload, u_id, data, user.get("role")
            )

            if data.get("secondary_groups") is not None:
                if len(data["secondary_groups"]) > 0:
                    CommonGroups.check_secondary_groups_category(
                        user["category"], data["secondary_groups"]
                    )

        background_tasks.add_task(
            CommonUsers.update_multiple_users,
            user_ids,
            data,
            str(uuid4()),
            payload,
        )

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()

    @staticmethod
    def delete_users(
        payload: dict, data: dict, background_tasks: BackgroundTasks
    ) -> tuple[dict, int]:
        """Delete one or more users."""
        exceptions = []

        for user_id in data["user"]:
            try:
                AdminUsersService.owns_user_id(payload, user_id)
                user = CommonUsers.get_user(user_id)
                if (
                    user["username"] == "admin"
                    and user["group"] == "default-default"
                    and user["category"] == "default"
                ):
                    raise Error(
                        "forbidden",
                        "Can not delete default admin",
                    )
                elif user["id"] == payload["user_id"]:
                    raise Error(
                        "forbidden",
                        "Can not delete your own user",
                    )
            except Error as e:
                exceptions.append(e.args[1] if len(e.args) > 1 else str(e))

        if exceptions:
            return {"exceptions": exceptions}, 428

        def process_bulk_delete() -> None:
            try:
                for user_id in data["user"]:
                    revoke_user_session(user_id)
                    CommonUsers.delete_user(
                        user_id, payload["user_id"], data.get("delete_user", True)
                    )
            except Exception as e:
                log.error(f"Error during bulk delete: {e}")
                log.error(traceback.format_exc())
            finally:
                # Clear inside the task: the list view changes only
                # once the delete actually completes, so clearing here
                # avoids a window where the next read caches pre-delete
                # state for 360 s.
                from api.routes.users import clear_users_list_cache

                clear_users_list_cache()

        # FastAPI runs the task in its default thread-pool executor after
        # the response is sent — replaces a gevent.spawn that would have
        # silently never run inside the asyncio worker. See
        # APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.
        background_tasks.add_task(process_bulk_delete)
        return {}, 200

    @staticmethod
    def force_logout_user(payload: dict, user_id: str) -> None:
        """Force logout a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        revoke_user_session(user_id)

    # ── CSV Operations ───────────────────────────────────────────────────

    @staticmethod
    def validate_csv_users(payload: dict, user_list: list[dict]) -> dict:
        """Validate users from CSV for creation."""
        processed_list = []
        errors = []

        for user in user_list:
            user = {field: html.escape(str(value)) for field, value in user.items()}
            try:
                user = CommonUsers.bulk_user_check(payload, user, "csv")
            except Error as e:
                errors.append(
                    f"Skipping user {user.get('username', 'unknown')}: "
                    f"{e.error.get('description') if hasattr(e, 'error') else str(e)}"
                )
                continue
            processed_list.append(user)

        return {"errors": errors, "users": processed_list}

    @staticmethod
    def import_csv_users(payload: dict, data: dict) -> dict:
        """Import users from validated CSV data.

        Runs synchronously and returns {created, errors}. Previously this
        used `gevent.spawn` to fire-and-forget, which (a) returned 200
        even when no users were created, and (b) silently died inside
        FastAPI's asyncio worker (same pattern as the nextcloud gevent
        bug tracked in route_filter.SKIPPED_BLOCKING).
        """
        result = CommonUsers.generate_users(payload, data)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()
        return result

    @staticmethod
    def validate_csv_users_edit(payload: dict, user_list: list[dict]) -> list[dict]:
        """Validate CSV data for editing existing users."""
        for i, user in enumerate(user_list):
            cg_data = AdminUsersService._category_name_group_name_match(
                user["category"], user["group"]
            )
            if user.get("secondary_groups"):
                secondary_groups = []
                for sg_name in user["secondary_groups"]:
                    sg = CommonGroups.get_group_by_name_category(
                        sg_name, cg_data["category_id"]
                    )
                    secondary_groups.append(sg["id"])
                user_list[i]["secondary_groups"] = secondary_groups
                user_list[i]["secondary_groups_names"] = user["secondary_groups"]
            if user.get("name"):
                user_list[i]["name"] = user_list[i]["name"].strip('"')
            # Webapp's CSV-edit flow seeds rows from the validate-create
            # output, which doesn't carry ``provider`` or ``uid`` — for
            # local-provider users ``uid`` is the same as ``username``.
            # Default both so KeyError can't dump a 500 with no useful
            # description.
            provider = user.get("provider", "local")
            uid = user.get("uid") or user.get("username")
            try:
                found = CommonUsers.get_by_provider_category_uid(
                    provider, cg_data["category_id"], uid
                )
                user_list[i]["id"] = found[0]["id"]
                AdminUsersService.owns_user_id(payload, user_list[i]["id"])
            except Error:
                raise
            except Exception:
                raise Error(
                    "not_found",
                    f"User with username {user.get('name', 'unknown')} not found",
                )

            if user.get("password"):
                policy = CommonUserPolicies.get_user_policy(
                    subtype="password", user_id=user_list[i]["id"]
                )
                if policy:
                    Password.check_policy(
                        user["password"],
                        policy,
                        user_list[i]["id"],
                        user.get("username"),
                    )

            user_list[i]["category_id"] = cg_data["category_id"]
            user_list[i]["group_id"] = cg_data["group_id"]

        return user_list

    @staticmethod
    def edit_csv_users(payload: dict, data: dict) -> None:
        """Edit users from validated CSV data."""
        # The validate-edit endpoint enriches each row with the
        # resolved ``category`` / ``group`` / ``category_id`` /
        # ``group_id`` / ``provider`` / ``uid`` / ``id`` fields so the
        # webapp can render the CSV preview. ``CommonUsers.update_user``
        # treats the presence of those keys as a *change* request and
        # rejects with ``Error("bad_request", "Category can not be
        # changed", ...)``. Strip them here so a vanilla edit (rename,
        # password change, role bump) round-trips cleanly.
        immutable_keys = {
            "category",
            "category_id",
            "group",
            "group_id",
            "provider",
            "uid",
            "username",
        }
        for user_data in data["users"]:
            AdminUsersService.owns_user_id(payload, user_data["id"])
            if user_data.get("password"):
                user_data["password_last_updated"] = 0
            update_payload = {
                k: v for k, v in user_data.items() if k not in immutable_keys
            }
            CommonUsers.update_user(user_data["id"], update_payload)

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()

    # ── Secondary Groups ────────────────────────────────────────────────

    @staticmethod
    def update_secondary_groups(payload: dict, action: str, data: dict) -> None:
        """Add, overwrite, or delete secondary groups for users."""
        for user_id in data["ids"]:
            AdminUsersService.owns_user_id(payload, user_id)
        for group_id in data["secondary_groups"]:
            group = Caches.get_document("groups", group_id)
            AdminUsersService.owns_category_id(payload, group["parent_category"])
        CommonUsers.update_secondary_groups(action, data)

    # ── Password & Security ─────────────────────────────────────────────

    @staticmethod
    def get_password_policy(payload: dict, user_id: str) -> dict:
        """Get password policy for a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        return CommonUserPolicies.get_user_policy(subtype="password", user_id=user_id)

    @staticmethod
    def reset_password(data: dict) -> None:
        """Admin reset of user password."""
        if not data.get("password") or not data.get("user_id"):
            raise Error(
                "bad_request",
                "Password and user_id are required",
            )
        CommonUsers.change_password(data["password"], data["user_id"])

    @staticmethod
    def check_password_expiration(user_id: str) -> bool:
        """Check if password reset is required."""
        return CommonUsers.check_password_expiration(user_id)

    @staticmethod
    def check_email_verified(user_id: str) -> bool:
        """Check if email is verified."""
        return not CommonUsers.check_verified_email(user_id)

    @staticmethod
    def check_disclaimer_acknowledgement(user_id: str) -> bool:
        """Check if disclaimer is acknowledged."""
        return CommonUsers.check_acknowledged_disclaimer(user_id)

    @staticmethod
    def reset_vpn(payload: dict, user_id: str) -> None:
        """Reset VPN credentials for a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        CommonUsers.reset_vpn(user_id)

    # ── Groups CRUD ──────────────────────────────────────────────────────

    @staticmethod
    def list_groups(payload: dict) -> list[dict]:
        """List all groups (admin sees all, manager sees own category)."""
        groups = CommonGroups.admin_get_groups()
        if payload["role_id"] == "manager":
            groups = [
                g for g in groups if g["parent_category"] == payload["category_id"]
            ]
        return groups

    @staticmethod
    def list_groups_nav(payload: dict, nav: str) -> list[dict]:
        """List groups for a specific navigation context.

        Route layer constrains ``nav`` via ``Literal[...]`` so an
        invalid value 422s before reaching here. ``CommonUsers.admin_list_groups``
        only handles ``management`` / ``quotas_limits`` and would crash
        downstream with ``'list' object has no attribute 'run'`` on
        anything else, so the route-level validation is load-bearing.
        """
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return CommonUsers.admin_list_groups(nav, category_id)

    @staticmethod
    def get_group(group_id: str) -> dict:
        """Get full group data."""
        return CommonGroups.group_get_full_data(group_id)

    @staticmethod
    def create_group(payload: dict, data: dict) -> dict:
        """Create a new group."""
        if payload["role_id"] == "manager":
            data["parent_category"] = payload["category_id"]

        if not data.get("parent_category"):
            raise Error(
                "bad_request",
                "parent_category is required to create a group",
                description_code="parent_category_required",
            )

        category = Caches.get_document("categories", data["parent_category"])
        if category is None:
            raise Error(
                "not_found",
                f"Category {data['parent_category']} not found",
                description_code="category_not_found",
            )
        data["description"] = f"[{category['name']}] {data.get('description', '')}"

        AdminUsersService.owns_category_id(payload, data["parent_category"])
        if not RethinkCategory.exists(data["parent_category"]):
            raise Error(
                "not_found",
                f"Category {data['parent_category']} not found",
            )

        AdminUsersService._check_duplicate(
            "groups", data["name"], category=data["parent_category"]
        )

        if not data.get("id"):
            data["id"] = str(uuid4())

        RethinkGroup.init_document(**data)

        from api.routes.users import clear_groups_list_cache

        clear_groups_list_cache()
        return data

    @staticmethod
    def update_group(payload: dict, group_id: str, data: dict) -> None:
        """Update a group."""
        group = Caches.get_document("groups", group_id)
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        AdminUsersService._check_duplicate(
            "groups",
            data["name"],
            group["parent_category"],
            item_id=data.get("id"),
        )
        AdminTablesService.update_table_item("groups", data)

        from api.routes.users import clear_groups_list_cache

        clear_groups_list_cache()

    @staticmethod
    def delete_group(payload: dict, group_id: str) -> None:
        """Delete a group."""
        if payload["group_id"] == group_id:
            raise Error(
                "precondition_required",
                f"Can't delete your own group {group_id}",
            )
        group = Caches.get_document("groups", group_id)
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        CommonGroups.delete_group(group_id, payload["user_id"])

        # Deleting a group cascades to its users, so clear both list
        # caches.
        from api.routes.users import clear_groups_list_cache, clear_users_list_cache

        clear_groups_list_cache()
        clear_users_list_cache()

    @staticmethod
    def get_group_users(payload: dict, group_id: str) -> list[dict]:
        """Get users in a group."""
        group = Caches.get_document("groups", group_id)
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        return CommonGroups.get_users_in_group(group_id)

    @staticmethod
    def update_group_enrollment(payload: dict, data: dict) -> Union[bool, str]:
        """Update group enrollment settings."""
        group = Caches.get_document("groups", data["id"])
        if group is None:
            raise Error(
                "not_found",
                f"Group {data['id']} not found",
                description_code="group_not_found",
            )
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        return CommonEnrollment.enrollment_action(data)

    # ── Categories CRUD ──────────────────────────────────────────────────

    @staticmethod
    def list_categories(payload: dict, frontend: bool = False) -> list[dict]:
        """List categories."""
        if not frontend:
            return CommonUsers.categories_get()
        else:
            return CommonCategories.get_categories_frontend()

    @staticmethod
    def list_categories_nav(payload: dict, nav: str) -> list[dict]:
        """List categories for a specific navigation context.

        Route layer constrains ``nav`` via ``Literal[...]`` (FastAPI 422 on
        invalid values). Mirror of ``list_groups_nav`` — the underlying
        ``CommonUsers.admin_list_categories`` only handles the two known
        values and crashes on anything else.
        """
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return CommonUsers.admin_list_categories(nav, category_id)

    @staticmethod
    def get_category(payload: dict, category_id: str) -> dict:
        """Get a category by ID with authentication secrets stripped."""
        AdminUsersService.owns_category_id(payload, category_id)
        category = ApiAdmin.get_table_item("categories", category_id)
        if category is None:
            raise Error("not_found", f"Category {category_id} not found")
        category["is_default"] = category["id"] == "default"
        if "authentication" in category:
            from api.services.admin.categories import _strip_authentication_secrets

            category["authentication"] = _strip_authentication_secrets(
                category["authentication"]
            )
        return category

    @staticmethod
    def create_category(payload: dict, data: dict) -> dict:
        """Create a new category."""
        AdminUsersService._check_duplicate("categories", data["name"])
        if data.get("uid"):
            AdminUsersService._check_duplicate_uid(data["uid"])
        if data.get("custom_url_name"):
            AdminUsersService._check_duplicate_custom_url(data["custom_url_name"])

        storage_pool = data.pop("storage_pool", None)

        # Generate the id up front instead of relying on
        # init_document's generated_keys path (RethinkBase.__init__
        # explodes on a None id). Mirrors v3 ApiCategories.New().
        category_id = str(uuid4())

        category_data = {
            "id": category_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "frontend": data.get("frontend", True),
            "custom_url_name": data.get("custom_url_name", ""),
            "photo": data.get("photo"),
            "uid": data.get("uid") or category_id,
            # No authentication on create (apiv3 parity): provider state is
            # derived from live global availability, not a per-category snapshot.
            # Managers get no per-category settings access unless the admin grants it on create.
            "manager_permissions": {
                "authentication": False,
                "branding": False,
                "login_notification": False,
                **(data.get("manager_permissions") or {}),
            },
        }

        RethinkCategory.init_document(**category_data)

        # Create associated Main group
        group_data = {
            "id": str(uuid4()),
            "uid": "Main",
            "description": f"[{data['name']}] main group",
            "parent_category": category_id,
            "name": "Main",
        }
        RethinkGroup.init_document(**group_data)

        if storage_pool:
            StoragePoolsProcessed.add_category_to_storage_pool(
                storage_pool, category_id
            )

        # New category spawns a Main group, so /items/groups changes too.
        from api.routes.users import clear_groups_list_cache

        clear_groups_list_cache()
        return category_data

    @staticmethod
    def update_category(payload: dict, category_id: str, data: dict) -> None:
        """Update a category."""
        AdminUsersService.owns_category_id(payload, category_id)
        AdminUsersService._check_duplicate(
            "categories", data["name"], item_id=data.get("id")
        )
        if data.get("uid"):
            AdminUsersService._check_duplicate_uid(
                data["uid"], category_id=data.get("id")
            )
        if data.get("custom_url_name"):
            AdminUsersService._check_duplicate_custom_url(
                data["custom_url_name"], category_id=data.get("id")
            )
        AdminTablesService.update_table_item("categories", data)

        # /items/users and /items/groups both merge in category_name,
        # so a category rename must invalidate both list caches.
        from api.routes.users import clear_groups_list_cache, clear_users_list_cache

        clear_groups_list_cache()
        clear_users_list_cache()

    @staticmethod
    def delete_category(payload: dict, category_id: str) -> Optional[dict]:
        """Delete a category."""
        result = CommonCategories.delete_category(category_id, payload["user_id"])

        # Category deletion cascades to its groups and users, so both
        # list caches go stale.
        from api.routes.users import clear_groups_list_cache, clear_users_list_cache

        clear_groups_list_cache()
        clear_users_list_cache()
        return result

    @staticmethod
    def get_category_users(payload: dict, category_id: str) -> list[dict]:
        """Get users in a category."""
        AdminUsersService.owns_category_id(payload, category_id)
        return CommonUsers.list_by_category(category_id)

    @staticmethod
    def get_category_by_name(category_name: str) -> str:
        """Get category ID by name."""
        return CommonCategories.get_id_by_name(category_name)

    @staticmethod
    def get_group_by_name_category(category_name: str, group_name: str) -> str:
        """Get group ID by name and category."""
        group = CommonGroups.get_group_by_name_category(group_name, category_name)
        return group["id"]

    # ── Quotas & Limits ──────────────────────────────────────────────────

    @staticmethod
    def update_group_quota(payload: dict, group_id: str, data: dict) -> None:
        """Update group quota."""
        propagate = data.get("propagate", False)
        role = data.get("role", "all_roles")
        if role == "all_roles":
            role = False
        group = Caches.get_document("groups", group_id)
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        CommonGroups.update_group_quota(
            group, data["quota"], propagate, role, payload["role_id"]
        )

    @staticmethod
    def update_category_quota(payload: dict, category_id: str, data: dict) -> None:
        """Update category quota."""
        propagate = data.get("propagate", False)
        role = data.get("role", "all_roles")
        if role == "all_roles":
            role = False
        AdminUsersService.owns_category_id(payload, category_id)
        CommonCategories.update_category_quota(
            category_id, data["quota"], propagate, role
        )

    @staticmethod
    def update_group_limits(payload: dict, group_id: str, data: dict) -> None:
        """Update group limits."""
        group = Caches.get_document("groups", group_id)
        AdminUsersService.owns_category_id(payload, group["parent_category"])
        CommonGroups.update_group_limits(group, data["limits"])

    @staticmethod
    def update_category_limits(payload: dict, category_id: str, data: dict) -> None:
        """Update category limits."""
        propagate = data.get("propagate", False)
        AdminUsersService.owns_category_id(payload, category_id)
        CommonCategories.update_category_limits(category_id, data["limits"], propagate)

    # ── Validation & Checks ──────────────────────────────────────────────

    @staticmethod
    def user_delete_checks(payload: dict, ids: list[str]) -> dict:
        """Check deletion dependencies for users."""
        for user_id in ids:
            AdminUsersService.owns_user_id(payload, user_id)
        return AdminUsersService._delete_checks_inline(ids, "user")

    @staticmethod
    def group_delete_checks(payload: dict, ids: list[str]) -> dict:
        """Check deletion dependencies for groups."""
        for group_id in ids:
            group = Caches.get_document("groups", group_id)
            AdminUsersService.owns_category_id(payload, group["parent_category"])
        return AdminUsersService._delete_checks_inline(ids, "group")

    @staticmethod
    def category_delete_checks(payload: dict, ids: list[str]) -> dict:
        """Check deletion dependencies for categories."""
        for category_id in ids:
            AdminUsersService.owns_category_id(payload, category_id)
        return AdminUsersService._delete_checks_inline(ids, "category")

    # ── Supporting ───────────────────────────────────────────────────────

    @staticmethod
    def get_user_templates(payload: dict, user_id: str) -> list[dict]:
        """Get templates allowed for a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        templates = DomainsProcessed.list_by_kind_user(
            "template", user_id, ["id", "name", "icon", "description"]
        )
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "icon": t.get("icon", ""),
                "image": "",
                "description": t.get("description", ""),
            }
            for t in templates
        ]

    @staticmethod
    def get_admin_templates(payload: dict) -> list[dict]:
        """Get all templates allowed for the admin/manager."""
        category_id = (
            payload["category_id"] if payload.get("role_id") == "manager" else None
        )
        return DomainsProcessed.list_templates_for_admin(
            ["id", "name", "icon", "user", "category"],
            category_id=category_id,
        )

    @staticmethod
    def get_user_desktops(payload: dict, user_id: str) -> list[dict]:
        """Get desktops for a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        return DomainsProcessed.list_by_kind_user(
            "desktop", user_id, ["id", "name", "status", "icon", "image", "kind"]
        )

    @staticmethod
    def _delete_checks_inline(ids: list[str], kind: str) -> dict:
        """Return ids of items that would be cascaded by a delete.

        Delegates to ``UsersProcessed.user_delete_checks`` which returns
        ``{desktops, templates, deployments, media, users, groups}`` and
        also ``storage_pools`` (count) when ``kind == "category"``. The
        webapp's delete-confirmation modal consumes all six lists.
        """
        if not ids:
            base: dict = {
                "desktops": [],
                "templates": [],
                "deployments": [],
                "media": [],
                "users": [],
                "groups": [],
            }
            if kind == "category":
                base["storage_pools"] = 0
            return base
        return CommonUsers.user_delete_checks(list(ids), kind)

    @staticmethod
    def get_roles(payload: dict) -> list[dict]:
        """Get roles available to the caller."""
        return CommonUsers.get_roles(payload["role_id"])

    @staticmethod
    def update_role(data: dict) -> None:
        """Update a role."""
        AdminTablesService.update_table_item("roles", data)

    @staticmethod
    def get_secrets() -> list[dict]:
        """Get admin secrets."""
        return ApiAdmin.admin_table_list("secrets")

    @staticmethod
    def create_secret(data: dict) -> dict:
        """Create a new admin secret."""
        data["role_id"] = "manager"
        if not RethinkCategory.exists(data["category_id"]):
            raise Error(
                "not_found",
                f"Category {data['category_id']} not found",
            )
        AdminTablesService.insert_table_item("secrets", data)
        return {"secret": data["secret"]}

    @staticmethod
    def delete_secret(kid: str) -> None:
        """Delete an admin secret."""
        AdminTablesService.delete_table_item("secrets", kid)

    @staticmethod
    def get_user_vpn(
        payload: dict, user_id: str, kind: str, os: Union[str, bool] = False
    ) -> dict:
        """Get VPN data for a user."""
        AdminUsersService.owns_user_id(payload, user_id)
        if not os and kind != "config":
            raise Error(
                "bad_request",
                "UserVpn: no OS supplied",
            )
        vpn_data = IsardVpn.vpn_data("users", kind, os, user_id)
        if not vpn_data:
            raise Error(
                "not_found",
                "UserVpn no VPN data",
            )
        return vpn_data

    @staticmethod
    def get_user_schema(payload: dict) -> dict:
        """Get user schema for admin forms."""
        result = {}
        result["role"] = ApiAdmin.admin_table_list(
            "roles",
            pluck=["id", "name", "description", "sortorder"],
            order_by="sortorder",
            without=False,
        )

        if payload["role_id"] == "admin":
            result["category"] = ApiAdmin.admin_table_list(
                "categories",
                pluck=["id", "name", "description"],
                order_by="name",
                without=False,
                merge=False,
            )
            result["group"] = ApiAdmin.admin_table_list(
                "groups",
                pluck=[
                    "id",
                    "name",
                    "description",
                    "parent_category",
                    "linked_groups",
                    "external_gid",
                ],
                order_by="name",
                without=False,
                merge=False,
            )
        elif payload["role_id"] == "manager":
            result["role"] = [
                r for r in result["role"] if r["id"] in ["manager", "advanced", "user"]
            ]
            result["category"] = [
                ApiAdmin.manager_table_list(
                    "categories",
                    category=payload["category_id"],
                    pluck=[
                        "id",
                        "name",
                        "description",
                        "parent_category",
                        "linked_groups",
                    ],
                    without=False,
                    id=payload["category_id"],
                    merge=False,
                )
            ]
            result["group"] = ApiAdmin.manager_table_list(
                "groups",
                category=payload["category_id"],
                pluck=[
                    "id",
                    "name",
                    "description",
                    "parent_category",
                    "linked_groups",
                    "external_gid",
                ],
                order_by="name",
                without=False,
                id=payload["category_id"],
                index="parent_category",
                merge=False,
            )

        return result

    @staticmethod
    def search_users(payload: dict, term: str) -> list[dict]:
        """Search users by term."""
        if payload["role_id"] == "admin":
            return Alloweds.get_table_term(
                "users",
                "name",
                term,
                pluck=["id", "name", "uid"],
                query_filter=lambda user: user["role"] != "user",
            )
        else:
            return Alloweds.get_table_term(
                "users",
                "name",
                term,
                pluck=["id", "name", "category", "uid"],
                index_key="category",
                index_value=payload["category_id"],
                query_filter=lambda user: user["role"] != "user",
            )

    @staticmethod
    def get_admin_quotas(payload: dict) -> dict:
        """Get quotas for admin view."""
        return QuotasProcess.get(
            user_id=payload.get("user_id"),
            category_id=payload.get("category_id"),
            role_id=payload.get("role_id"),
        )

    @staticmethod
    def get_user_applied_quota(payload: dict, user_id: str) -> dict:
        """Get applied quota for a specific user."""
        return Quotas.get_applied_quota(user_id)

    @staticmethod
    def get_user_by_email_and_category(email: str, category: str) -> str:
        """Get user ID by email and category."""
        return CommonUsers.get_user_by_email_and_category(email, category)

    @staticmethod
    def auto_register_user(payload: dict, data: dict) -> str:
        """Auto-register a user."""
        AdminUsersService._check_duplicate_user(
            payload["user_id"], payload["category_id"], payload["provider"]
        )
        from api.services.users import UsersService

        user = UsersService.create(
            provider=payload["provider"],
            category_id=payload["category_id"],
            uid=payload["user_id"],
            username=payload["username"],
            name=payload["name"],
            role_id=data["role_id"],
            group_id=data["group_id"],
            photo=payload.get("photo"),
            email=payload.get("email"),
            secondary_groups=data.get("secondary_groups", []),
        )

        from api.routes.users import clear_users_list_cache

        clear_users_list_cache()
        return user.id if hasattr(user, "id") else user.get("id", user)

    # ── Migration ────────────────────────────────────────────────────────

    @staticmethod
    def check_valid_migration(payload: dict, user_id: str, target_user_id: str) -> list:
        """Check if a migration between users is valid."""
        AdminUsersService.owns_user_id(payload, user_id)
        AdminUsersService.owns_user_id(payload, target_user_id)
        return CommonMigrations.check_valid_migration(user_id, target_user_id)

    @staticmethod
    def migrate_user(
        payload: dict,
        user_id: str,
        target_user_id: str,
        background_tasks: BackgroundTasks,
    ) -> tuple[dict, int]:
        """Migrate a user to another user."""
        if user_id == target_user_id:
            raise Error(
                "precondition_required",
                "Can't migrate user to itself",
            )
        AdminUsersService.owns_user_id(payload, user_id)
        AdminUsersService.owns_user_id(payload, target_user_id)

        errors = CommonMigrations.check_valid_migration(user_id, target_user_id)
        if errors:
            return {"errors": errors}, 428

        def migrate_and_invalidate() -> None:
            try:
                CommonMigrations.process_migrate_user(user_id, target_user_id)
            finally:
                # User migration reassigns the source user's data and
                # eventually deletes the source user, so the /items/users
                # list view changes only once the migration actually
                # completes — clear inside the task. The routes import
                # stays lazy to avoid the services→routes cycle.
                from api.routes.users import clear_users_list_cache

                clear_users_list_cache()
                clear_templates_cache()

        # FastAPI runs the task after the response. Replaces the prior
        # gevent.spawn that silently never ran inside the asyncio worker.
        # See APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.
        background_tasks.add_task(migrate_and_invalidate)
        return {}, 200

    @staticmethod
    def migrate_user_resource(
        payload: dict, user_id: str, target_user_id: str, resource_type: str
    ) -> None:
        """Migrate a specific resource type from one user to another."""
        AdminUsersService.owns_user_id(payload, user_id)
        resources = CommonMigrations.get_user_resources(user_id)
        user_data = Helpers.get_new_user_data(target_user_id)

        if resource_type == "desktop":
            Helpers.change_owner_desktops(resources["desktops"], user_data, user_id)
        elif resource_type == "template":
            Helpers.change_owner_templates(resources["templates"], user_data)
            clear_templates_cache()
        elif resource_type == "media":
            Helpers.change_owner_medias(resources["media"], user_data)
        elif resource_type == "deployments":
            Helpers.change_owner_deployments(
                resources["deployments"], user_data, user_id
            )

    @staticmethod
    def check_migrated_users(payload: dict, user_ids: list[str]) -> bool:
        """Check if any users in the list are migrated."""
        migrated = False
        for user_id in user_ids:
            if CommonMigrations.check_migrated_user(
                payload["role_id"], user_id=user_id
            ):
                migrated = True
        return migrated

    # ── Check Group Category ─────────────────────────────────────────────

    @staticmethod
    def check_group_category(data: dict) -> None:
        """Verify each (group_id, category_id) pair: group must exist and
        belong to that category. Raises typed Error("not_found") on first
        mismatch so the webapp's bulk-edit form can report a clear error.
        """
        pairs = data.get("ids") or []
        if not pairs:
            return
        group_ids = [p.get("group") for p in pairs if p.get("group")]
        parent_by_group = CommonGroups.get_parent_category_map(group_ids)
        for p in pairs:
            gid = p.get("group")
            cid = p.get("category")
            parent = parent_by_group.get(gid)
            if parent is None:
                raise Error("not_found", f"Group {gid} not found")
            if parent != cid:
                raise Error(
                    "bad_request",
                    f"Group {gid} does not belong to category {cid}",
                )

    # ── Bastion Domain ───────────────────────────────────────────────────

    @staticmethod
    def get_category_bastion_domain(payload: dict, category_id: str) -> str:
        """Get bastion domain for a category."""
        AdminUsersService.owns_category_id(payload, category_id)
        from isardvdi_common.helpers.bastion import Bastion

        return Bastion.get_category_bastion_domain(category_id)

    @staticmethod
    def update_category_bastion_domain(
        payload: dict, category_id: str, data: dict
    ) -> None:
        """Update bastion domain for a category."""
        AdminUsersService.owns_category_id(payload, category_id)

        from isardvdi_common.helpers.bastion import Bastion

        bastion_domain = data["bastion_domain"]
        if (
            isinstance(bastion_domain, str)
            and Bastion.bastion_domain_verification_required()
        ):
            Bastion.check_bastion_domain_dns(
                bastion_domain, category_id, kind="category"
            )
        AdminUsersService._check_duplicate_bastion_domain(
            bastion_domain, category_id=category_id
        )
        Bastion.update_category_bastion_domain(category_id, bastion_domain)

    # ── Users Table Nav ──────────────────────────────────────────────────

    @staticmethod
    def list_users_nav(payload: dict, nav: str) -> list[dict]:
        """List users for a specific navigation context."""
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return CommonUsers.admin_list_users(nav, category_id)

    # ── Private Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _category_name_group_name_match(category_name: str, group_name: str) -> dict:
        """Match category and group names, handling special formats."""
        category = category_name
        group = group_name
        return {
            "category": category,
            "group": group,
            "category_id": CommonCategories.get_id_by_name(category),
            "group_id": CommonGroups.get_group_by_name_category(
                group,
                CommonCategories.get_id_by_name(category),
            )["id"],
        }

    @staticmethod
    def _check_duplicate_user(uid: str, category_id: str, provider: str) -> None:
        """Check for duplicate user."""
        exists = CommonUsers.check_user_exists(
            uid=uid, category_id=category_id, provider=provider
        )
        if exists:
            raise Error(
                "conflict",
                f"User with uid {uid} already exists in category {category_id} for provider {provider}",
            )

    @staticmethod
    def _check_duplicate(
        table: str,
        name: str,
        category: Optional[str] = None,
        item_id: Optional[str] = None,
    ) -> None:
        """Check for duplicate items in a table by name."""
        Helpers.check_duplicate(table, name, category=category, item_id=item_id)

    @staticmethod
    def _check_duplicate_uid(uid: str, category_id: Optional[str] = None) -> None:
        """Reject a category uid that already exists in another category."""
        rows = CommonCategories.find_duplicate_uid(uid, exclude_category_id=category_id)
        if rows:
            raise Error(
                "conflict",
                f"Category with uid {uid} already exists",
                description_code="duplicated_uid",
            )

    @staticmethod
    def _check_duplicate_custom_url(
        custom_url_name: str, category_id: Optional[str] = None
    ) -> None:
        """Reject a category custom_url_name that another category already uses."""
        rows = CommonCategories.find_duplicate_custom_url(
            custom_url_name, exclude_category_id=category_id
        )
        if rows:
            raise Error(
                "conflict",
                f"Category with custom_url_name {custom_url_name} already exists",
                description_code="duplicated_custom_url",
            )

    @staticmethod
    def _check_duplicate_bastion_domain(
        bastion_domain: str, category_id: Optional[str] = None
    ) -> None:
        """Reject a bastion domain that another category or desktop already uses."""
        Bastion.check_duplicate_bastion_domains(
            [bastion_domain], category_id=category_id
        )
