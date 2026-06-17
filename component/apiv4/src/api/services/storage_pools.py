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

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.storage.storage_pools.storage_pools import (
    StoragePoolsProcessed,
)
from isardvdi_common.models.storage_pool import StoragePool


class StoragePoolService:

    @staticmethod
    def add_storage_pool(data: dict) -> None:
        """
        Create a new storage pool.
        """
        StoragePoolsProcessed.add_storage_pool(data)

    @staticmethod
    def get_storage_pools() -> list[dict]:
        """
        Get all storage pools with enriched data.
        """
        return StoragePoolsProcessed.get_storage_pools()

    @staticmethod
    def get_storage_pool(storage_pool_id: str) -> dict:
        """
        Get a specific storage pool by ID and add the is_default flag.
        """
        StoragePool(storage_pool_id)  # raises not_found if missing
        result = StoragePool.get(storage_pool_id)
        result["is_default"] = storage_pool_id == DEFAULT_STORAGE_POOL_ID
        return result

    @staticmethod
    def get_storage_pool_by_path(path: str) -> dict:
        """
        Get a storage pool by its path.
        """
        storage_pools = StoragePool.get_by_path(path)
        if not storage_pools:
            raise Error(
                "not_found",
                f"No storage pool found for path {path}.",
                description_code="not_found",
            )
        storage_pool_id = storage_pools[0].id
        result = StoragePool.get(storage_pool_id)
        result["is_default"] = storage_pool_id == DEFAULT_STORAGE_POOL_ID
        return result

    @staticmethod
    def update_storage_pool(storage_pool_id: str, data: dict) -> None:
        """
        Update a storage pool.
        """
        StoragePoolsProcessed.update_storage_pool(storage_pool_id, data)

    @staticmethod
    def delete_storage_pool(storage_pool_id: str) -> None:
        """
        Delete a storage pool.
        """
        StoragePoolsProcessed.delete_storage_pool(storage_pool_id)

    @staticmethod
    def get_default_storage_pool() -> dict:
        """
        Get the default storage pool.
        """
        pool = ApiAdmin.get_table_item("storage_pool", DEFAULT_STORAGE_POOL_ID)
        return pool or {"id": DEFAULT_STORAGE_POOL_ID}

    @staticmethod
    def check_category_availability(
        categories: list[str], storage_pool_id: str = None
    ) -> bool:
        """
        Check if categories are available for assignment to a storage pool.
        """
        if not len(categories):
            return True
        return StoragePoolsProcessed.check_category_storage_pool_availability(
            categories, storage_pool_id
        )
