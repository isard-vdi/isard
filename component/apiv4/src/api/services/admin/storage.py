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

from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.media.media import MediaProcessed
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.storage import Storage


class AdminStorageService:

    @staticmethod
    def get_storage_status(payload: dict) -> list:
        """Get storage status counts, scoped by category for managers."""
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return StorageProcessed.get_status_counts(category_id=category_id)

    @staticmethod
    def get_storages(
        payload: dict, status: str = None, categories: list = None
    ) -> list:
        """Get storage list, optionally filtered by status and categories."""
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        admin_categories = categories if payload["role_id"] == "admin" else None

        if status == "delete_pending":
            return StorageProcessed.get_storages(
                status=status,
                category_id=category_id,
                categories=admin_categories,
            )
        else:
            return StorageProcessed.get_storages(
                status=status,
                category_id=category_id,
                categories=admin_categories,
            )

    @staticmethod
    def get_storage_domains(payload: dict, storage_id: str) -> list:
        """Get domains attached to a storage."""
        StorageProcessed.check_storage(payload, storage_id)
        return StorageProcessed.get_storage_domains(storage_id)

    @staticmethod
    def get_media_domains(payload: dict, storage_id: str) -> list:
        """Get domains using a media item."""
        Helpers.owns_media_id(payload, storage_id)
        return MediaProcessed.get_media_domains(storage_id)

    @staticmethod
    def delete_storage(payload: dict, storage_id: str) -> str:
        """Delete a storage via the canonical task chain (same one the
        user-facing ``DELETE /item/storage/{id}`` uses).

        The historical implementation only flipped ``status="Deleting"``
        via ``StorageProcessed.mark_delete``. No worker scans for that
        status — verified across change-handler, scheduler, storage
        worker — so the storage row got marked, the qcow2 file was never
        unlinked, and any child storages (rows whose ``parent ==
        storage_id``) silently became orphans pointing at a row marked
        Deleting. Operator's storage table showed the row "deleted"
        from Ready and they thought it worked.

        Now the admin endpoint mirrors the user endpoint:
        ``Storage(id).task_delete(user_id)`` fires the real cascade chain
        on the storage worker (delete file -> update_status ->
        storage_delete), with a typed-Error 428 precondition that rejects
        the call if the row still has child storages — avoids the
        silent "delete parent, orphan children" race.
        """
        if not Storage.exists(storage_id):
            raise Error(
                "not_found",
                f"Storage {storage_id} not found",
                description_code="not_found",
            )
        storage = Storage(storage_id)
        if storage.children:
            raise Error(
                "precondition_required",
                f"Storage {storage_id} has {len(storage.children)} child "
                "storage(s); delete them first.",
                description_code="storage_has_children",
            )
        return storage.task_delete(payload.get("user_id"))

    @staticmethod
    def get_storage_info(payload: dict, storage_id: str) -> dict:
        """Get detailed storage information."""
        StorageProcessed.check_storage(payload, storage_id)
        return StorageProcessed.get_storage(storage_id)

    @staticmethod
    def get_storage_search_info(payload: dict, storage_id: str) -> dict:
        """Get storage info with owner data."""
        StorageProcessed.check_storage(payload, storage_id)
        storage = StorageProcessed.get_storage_info(storage_id)
        storage["owner_data"] = Caches.get_cached_user_with_names(storage["user_id"])
        return storage

    @staticmethod
    def get_storages_by_role(role: str) -> list:
        """Get all storages filtered by user role."""
        valid_roles = ["admin", "manager", "advanced", "user"]
        if role not in valid_roles:
            raise Error(
                "bad_request",
                f"Invalid role: {role}. Valid roles are: {', '.join(valid_roles)}",
                description_code="invalid_role",
            )
        return StorageProcessed.get_storages_by_role(role)
