#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api.dependencies.jwt_token import TokenFastAPI
from api.services.config import ConfigService
from api.services.error import Error
from isardvdi_authentication_client.api.default import migrate_user
from isardvdi_authentication_client.models import MigrateUserRequest
from isardvdi_authentication_client_auth import build_client, raise_for_status
from isardvdi_common.lib.users.users.user import UsersProcessed as CommonUser
from isardvdi_common.lib.users.users.user_migrations import UserMigrationsProcessed
from isardvdi_common.models.config import Config
from isardvdi_common.models.user import User as RethinkUser


class MigrationService:

    @staticmethod
    def export_user(user_id: str) -> str:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID '{user_id}' does not exist.",
            )

        resources = CommonUser.user_delete_checks([user_id], "user")
        if not any(
            [
                resources["desktops"],
                resources["templates"],
                resources["media"],
                resources["deployments"],
            ]
        ):
            raise Error(
                "bad_request",
                description="No items available for migration",
                description_code="migration_no_items_available",
            )

        try:
            with build_client("isard-apiv4") as client:
                resp = migrate_user.sync_detailed(
                    client=client, body=MigrateUserRequest(user_id=user_id)
                )
                raise_for_status(resp)
                token = resp.parsed.token
        except Error:
            raise
        except Exception:
            raise Error(
                "internal_server",
                "Unable to connect with isard-authentication to get migration token",
                traceback.format_exc(),
                description_code="generic-error",
            )
        UserMigrationsProcessed.register_migration(token, user_id)
        return token

    @staticmethod
    def import_user(user_id: str, token: str) -> None:
        errors = UserMigrationsProcessed.check_user_migration(token, user_id)
        if errors:
            raise Error(
                "precondition_required",
                description=errors[0]["description"],
                description_code=errors[0]["description_code"],
            )

        try:
            TokenFastAPI.get_user_migration_payload(token)
        except Error as e:
            if e.error.get("description_code") == "token_expired":
                UserMigrationsProcessed.delete_user_migration(token)
                raise Error(
                    "bad_request",
                    description="The migration token has expired.",
                    description_code="token_expired",
                )
            raise e

        UserMigrationsProcessed.reset_imported_user_migration_by_target_user(user_id)
        UserMigrationsProcessed.update_user_migration(token, "imported", user_id)

    @staticmethod
    def list_migration_items(user_id: str) -> dict:
        try:
            user_migration = UserMigrationsProcessed.get_user_migration_by_target_user(
                user_id
            )
        except Error as e:
            if e.error.get("description_code") == "migration_not_found":
                errors = [
                    {
                        "description": "The user migration process was not found.",
                        "description_code": "invalid_token",
                    }
                ]
            elif (
                e.error.get("description_code")
                == "multiple_migrations_found_target_user"
            ):
                errors = [
                    {
                        "description": "Multiple user migration processes found for the target user.",
                        "description_code": "multiple_migrations_found_target_user",
                    }
                ]
            else:
                raise
            raise Error(
                "precondition_required",
                description=errors[0]["description"],
                description_code=errors[0]["description_code"],
            )

        errors = []

        try:
            TokenFastAPI.get_user_migration_payload(user_migration["token"])
        except Error as e:
            if e.error.get("description_code") == "token_expired":
                UserMigrationsProcessed.delete_user_migration(user_migration["token"])
            raise e

        errors += UserMigrationsProcessed.check_valid_migration(
            user_migration["origin_user"], user_id, check_quotas=True
        )

        quota_errors = []
        non_quota_errors = []

        if ConfigService.get_user_migration_config().get("check_quotas", False):
            non_quota_errors = errors
        else:
            for error in errors:
                if error["description_code"] in [
                    "migration_desktop_quota_error",
                    "migration_template_quota_error",
                    "migration_media_quota_error",
                    "migration_deployments_quota_error",
                ]:
                    quota_errors.append(error)
                else:
                    non_quota_errors.append(error)

        if non_quota_errors:
            return {
                "errors": non_quota_errors,
            }

        items = CommonUser.user_delete_checks([user_migration["origin_user"]], "user")
        items["desktops"] = [
            item
            for item in items["desktops"]
            if item["user"] == user_migration["origin_user"]
        ]
        items["templates"] = [
            item
            for item in items["templates"]
            if item["user"] == user_migration["origin_user"]
        ]
        if quota_errors:
            items["quota_errors"] = quota_errors

        items["action_after_migrate"] = (
            ConfigService.get_provider_config(items["users"][0]["provider"])
            .get("migration", {})
            .get("action_after_migrate", "none")
        )

        if (
            not items["desktops"]
            and not items["templates"]
            and not items["media"]
            and not items["deployments"]
        ):
            return {
                "errors": [
                    {
                        "description": "No items to migrate.",
                        "description_code": "no_items_to_migrate",
                    }
                ]
            }

        return {
            "items": items,
        }

    @staticmethod
    def migrate_user(target_user_id: str) -> dict:
        user_migration = UserMigrationsProcessed.get_user_migration_by_target_user(
            target_user_id
        )
        try:
            TokenFastAPI.get_user_migration_payload(user_migration["token"])
        except Error as e:
            if e.error.get("description_code") == "token_expired":
                UserMigrationsProcessed.delete_user_migration(user_migration["token"])
                raise Error(
                    "bad_request",
                    description="The migration token has expired.",
                    description_code="token_expired",
                )
            raise e

        errors = []
        errors += UserMigrationsProcessed.check_valid_migration(
            user_migration["origin_user"], target_user_id
        )
        if errors:
            return {
                "errors": errors,
            }

        return {
            "origin_user": user_migration["origin_user"],
            "target_user_id": target_user_id,
            "token": user_migration["token"],
        }

    @staticmethod
    async def migrate_user_and_process(target_user_id: str) -> dict:
        result = await asyncio.to_thread(MigrationService.migrate_user, target_user_id)
        if result.get("errors"):
            return result

        asyncio.create_task(
            UserMigrationsProcessed.process_automigrate_user(
                result["origin_user"],
                result["target_user_id"],
                result["token"],
            )
        )

        return {}

    @staticmethod
    def get_admin_migration_config() -> dict:
        return Config.get_user_migration_config()

    @staticmethod
    def update_admin_migration_config(data: dict) -> dict:
        return Config.set_user_migration_config(data)

    @staticmethod
    def get_all_migrations() -> list[dict]:
        return UserMigrationsProcessed.get_migrations()

    @staticmethod
    def revoke_migration(migration_id: str) -> None:
        UserMigrationsProcessed.revoke_user_migration(migration_id)

    @staticmethod
    def delete_migration(migration_id: str) -> None:
        UserMigrationsProcessed.delete_user_migration_by_id(migration_id)
