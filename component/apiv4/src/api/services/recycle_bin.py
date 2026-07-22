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
import logging
from datetime import datetime, timedelta, timezone

from api.services.error import Error
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.recycle_bin import RecycleBin as CommonRecycleBin
from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue
from isardvdi_common.lib.deployments.deployments import DeploymentsProcessed
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.lib.notifications.notifications import NotificationsProcessed
from isardvdi_common.lib.notifications.notifications_action import (
    NotificationsActionProcessed,
)
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)
from isardvdi_common.models.category import Category as RethinkCategory
from isardvdi_common.models.recycle_bin import RecycleBin as RethinkRecycleBin
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.schemas.recycle_bin import RecycleBinStatusEnum

log = logging.getLogger(__name__)


class RecycleBinService:

    @staticmethod
    def get_default_delete_config() -> bool:
        return RecycleBinHelpers.get_default_delete()

    @staticmethod
    def get_user_cutoff_time(category_id: str) -> int:
        if not RethinkCategory.exists(category_id):
            raise Error(
                "not_found",
                f"Category {category_id} does not exist",
            )
        return RecycleBinHelpers.get_category_recycle_bin_cuttoff_time(
            category_id=category_id
        )

    @staticmethod
    def get_user_recycle_bin_entries(user_id: str) -> list[dict]:
        return RecycleBinHelpers.get_item_count(user_id=user_id)

    @staticmethod
    def get_recycle_bin_entry_details(
        recycle_bin_id: str, all_data: bool | None = None
    ) -> dict:
        if not RethinkRecycleBin.exists(recycle_bin_id):
            raise Error(
                "not_found",
                f"Recycle bin entry {recycle_bin_id} does not exist",
            )
        return RecycleBinHelpers.get(
            recycle_bin_id=recycle_bin_id,
            all_data=all_data,
        )

    @staticmethod
    def restore_recycle_bin_entry(recycle_bin_id: str) -> str:
        if not RethinkRecycleBin.exists(recycle_bin_id):
            raise Error(
                "not_found",
                f"Recycle bin entry {recycle_bin_id} does not exist",
            )
        return CommonRecycleBin(recycle_bin_id).restore()

    @staticmethod
    async def delete_recycle_bin_entry(recycle_bin_id: str, user_id: str) -> str:
        if not RethinkRecycleBin.exists(recycle_bin_id):
            raise Error(
                "not_found",
                f"Recycle bin entry {recycle_bin_id} does not exist",
            )
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User {user_id} does not exist",
            )
        await RecycleBinDeleteQueue().enqueue(
            {
                "action": "delete",
                "recycle_bin_id": recycle_bin_id,
                "user_id": user_id,
            }
        )

    @staticmethod
    async def empty_user_recycle_bin(user_id: str) -> str:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User {user_id} does not exist",
            )
        rb_ids = RecycleBinHelpers.get_user_recycle_bin_ids(
            user_id=user_id, status=RecycleBinStatusEnum.recycled.value
        )
        for rb_id in rb_ids:
            await RecycleBinDeleteQueue().enqueue(
                {"recycle_bin_id": rb_id, "user_id": user_id}
            )

    @staticmethod
    async def bulk_restore(recycle_bin_ids: list[str], user_id: str) -> list[str]:
        # ``CommonRecycleBin.restore()`` is sync RethinkDB I/O — running
        # it on the asyncio loop blocks every other request for
        # ~50-150 ms per item. Offload the whole sequential body to a
        # worker thread via ``asyncio.create_task(asyncio.to_thread(...))``
        # so the loop stays responsive while the bulk operation runs.
        def _process_sync():
            try:
                for rb_id in recycle_bin_ids:
                    rb = CommonRecycleBin(id=rb_id)
                    rb._update_agent(user_id)
                    rb.restore()
            except Exception as e:
                log.error("Bulk restore failed: %s", e)

        asyncio.create_task(asyncio.to_thread(_process_sync))
        return recycle_bin_ids

    @staticmethod
    async def bulk_delete(recycle_bin_ids: list[str], user_id: str) -> list[str]:
        async def _process():
            try:
                for rb_id in recycle_bin_ids:
                    await RecycleBinDeleteQueue().enqueue(
                        {
                            "action": "delete",
                            "recycle_bin_id": rb_id,
                            "user_id": user_id,
                        }
                    )
            except Exception as e:
                log.error("Bulk delete failed: %s", e)

        asyncio.create_task(_process())
        return recycle_bin_ids

    @staticmethod
    async def delete_cutoff_time_surpassed(user_id: str) -> None:
        recycle_bin_ids = (
            RecycleBinHelpers.get_recycle_bin_entries_cutoff_time_surpassed()
        )

        async def _process():
            try:
                for rb_id in recycle_bin_ids:
                    await RecycleBinDeleteQueue().enqueue(
                        {
                            "action": "delete",
                            "recycle_bin_id": rb_id,
                            "user_id": user_id,
                        }
                    )
            except Exception as e:
                log.error("Delete cutoff surpassed failed: %s", e)

        asyncio.create_task(_process())

    @staticmethod
    def list_stuck_entries(older_than_minutes: int = 0) -> list[dict]:
        """Recycle bin entries stranded mid-delete ('deleting' or 'queued')."""
        return RecycleBinHelpers.get_stuck_delete_entries(
            older_than_minutes=older_than_minutes
        )

    @staticmethod
    async def recover_stuck_entries(
        user_id: str, older_than_minutes: int = 0
    ) -> list[str]:
        """
        Re-enqueue recycle bin entries stranded mid-delete so the bulk-delete
        worker retries them.

        Manual admin recovery for entries orphaned by an ``isard-api`` restart:
        the startup reconcile only re-enqueues ``queued``, never ``deleting``.
        ``RecycleBin.delete_storage`` re-checks each storage's status and skips
        ones already ``deleted``, so re-running a partly-deleted entry only
        re-issues work for disks that are not gone yet.
        """
        stuck_ids = [
            entry["id"]
            for entry in RecycleBinHelpers.get_stuck_delete_entries(
                older_than_minutes=older_than_minutes
            )
        ]

        async def _process():
            try:
                for rb_id in stuck_ids:
                    await RecycleBinDeleteQueue().enqueue(
                        {
                            "action": "delete",
                            "recycle_bin_id": rb_id,
                            "user_id": user_id,
                        }
                    )
            except Exception as e:
                log.error("Recover stuck entries failed: %s", e)

        asyncio.create_task(_process())
        return stuck_ids

    @staticmethod
    def recycle_unused_items() -> None:
        # Apiv3 parity: ``recycle_bin_add_unused_items`` from
        # ``api/src/api/views/RecycleBinView.py`` (main). Each unused
        # desktop/deployment is moved to the recycle bin under the
        # ``isard-scheduler`` agent, and a ``notification_data`` row is
        # written so the user gets a heads-up before the cutoff fires.
        cutoff_hours = RecycleBinHelpers.get_recycle_bin_cuttoff_time()

        desktops = DesktopsProcessed.get_unused_desktops()
        desktop_notification = NotificationsProcessed.get_notifications_by_action_id(
            "unused_desktops"
        )
        desktop_notification = (
            desktop_notification[0]
            if desktop_notification and desktop_notification[0].get("trigger")
            else None
        )
        desktop_action = (
            NotificationsActionProcessed.get_notification_action(
                desktop_notification["action_id"]
            )
            if desktop_notification
            else None
        )

        notification_data: list[dict] = []
        for desktop in desktops:
            DesktopEvents.desktop_delete(desktop["id"], "isard-scheduler")
            if desktop_notification and desktop_action:
                notification_data.append(
                    {
                        "item_id": desktop["id"],
                        "item_type": "desktop",
                        "status": "pending",
                        "user_id": desktop["user"],
                        "created_at": datetime.now(timezone.utc),
                        "notified_at": None,
                        "accepted_at": None,
                        "notification_id": desktop_notification["id"],
                        "vars": {
                            var: desktop[var]
                            for var in desktop_action.get("kwargs", [])
                        },
                        "ignore_after": datetime.now(timezone.utc)
                        + timedelta(hours=int(cutoff_hours)),
                    }
                )
        if notification_data:
            NotificationsDataProcessed.add_notification_data(notification_data)

        deployments = DeploymentsProcessed.get_unused_deployments()
        deployment_notification = NotificationsProcessed.get_notifications_by_action_id(
            "unused_deployments"
        )
        deployment_notification = (
            deployment_notification[0]
            if deployment_notification and deployment_notification[0].get("trigger")
            else None
        )
        deployment_action = (
            NotificationsActionProcessed.get_notification_action(
                deployment_notification["action_id"]
            )
            if deployment_notification
            else None
        )

        notification_data = []
        for deployment in deployments:
            DesktopEvents.deployment_delete(deployment["id"], "isard-scheduler")
            if deployment_notification and deployment_action:
                common_data = {
                    "item_id": deployment["id"],
                    "item_type": "deployment",
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                    "notified_at": None,
                    "accepted_at": None,
                    "notification_id": deployment_notification["id"],
                    "vars": {
                        var: deployment[var]
                        for var in deployment_action.get("kwargs", [])
                    },
                    "ignore_after": datetime.now(timezone.utc)
                    + timedelta(hours=int(cutoff_hours)),
                }
                notification_data.append({**common_data, "user_id": deployment["user"]})
                for co_owner in deployment.get("co_owners") or []:
                    notification_data.append({**common_data, "user_id": co_owner})
        if notification_data:
            NotificationsDataProcessed.add_notification_data(notification_data)

        # Third pass: trim cold desktops belonging to deployments without
        # removing the parent deployment. Rule resolution is keyed on the
        # deployment creator. Port of main 7df258e32.
        deployment_desktop_groups = (
            DeploymentsProcessed.get_unused_deployment_desktops()
        )
        owner_notification = NotificationsProcessed.get_notifications_by_action_id(
            "unused_deployment_desktops_owner"
        )
        owner_notification = (
            owner_notification[0]
            if owner_notification and owner_notification[0].get("trigger")
            else None
        )
        user_notification = NotificationsProcessed.get_notifications_by_action_id(
            "unused_deployment_desktops_user"
        )
        user_notification = (
            user_notification[0]
            if user_notification and user_notification[0].get("trigger")
            else None
        )

        user_name_cache: dict[str, str] = {}

        def _resolve_user_name(user_id):
            if user_id not in user_name_cache:
                try:
                    name = Caches.get_document("users", user_id, ["name"])
                    user_name_cache[user_id] = name or user_id
                except ValueError:
                    user_name_cache[user_id] = user_id
            return user_name_cache[user_id]

        notification_data = []
        for group in deployment_desktop_groups:
            desktop_ids = [d["id"] for d in group["desktops"]]
            try:
                deployment_name = (
                    Caches.get_document("deployments", group["deployment_id"], ["name"])
                    or group["deployment_id"]
                )
            except ValueError:
                deployment_name = group["deployment_id"]
            DesktopEvents.deployment_delete_desktops(
                "isard-scheduler",
                desktop_ids,
                owner_id=group["creator"],
                name=deployment_name,
            )

            if not (owner_notification or user_notification):
                continue

            deployment_owner_name = _resolve_user_name(group["creator"])
            for desktop in group["desktops"]:
                desktop_owner_name = _resolve_user_name(desktop["user"])
                common_data = {
                    "item_id": desktop["id"],
                    "item_type": "desktop",
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                    "notified_at": None,
                    "accepted_at": None,
                    "ignore_after": datetime.now(timezone.utc)
                    + timedelta(hours=int(cutoff_hours)),
                }
                if owner_notification:
                    notification_data.append(
                        {
                            **common_data,
                            "user_id": group["creator"],
                            "notification_id": owner_notification["id"],
                            "vars": {
                                "desktop_name": desktop["name"],
                                "desktop_owner": desktop_owner_name,
                                "deployment_name": deployment_name,
                                "accessed": desktop["accessed"],
                            },
                        }
                    )
                if user_notification:
                    notification_data.append(
                        {
                            **common_data,
                            "user_id": desktop["user"],
                            "notification_id": user_notification["id"],
                            "vars": {
                                "desktop_name": desktop["name"],
                                "deployment_name": deployment_name,
                                "deployment_owner": deployment_owner_name,
                                "accessed": desktop["accessed"],
                            },
                        }
                    )

        if notification_data:
            NotificationsDataProcessed.add_notification_data(notification_data)

    @staticmethod
    def get_system_cutoff_time(category_id: str | None = None) -> int:
        return RecycleBinHelpers.get_recycle_bin_cuttoff_time(category_id=category_id)

    @staticmethod
    def set_system_cutoff_time(
        cutoff_time: int | float, category_id: str | None = None
    ) -> None:
        RecycleBinHelpers.set_system_recycle_bin_cutoff_time(cutoff_time, category_id)

    @staticmethod
    def get_status(category_id: str | None = None) -> dict:
        return RecycleBinHelpers.get_status(category_id=category_id)

    @staticmethod
    def get_user_count(user_id: str) -> int:
        return RecycleBinHelpers.get_user_amount(user_id=user_id)

    @staticmethod
    def set_old_entries_max_time(max_time: str) -> dict:
        return CommonRecycleBin.set_old_entries_max_time(max_time)

    @staticmethod
    def set_old_entries_action(action: str) -> dict:
        return CommonRecycleBin.set_old_entries_action(action)

    @staticmethod
    def get_old_entries_config() -> dict:
        return RecycleBinHelpers.get_old_entries_config()

    @staticmethod
    def delete_old_entries() -> None:
        # Indexed range scan (one rdb roundtrip, IDs-only). The
        # pre-fix path materialised every deleted-entry row via
        # ``get_item_count(status="deleted")`` (full count merge) and
        # Python-filtered them — pathological at scale.
        rcb_list = RecycleBinHelpers.get_old_deleted_entry_ids()
        CommonRecycleBin.delete_old_entries(rcb_list)

    @staticmethod
    def set_default_delete(rb_default: bool) -> None:
        CommonRecycleBin.set_default_delete(rb_default)

    @staticmethod
    def get_delete_action() -> str:
        return RecycleBinHelpers.get_delete_action()

    @staticmethod
    def set_delete_action(action: str) -> None:
        CommonRecycleBin.set_delete_action(action)

    @staticmethod
    def get_all_unused_item_timeout_rules() -> list[dict]:
        return CommonRecycleBin.get_all_unused_item_timeout()

    @staticmethod
    def get_unused_item_timeout_rule(rule_id: str) -> dict:
        return CommonRecycleBin.get_unused_item_timeout(rule_id)

    @staticmethod
    def create_unused_item_timeout_rule(data: dict) -> str:
        # Apiv3 contract: ``id`` is a server-generated UUID (Cerberus
        # ``default_setter: genuuid``). Webapp form does not send one.
        # Default ``allowed`` to the empty allow-set (per apiv3
        # ``allowed: {schema: allowed, default: {}}``) so consumers
        # see a consistent shape on read.
        import uuid

        if not data.get("id"):
            data["id"] = str(uuid.uuid4())
        if data.get("allowed") is None:
            data["allowed"] = {}
        CommonRecycleBin.create_unused_item_timeout(data)
        return data["id"]

    @staticmethod
    def update_unused_item_timeout_rule(rule_id: str, data: dict) -> None:
        CommonRecycleBin.update_unused_item_timeout(rule_id, data)

    @staticmethod
    def delete_unused_item_timeout_rule(rule_id: str) -> None:
        CommonRecycleBin.delete_unused_item_timeout(rule_id)

    @staticmethod
    def get_item_count(
        user_id: str | None = None,
        category_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        return RecycleBinHelpers.get_item_count(
            user_id=user_id, category_id=category_id, status=status
        )
