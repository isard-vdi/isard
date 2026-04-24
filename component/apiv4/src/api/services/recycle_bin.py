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

from api.services.error import Error
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.recycle_bin import RecycleBin as CommonRecycleBin
from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue
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
        async def _process():
            try:
                for rb_id in recycle_bin_ids:
                    rb = CommonRecycleBin(id=rb_id)
                    rb._update_agent(user_id)
                    rb.restore()
            except Exception as e:
                log.error("Bulk restore failed: %s", e)

        asyncio.create_task(_process())
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
        rcbs = RecycleBinHelpers.get_item_count(status="deleted")
        rcb_list = []
        for rcb in rcbs:
            if RecycleBinHelpers.check_older_than_old_entry_max_time(
                rcb["last"]["time"]
            ):
                rcb_list.append(rcb["id"])
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
    def update_task(task: dict) -> None:
        RecycleBinHelpers.update_task_status(task)

    @staticmethod
    def get_all_unused_item_timeout_rules() -> list[dict]:
        return CommonRecycleBin.get_all_unused_item_timeout()

    @staticmethod
    def get_unused_item_timeout_rule(rule_id: str) -> dict:
        return CommonRecycleBin.get_unused_item_timeout(rule_id)

    @staticmethod
    def create_unused_item_timeout_rule(data: dict) -> str:
        CommonRecycleBin.create_unused_item_timeout(data)
        return data.get("id", "")

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
