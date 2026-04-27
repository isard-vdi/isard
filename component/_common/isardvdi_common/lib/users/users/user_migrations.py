#
#   Copyright © 2025 Pau Abril Iranzo
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


import asyncio
import logging as logger
import time
import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.api_notify import notify_admins, notify_custom
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue
from isardvdi_common.lib.users.users.user import UsersProcessed
from isardvdi_common.models.config import Config
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError


class UserMigrationsProcessed(RethinkSharedConnection):

    @classmethod
    def get_user_resources(cls, user_id):
        desktops = []
        templates = []
        deployments = []
        media = []
        with cls._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(user_id, index="user")["id"]
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")["id"]
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = list(
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")["id"]
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            media = list(
                r.table("media")
                .get_all(user_id, index="user")["id"]
                .run(cls._rdb_connection)
            )
        return {
            "desktops": desktops,
            "templates": templates,
            "deployments": deployments,
            "media": media,
        }

    @classmethod
    def register_migration(cls, migration_token, origin_user_id):
        """
        _From api/libv2/api_users.py ApiUsers.register_migration()_

        Registers a user migration in the database. If a migration already exists for the user, it updates it with the new token.

        :param migration_token: The migration token
        :type migration_token: str
        :param origin_user_id: The origin user id
        :type origin_user_id: str
        :param exp_time: The expiration time
        :type exp_time: int

        """
        with cls._rdb_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(origin_user_id, index="origin_user")
                .run(cls._rdb_connection)
            )
        if user_migration:
            if len(user_migration) > 1:
                raise Error(
                    "forbidden",
                    "Multiple migrations found for the same user",
                    description_code="multiple_migrations_found_origin_user",
                )
            with cls._rdb_context():
                r.table("users_migrations").get_all(
                    origin_user_id, index="origin_user"
                ).filter(
                    lambda migration: ~migration["status"].match("migrated")
                ).replace(
                    r.row.without({"import_time": True, "target_user": True}).merge(
                        {
                            "status": "exported",
                            "export_time": int(time.time()),
                            "origin_user": origin_user_id,
                            "token": migration_token,
                        }
                    )
                ).run(
                    cls._rdb_connection
                )
        else:
            with cls._rdb_context():
                # TODO(move-users-to-common): pydantic validation
                r.table("users_migrations").insert(
                    {
                        "token": migration_token,
                        "status": "exported",
                        "created": int(time.time()),
                        "origin_user": origin_user_id,
                    }
                ).run(cls._rdb_connection)

    @classmethod
    def get_user_migration(cls, migration_token):
        """

        Gets a user migration based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        :return: The user migration data

        """
        with cls._rdb_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .filter(lambda migration: ~migration["status"].match("revoked|failed"))
                .run(cls._rdb_connection)
            )
        if user_migration:
            if len(user_migration) > 1:
                raise Error(
                    "internal_server",
                    "Multiple migrations found for token",
                    description_code="multiple_migrations_found",
                )

            return user_migration[0]
        else:
            raise Error(
                "not_found",
                "Migration not found",
                description_code="migration_not_found",
            )

    @classmethod
    def get_migrations(cls):
        with cls._rdb_context():
            migrations = list(
                r.table("users_migrations")
                .merge(
                    lambda migration: {
                        "origin_user": r.table("users")
                        .get(migration["origin_user"])
                        .default({"name": None, "category": None})
                        .pluck("name", "category"),
                        "target_username": r.branch(
                            migration.has_fields("target_user"),
                            r.table("users")
                            .get(migration["target_user"])
                            .default({"name": None})["name"],
                            None,
                        ),
                    }
                )
                .merge(
                    lambda migration: {
                        "category": r.branch(
                            migration["origin_user"]["category"],
                            r.table("categories")
                            .get(migration["origin_user"]["category"])
                            .pluck("name")["name"],
                            "[DELETED]",
                        )
                    }
                )
                .run(cls._rdb_connection)
            )
        result = []
        for migration in migrations:
            result.append(
                {
                    "origin_username": (
                        migration["origin_user"]["name"]
                        if migration["origin_user"].get("name")
                        else "[DELETED]"
                    ),
                    "target_username": (
                        migration["target_username"]
                        if migration["target_username"]
                        else "[DELETED]"
                    ),
                    **{k: v for k, v in migration.items()},
                }
            )
        return result

    @classmethod
    def check_user_migration(cls, migration_token: str, target_user_id: str):
        """

        Check if the user migration exists and if the migration is valid based on the migration token. If it doesn't it raises an error.

        :param migration_token: The migration token
        :type migration_token: str
        """

        migration = cls.get_user_migration(migration_token)
        errors = cls.check_valid_migration(migration["origin_user"], target_user_id)
        return errors

    @classmethod
    def get_user_migration_by_target_user(cls, target_user_id):
        """

        Gets a user migration based on the target user id

        :param target_user_id: The target user id
        :type target_user_id: str
        :return: The user migration data

        """

        with cls._rdb_context():
            user_migration = list(
                r.table("users_migrations")
                .get_all(target_user_id, index="target_user")
                .filter(
                    lambda migration: ~migration["status"].match(
                        "migrated|revoked|failed"
                    )
                )
                .run(cls._rdb_connection)
            )
        if len(user_migration) > 1:
            raise Error(
                "forbidden",
                "Multiple migrations found for the same target user",
                description_code="multiple_migrations_found_target_user",
            )
        if user_migration:
            return user_migration[0]
        else:
            raise Error(
                "not_found",
                "Migration not found",
                description_code="migration_not_found",
            )

    @classmethod
    def update_user_migration(
        cls,
        migration_token,
        status=None,
        target_user_id=None,
        migration_start_time=False,
        migration_end_time=False,
        migrated_items=None,
        migrated_desktops: bool | None = None,
        migrated_desktops_error: str | None = None,
        migrated_templates: bool | None = None,
        migrated_templates_error: str | None = None,
        migrated_media: bool | None = None,
        migrated_media_error: str | None = None,
        migrated_deployments: bool | None = None,
        migrated_deployments_error: str | None = None,
    ):
        """
        Updates a user migration status based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        :param status: The migration status
        :type status: str
        :param target_user_id: The target user id
        :type target_user_id: str
        :param migration_start_time: Whether to set the migration start time
        :type migration_start_time: bool
        :param migration_end_time: Whether to set the migration end time
        :type migration_end_time: bool
        :param migrated_items: The migrated items
        :type migrated_items: dict
        :param migrated_desktops: Whether the desktops were migrated
        :type migrated_desktops: bool
        :param migrated_templates: Whether the templates were migrated
        :type migrated_templates: bool
        :param migrated_media: Whether the media was migrated
        :type migrated_media: bool
        :param migrated_deployments: Whether the deployments were migrated
        :type migrated_deployments: bool
        """
        data = {
            "status": status if status else None,
            "target_user": target_user_id,
            "import_time": int(time.time()) if status == "imported" else None,
            "migration_start_time": int(time.time()) if migration_start_time else None,
            "migration_end_time": int(time.time()) if migration_end_time else None,
            "migrated_items": migrated_items,
            "migrated_desktops": migrated_desktops,
            "migrated_desktops_error": migrated_desktops_error,
            "migrated_templates": migrated_templates,
            "migrated_templates_error": migrated_templates_error,
            "migrated_media": migrated_media,
            "migrated_media_error": migrated_media_error,
            "migrated_deployments": migrated_deployments,
            "migrated_deployments_error": migrated_deployments_error,
        }
        data = {k: v for k, v in data.items() if v is not None}
        with cls._rdb_context():
            total = (
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .count()
                .run(cls._rdb_connection)
            )
        if total > 1:
            raise Error(
                "forbidden",
                "Multiple migrations found for the same token",
                description_code="multiple_migrations_found_token",
            )
        else:
            with cls._rdb_context():
                r.table("users_migrations").get_all(
                    migration_token, index="token"
                ).update(data).run(cls._rdb_connection)

    @classmethod
    def delete_user_migration(cls, migration_token):
        """
        Deletes a user migration based on the migration token

        :param migration_token: The migration token
        :type migration_token: str
        """
        with cls._rdb_context():
            result = (
                r.table("users_migrations")
                .get_all(migration_token, index="token")
                .delete()
                .run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "No migration found when deleting",
                description_code="migration_not_found",
            )

    @classmethod
    def delete_user_migration_by_id(cls, migration_id):
        """
        Deletes a user migration based on the migration id

        :param migration_id: The migration id
        :type migration_id: str
        """
        with cls._rdb_context():
            result = (
                r.table("users_migrations")
                .get(migration_id)
                .delete()
                .run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "No migration found when deleting",
                description_code="migration_not_found",
            )

    @classmethod
    def reset_imported_user_migration_by_target_user(cls, target_user_id):
        """
        Reset as exported all the imported migrations from the given target user id (remove the import_time and target_user fields too).

        :param target_user_id: The target user id
        :type target_user_id: str
        """
        with cls._rdb_context():
            r.table("users_migrations").get_all(
                target_user_id, index="target_user"
            ).filter({"status": "imported"}).replace(
                r.row.without({"import_time": True, "target_user": True}).merge(
                    {"status": "exported"}
                )
            ).run(
                cls._rdb_connection
            )

    @classmethod
    def process_migrate_user(cls, user_id, target_user_id):
        user_data = Helpers.get_new_user_data(target_user_id)
        try:
            cls.migrate_user(user_id, user_data)
            notify_admins(
                "user_action",
                {"action": "migrate", "count": 1, "status": "completed"},
                category=user_data["new_user"]["category"],
            )
        except Error as e:
            logger.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "user_action",
                {
                    "action": "migrate",
                    "count": 1,
                    "msg": error_message,
                    "status": "failed",
                },
                category=user_data["new_user"]["category"],
            )
        except Exception:
            logger.error(traceback.format_exc())
            notify_admins(
                "user_action",
                {
                    "action": "migrate",
                    "count": 1,
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def migrate_user(cls, user_id, user_data):
        user_resources = cls.get_user_resources(user_id)
        if user_resources["desktops"]:
            Helpers.change_owner_desktops(
                user_resources["desktops"], user_data, user_id
            )
        if user_resources["templates"]:
            Helpers.change_owner_templates(user_resources["templates"], user_data)
        if user_resources["media"]:
            Helpers.change_owner_medias(user_resources["media"], user_data)
        Helpers.change_owner_deployments(
            user_resources["deployments"], user_data, user_id
        )
        rb_ids = RecycleBinHelpers.get_user_recycle_bin_ids(user_id, "recycled")
        for rb_id in rb_ids:
            RecycleBinDeleteQueue().enqueue_sync(
                {"recycle_bin_id": rb_id, "user_id": user_id}
            )

    @classmethod
    async def process_automigrate_user(cls, user_id, target_user_id, migration_token):
        # The whole body is sync RethinkDB I/O plus a long-running
        # ``automigrate_user`` that walks every desktop / template /
        # media / deployment owned by the source user. Running on the
        # asyncio event loop would freeze apiv4 for the duration of
        # the migration. Offload to a worker thread so the loop stays
        # responsive.
        def _sync_body():
            user_data = Helpers.get_new_user_data(target_user_id)
            cls.update_user_migration(
                migration_token, "migrating", migration_start_time=True
            )
            result = cls.automigrate_user(user_id, user_data, migration_token)
            if any(
                s in result
                for s in [
                    "desktops_error",
                    "templates_error",
                    "media_error",
                    "deployments_error",
                ]
            ):
                cls.update_user_migration(
                    migration_token, "failed", migration_end_time=True
                )
            else:
                cls.update_user_migration(
                    migration_token, "migrated", migration_end_time=True
                )
                with cls._rdb_context():
                    provider_migration_config = (
                        r.table("config")
                        .get(1)["auth"][user_data["payload"]["provider"]]
                        .run(cls._rdb_connection)
                    )
                action_after_migrate = provider_migration_config.get(
                    "migration", {}
                ).get("action_after_migrate", "")
                if action_after_migrate == "delete":
                    UsersProcessed.delete_user(user_id, user_id, True)
                elif action_after_migrate == "disable":
                    UsersProcessed.update_user(user_id, {"active": False})
            return result

        return await asyncio.to_thread(_sync_body)

    @classmethod
    def automigrate_user(cls, user_id, user_data, migration_token):
        """

        Migrates a user based on the user data and migration token

        :param user_id: The user id to migrate
        :type user_id: str
        :param user_data: The user data to migrate to
        :type user_data: dict
        :param migration_token: The migration token
        :type migration_token: str

        """
        progress = {}

        user_resources = cls.get_user_resources(user_id)
        cls.update_user_migration(migration_token, migrated_items=user_resources)

        if user_resources["desktops"]:
            try:
                Helpers.change_owner_desktops(
                    user_resources["desktops"], user_data, user_id
                )
            except Error as e:
                cls.update_user_migration(
                    migration_token,
                    migrated_desktops=False,
                    migrated_desktops_error=str(e),
                )
            except Exception:
                cls.update_user_migration(
                    migration_token,
                    migrated_desktops=False,
                    migrated_desktops_error="unknown",
                )
            else:
                cls.update_user_migration(migration_token, migrated_desktops=True)

        if user_resources["templates"]:
            try:
                Helpers.change_owner_templates(user_resources["templates"], user_data)
            except Error as e:
                cls.update_user_migration(
                    migration_token,
                    migrated_templates=False,
                    migrated_templates_error=str(e),
                )
            except Exception:
                cls.update_user_migration(
                    migration_token,
                    migrated_templates=False,
                    migrated_templates_error="unknown",
                )
            else:
                cls.update_user_migration(migration_token, migrated_templates=True)

        if user_resources["media"]:
            try:
                Helpers.change_owner_medias(user_resources["media"], user_data)
            except Error as e:
                cls.update_user_migration(
                    migration_token,
                    migrated_media=False,
                    migrated_media_error=str(e),
                )
            except Exception:
                cls.update_user_migration(
                    migration_token,
                    migrated_media=False,
                    migrated_media_error="unknown",
                )
            else:
                cls.update_user_migration(migration_token, migrated_media=True)

        if user_resources["deployments"]:
            try:
                Helpers.change_owner_deployments(
                    user_resources["deployments"], user_data, user_id
                )
            except Error as e:
                cls.update_user_migration(
                    migration_token,
                    migrated_deployments=False,
                    migrated_deployments_error=str(e),
                )
            except Exception:
                cls.update_user_migration(
                    migration_token,
                    migrated_deployments=False,
                    migrated_deployments_error="unknown",
                )
            else:
                cls.update_user_migration(migration_token, migrated_deployments=True)

        rb_ids = RecycleBinHelpers.get_user_recycle_bin_ids(user_id, "recycled")
        for rb_id in rb_ids:
            RecycleBinDeleteQueue().enqueue_sync(
                {"recycle_bin_id": rb_id, "user_id": user_id}
            )
        progress["rb_deleted"] = True
        notify_custom(
            "migration_progress",
            {"rb_deleted": True},
            "/userspace",
            user_id,
        )

        # TODO: only use ws once they are implemented in frontend
        return progress

    @classmethod
    def check_valid_migration(cls, origin_user_id, target_user_id, check_quotas=False):
        """

        Checks if the user migration is valid based on the role, category and quotas

        :param origin_user_id: The user id to migrate
        :param target_user_id: The user id to migrate to
        :return: A list of errors if the migration is not valid

        """
        errors = []
        if origin_user_id == target_user_id:
            errors.append(
                {
                    "description": "Can't migrate to the same user.",
                    "description_code": "same_user_migration",
                }
            )

        user_resources = cls.get_user_resources(origin_user_id)
        errors += cls.check_user_category_role_migration(
            origin_user_id, target_user_id, user_resources
        )
        if errors:
            return errors
        if Config.get_config()["user_migration"]["check_quotas"] or check_quotas:
            errors += cls.check_target_user_quotas_migration(
                target_user_id, user_resources
            )
        return errors

    @classmethod
    def check_user_category_role_migration(
        cls, origin_user_id, target_user_id, user_resources=None
    ):
        """

        Checks if the user migration is valid based on the following rules:
        - Can't migrate to a different category
        - Can't migrate to an admin role
        - If the old role is advanced, manager or admin and the origin user has templates, media or deployments the new role can't be user

        :param origin_user_id: The user id to migrate
        :param target_user_id: The user id to migrate to
        :param user_resources: The user resources to check if the user has templates, media or deployments
        :return: A list of errors if the migration is not valid

        """
        errors = []
        origin_user = UsersProcessed.get_user(origin_user_id)
        target_user = UsersProcessed.get_user(target_user_id)

        if origin_user["category"] != target_user["category"]:
            errors.append(
                {
                    "description": "Can't migrate to a different category.",
                    "description_code": "different_category_migration",
                }
            )

        if origin_user["role"] == "admin" and target_user["role"] != "admin":
            errors.append(
                {
                    "description": "Can't migrate from an admin role.",
                    "description_code": "role_migration_admin",
                }
            )
        # If the old role is advanced, manager or admin and the origin user has templates, media or deployments the new role can't be user
        if (
            origin_user["role"] in ["advanced", "manager", "admin"]
            and target_user["role"] == "user"
            and (
                user_resources["templates"]
                or user_resources["media"]
                or user_resources["deployments"]
            )
        ):
            errors.append(
                {
                    "description": "Can't migrate to a user role. Users only can have desktops. Change templates, media and deployments ownership or delete them first.",
                    "description_code": "role_migration_user",
                }
            )
        return errors

    @classmethod
    def check_target_user_quotas_migration(cls, target_user_id, user_resources):
        """

        Checks if the target user quotas are surpassed based on the following rules:
        - The new user can't surpass the desktops, templates, media or deployments quotas

        :param target_user_id: The user id to migrate to
        :param user_resources: The user resources to check if the user has templates, media or deployments
        :return: A list of errors if the quotas are surpassed

        """
        errors = []
        # Deployment desktops must be ignored when checking the new user quotas
        with cls._rdb_context():
            user_desktops = list(
                r.table("domains")
                .get_all(r.args(user_resources["desktops"]), index="id")
                .pluck("id", "tag")
                .run(cls._rdb_connection)
            )
        not_deployment_desktops = list(
            filter(lambda desktop: (desktop.get("tag") in [None, False]), user_desktops)
        )
        try:
            Quotas.desktop_create(target_user_id, len(not_deployment_desktops))
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_desktop_quota_error",
                }
            )

        try:
            Quotas.template_create(
                target_user_id,
                len(user_resources["templates"]),
            )
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_template_quota_error",
                }
            )

        try:
            Quotas.media_create(target_user_id, quantity=len(user_resources["media"]))
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_media_quota_error",
                }
            )

        try:
            Quotas.deployment_create(
                owner_id=target_user_id, quantity=len(user_resources["deployments"])
            )
        except Error as e:
            errors.append(
                {
                    "description": e.args[1],
                    "description_code": "migration_deployments_quota_error",
                }
            )

        return errors

    @classmethod
    def get_user_migration_status(cls, migration_id):
        with cls._rdb_context():
            return (
                r.table("users_migrations")
                .get(migration_id)
                .pluck("status")
                .run(cls._rdb_connection)["status"]
            )

    @classmethod
    def revoke_user_migration(cls, migration_id):
        try:
            status = cls.get_user_migration_status(migration_id)
        except ReqlNonExistenceError:
            raise Error(
                "not_found",
                f"Migration {migration_id} not found",
                description_code="migration_not_found",
            )

        if status in ["exported", "imported", "migrating"]:
            with cls._rdb_context():
                r.table("users_migrations").get(migration_id).update(
                    {"status": "revoked"}
                ).run(cls._rdb_connection)
        else:
            raise Error(
                "bad_request",
                description=f'Migrations in status "{status}" cannot be revoked.',
            )

    @classmethod
    def check_migrated_user(cls, role, user=None, user_id=None):
        """
        Check if the user trying to be enabled is a migrated user. If it is and the role is not admin, raise an error.

        :param role: The role of the user doing the action
        :type role: str
        :param user_id: The user id to check
        :type user_id: str

        :return: True if the user is a migrated user, False otherwise
        :rtype: bool
        """
        if not user:
            if not user_id:
                raise Error("bad_request", "User data or user_id must be provided")
            user = Caches.get_document("users", user_id, ["active", "id"])
        # Older user docs predate the ``active`` field; treat them as
        # active by default so check_migrated_user doesn't crash with
        # KeyError on every login attempt.
        if user.get("active") is False:
            with cls._rdb_context():
                user_migrated = list(
                    r.table("users_migrations")
                    .get_all(user["id"], index="origin_user")
                    .filter({"status": "migrated"})
                    .run(cls._rdb_connection)
                )
            if user_migrated:
                if role == "admin":
                    return True
                else:
                    raise Error(
                        "bad_request",
                        "Migrated user cannot be activated. Please contact an administrator.",
                        description_code="migrated_user_activation_error",
                    )
            return False
        return False

    @classmethod
    def enable_users_check(cls, enable, payload, user=None, user_id=None):
        """
        Check if an user can be enabled or disabled. If the user data is not provided, it will be retrieved using the user_id.

        :param enable: If the user is being enabled or disabled
        :type enable: bool
        :param payload: The payload of the user doing the action
        :type payload: dict
        :param user: The data of the user to enable or disable
        :type user: dict

        :return: True if the user can be enabled or disabled, False otherwise
        :rtype: bool
        """

        if not user:
            if not user_id:
                raise Error("bad_request", "User data or user_id must be provided")
            user = Caches.get_document("users", user_id, invalidate=True)
        if enable:
            return not cls.check_migrated_user(payload["role_id"], user=user)
        else:
            if user["id"] == "local-default-admin-admin":
                raise Error("forbidden", "Can not deactivate default admin")
            if user["id"] == payload["user_id"]:
                raise Error("forbidden", "Can not deactivate your own account")
        return True
