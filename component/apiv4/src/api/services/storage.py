#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

import json
import time

from api.services.error import Error
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.api_notify import notify_admin, notify_admins
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task
from isardvdi_common.models.user import User as RethinkUser
from rethinkdb import r


def desktops_stop(
    desktops_ids,
    force=False,
    include_shutting_down=True,
    batch_size=20,
    wait_seconds=1,
    update_accessed=True,
):
    """Stop desktops by updating their status in RethinkDB."""
    action = "stop"
    try:
        status_updates = []
        if include_shutting_down:
            status_updates.append(("Shutting-down", "Stopping"))
        if force:
            status_updates.append(("Started", "Stopping"))
        else:
            status_updates.append(("Started", "Shutting-down"))

        update_data = {}
        if update_accessed:
            update_data["accessed"] = int(time.time())

        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            keys = [["desktop", d_id] for d_id in batch_ids]
            for current_status, new_status in status_updates:
                update_data["status"] = new_status
                with RethinkSharedConnection._rdb_context():
                    r.table("domains").get_all(*keys, index="kind_ids").filter(
                        {"status": current_status}
                    ).update(update_data).run(RethinkSharedConnection._rdb_connection)
            time.sleep(wait_seconds)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Exception:
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def get_disks_ids_by_status(status=None):
    """Get storage IDs filtered by status."""
    with RethinkSharedConnection._rdb_context():
        query = r.table("storage")
        if status:
            if status == "other":
                query = query.filter(
                    lambda disk: r.expr(["ready", "deleted"])
                    .contains(disk["status"])
                    .not_()
                )
            else:
                query = query.get_all(status, index="status")
        return list(
            query.pluck("id")["id"].run(RethinkSharedConnection._rdb_connection)
        )


def get_user_ready_disks(user_id):
    """Get ready disks for a user."""
    with RethinkSharedConnection._rdb_context():
        query = (
            r.table("storage")
            .get_all([user_id, "ready"], index="user_status")
            .pluck(
                [
                    "id",
                    "user_id",
                    "user_name",
                    {"qemu-img-info": {"virtual-size": True, "actual-size": True}},
                    "status_logs",
                ],
            )
            .merge(
                lambda disk: {
                    "user_name": r.table("users")
                    .get(disk["user_id"])
                    .default({"name": "[DELETED] " + disk["user_id"]})["name"],
                    "category": r.table("users")
                    .get(disk["user_id"])
                    .default({"category": "[DELETED]"})["category"],
                    "domains": r.table("domains")
                    .get_all(disk["id"], index="storage_ids")
                    .filter({"user": user_id})
                    .pluck("id", "name", "status")
                    .coerce_to("array"),
                }
            )
        )
        return list(query.run(RethinkSharedConnection._rdb_connection))


def parse_disks(disks):
    """Parse disk data, extracting qemu-img-info and status_logs."""
    parsed_disks = []
    for disk in disks:
        if disk.get("qemu-img-info"):
            disk["actual_size"] = disk["qemu-img-info"]["actual-size"]
            disk["virtual_size"] = disk["qemu-img-info"]["virtual-size"]
            disk.pop("qemu-img-info")
        if disk.get("status_logs"):
            disk["last"] = disk["status_logs"][-1]["time"]
            disk.pop("status_logs")
        parsed_disks.append(disk)
    return parsed_disks


MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024


def get_storage(payload: dict, storage_id: str) -> Storage:
    """
    Check storage existence and access rights.

    :param payload: Data from JWT
    :param storage_id: Storage ID
    :return: Storage object
    """
    if not Storage.exists(storage_id):
        raise Error("not_found", f"Storage {storage_id} not found")

    storage = Storage(storage_id)
    if payload["role_id"] == "admin":
        return storage

    if storage.user_id is None:
        raise Error("not_found", f"Storage {storage_id} missing user_id")

    if storage.user_id == payload["user_id"]:
        return storage

    if payload["role_id"] == "manager":
        storage_category_id = RethinkUser.get(storage.user_id).get("category")
        if storage_category_id == payload["category_id"]:
            return storage

    raise Error(
        "forbidden",
        "Not enough access rights for this user_id " + payload["user_id"],
    )


def storage_status(storage: Storage, status: str) -> None:
    """Check that storage has the expected status."""
    if storage.status != status:
        raise Error(
            "precondition_required",
            f"Storage {storage.id} status is not ready ({storage.status}). Can't execute operation",
            description_code="storage_not_ready",
        )


def not_storage_children(storage: Storage) -> None:
    """Check that storage has no children (derivatives)."""
    if storage.children:
        raise Error(
            "conflict",
            f"Storage {storage.id} used as backing file for {len(storage.children)} storages. Can't execute operation",
        )


def check_task_priority(payload: dict, priority: str) -> str:
    """Validate and return task priority."""
    if payload["role_id"] != "admin":
        priority = "low"
    else:
        if priority not in ["low", "default", "high"]:
            raise Error(
                "bad_request",
                "Priority must be low, default or high",
            )
    return priority


def check_task_retry(payload: dict, retry) -> int:
    """Validate and return task retry count."""
    if payload["role_id"] != "admin" or retry is None:
        retry = 0
    else:
        if not isinstance(retry, int):
            try:
                retry = int(retry)
            except ValueError:
                raise Error(
                    "bad_request",
                    "Retry should be an integer between 0 and 5",
                )
        if retry < 0 or retry > 5:
            raise Error(
                "bad_request",
                "Retry should be an integer between 0 and 5",
            )
    return retry


def get_storage_pool_obj(storage_pool_id: str) -> StoragePool:
    """Check storage pool existence and return it."""
    if not StoragePool.exists(storage_pool_id):
        raise Error(
            "not_found",
            f"Storage pool {storage_pool_id} not found",
        )
    return StoragePool(storage_pool_id)


def get_storage_pool_by_path(path: str) -> StoragePool:
    """Get storage pool by path."""
    storage_pools = StoragePool.get_by_path(path)
    if not storage_pools:
        raise Error(
            "not_found",
            f"Storage pool for path {path} not found",
        )
    return storage_pools[0]


class StorageService:

    # ── STATUS MANAGEMENT ──────────────────────────────────────────────

    @staticmethod
    def set_maintenance(payload: dict, storage_id: str, action: str) -> str:
        """Set a storage to maintenance status."""
        storage = get_storage(payload, storage_id)
        storage.set_maintenance(storage_id, action)
        return storage.id

    @staticmethod
    def set_ready(payload: dict, storage_id: str) -> str:
        """Set a storage to ready status."""
        storage = get_storage(payload, storage_id)
        storage.set_ready()
        return storage.id

    @staticmethod
    def batch_check_backing_chain(payload: dict, storage_ids: list[str]) -> None:
        """Check backing chain for a batch of storages by IDs."""
        for storage_id in storage_ids:
            storage = get_storage(payload, storage_id)
            storage.check_backing_chain(user_id=payload.get("user_id"))

    @staticmethod
    def batch_check_backing_chain_by_status(payload: dict, status: str) -> None:
        """Check backing chain for all storages with a given status."""
        storages_ids = get_disks_ids_by_status(status=status)
        for storage_id in storages_ids:
            try:
                storage = get_storage(payload, storage_id)
                storage.check_backing_chain(user_id=payload.get("user_id"))
            except Exception:
                notify_admin(
                    payload["user_id"],
                    "Error finding storage",
                    f"There was an error creating a task for {storage_id}",
                    type="error",
                )

    # ── CRUD ───────────────────────────────────────────────────────────

    @staticmethod
    def get_storage_detail(payload: dict, storage_id: str) -> dict:
        """Get storage details.

        ``get_storage`` returns a ``Storage`` model wrapper (not a dict).
        Calling ``dict(storage)`` on it crashes because the
        ``RethinkCustomBase.__getattr__`` proxies any unknown attribute
        access to a rethinkdb pluck and returns ``None`` for unknown
        fields — so ``storage.keys`` silently becomes ``None`` and the
        builtin ``dict()`` constructor calls ``None()`` and dies with
        ``'NoneType' object is not callable``. Bypass the wrapper and
        fetch the raw row directly.
        """
        # Access-control side-effect (raises 404 if missing / not owned).
        get_storage(payload, storage_id)
        with RethinkSharedConnection._rdb_context():
            row = (
                r.table("storage")
                .get(storage_id)
                .run(RethinkSharedConnection._rdb_connection)
            )
        return row or {}

    @staticmethod
    def get_user_ready_storages(user_id: str) -> list[dict]:
        """Get user's ready disks."""
        disks = get_user_ready_disks(user_id)
        return parse_disks(disks)

    @staticmethod
    def get_storage_storages_with_uuid(payload: dict, storage_id: str) -> list:
        """Return the ``storages_with_uuid`` field of a single storage.

        Mirrors v3 ``GET /storage/<id>/storages_with_uuid``
        (``StorageView.py:1299``). Used by the old admin storage page
        to inspect "phantom" storages found inside a backing chain.
        """
        storage = get_storage(payload, storage_id)
        return getattr(storage, "storages_with_uuid", []) or []

    @staticmethod
    def get_all_storages_with_uuid(payload: dict, status: str | None = None) -> list:
        """Return all rows in ``storages_with_uuid`` across the storage table.

        Mirrors v3 ``GET /storage/storages_with_uuid[/<status>]``
        (``StorageView.py:1306``). Manager-role callers are scoped to
        their own category; admins see everything.
        """
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return StorageProcessed.get_storages_with_uuid(
            category_id=category_id,
            status=status,
        )

    @staticmethod
    def get_all_storages_with_uuid_status(payload: dict) -> list:
        """Return the per-status counts of ``storages_with_uuid``.

        Mirrors v3 ``GET /storage/storages_with_uuid/status``
        (``StorageView.py:1320``). Same category-scoping rules as
        :py:meth:`get_all_storages_with_uuid`.
        """
        category_id = (
            payload["category_id"] if payload["role_id"] == "manager" else None
        )
        return StorageProcessed.get_storages_with_uuid_status(
            category_id=category_id,
        )

    @staticmethod
    def create_storage(
        payload: dict,
        usage: str,
        storage_type: str,
        parent: str,
        size: str,
        user_id: str | None,
        priority: str,
    ) -> dict:
        """Create a new storage."""
        priority = check_task_priority(payload, priority)
        user_id = user_id or payload["user_id"]

        quota = Quotas.get_applied_quota(user_id).get("quota")
        if quota and quota.get("desktops_disk_size") < int(size[:-1]):
            raise Error("bad_request", "Disk size quota exceeded")

        try:
            storage, task_id = Storage.create_new_storage(
                user_id=user_id,
                pool_usage=usage,
                parent_id=parent,
                storage_type=storage_type,
                size=str(size),
                priority=priority,
            )
        except Exception as e:
            raise Error(*e.args)

        return {"storage_id": storage.id, "task_id": task_id}

    @staticmethod
    def delete_storage(payload: dict, storage_id: str) -> str:
        """Delete a storage."""
        storage = get_storage(payload, storage_id)
        try:
            return storage.task_delete(payload.get("user_id"))
        except Exception as e:
            raise Error(*e.args)

    # ── STORAGE INFO ───────────────────────────────────────────────────

    @staticmethod
    def get_parents(payload: dict, storage_id: str) -> list[dict]:
        """Get storage parent chain."""
        storage = get_storage(payload, storage_id)
        return [
            {
                "id": s.id,
                "status": s.status,
                "parent_id": s.parent,
                "domains": [
                    {"id": domain.id, "name": domain.name, "kind": domain.kind}
                    for domain in s.domains
                ],
            }
            for s in [storage] + storage.parents
        ]

    @staticmethod
    def get_task(payload: dict, storage_id: str) -> dict | None:
        """Get storage task as dict."""
        storage = get_storage(payload, storage_id)
        if storage.task:
            return Task(storage.task).to_dict()
        return None

    @staticmethod
    def get_statuses(payload: dict, storage_id: str) -> dict:
        """Get storage and domain statuses."""
        storage = get_storage(payload, storage_id)
        return storage.statuses

    @staticmethod
    def has_derivatives(payload: dict, storage_id: str) -> int:
        """Return the number of derivatives (children) for a storage."""
        storage = get_storage(payload, storage_id)
        return len(storage.children)

    # ── DISK OPERATIONS ────────────────────────────────────────────────

    @staticmethod
    def increase_size(
        payload: dict,
        storage_id: str,
        increment: int,
        priority: str = "low",
        retry: int = 0,
    ) -> str:
        """Increase the size of a storage qcow2.

        Mirrors v3 ``api/views/StorageView.py::storage_increase_size``:
        - resolves the storage with ownership check via ``get_storage``,
        - validates the user's ``desktops_disk_size`` quota against the
          requested increment,
        - normalises the priority to ``low`` for non-admin callers and
          rejects unknown priorities,
        - validates the retry count,
        - delegates to ``Storage.increase_size``.
        """
        storage = get_storage(payload, storage_id)
        quota = Quotas.get_applied_quota(storage.user_id).get("quota")
        if quota:
            virtual_size_gb = (
                getattr(storage, "qemu-img-info")["virtual-size"] / 1024 / 1024 / 1024
            )
            if quota.get("desktops_disk_size") < (virtual_size_gb - int(increment)):
                raise Error("bad_request", "Disk size quota exceeded")

        if payload["role_id"] != "admin":
            priority = "low"
        if priority not in ["low", "default", "high"]:
            raise Error(
                "bad_request",
                "Priority must be low, default or high",
            )
        retry = check_task_retry(payload, retry)
        try:
            return storage.increase_size(
                payload["user_id"],
                increment,
                priority,
                retry=retry,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def sparsify(
        payload: dict,
        storage_id: str,
        priority: str,
        retry: int = 0,
    ) -> str:
        """Sparsify a storage qcow2."""
        if priority not in ["low", "default", "high"]:
            raise Error("bad_request", "Priority must be low, default or high")
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)
        try:
            return storage.sparsify(
                payload.get("user_id"),
                priority=priority,
                secondary_priority="high",
                retry=retry,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def batch_sparsify(payload: dict, storage_ids: list[str]) -> None:
        """Sparsify a batch of storages."""
        for storage_id in storage_ids:
            try:
                storage = get_storage(payload, storage_id)
                storage.sparsify(
                    payload.get("user_id"),
                    priority="default",
                    secondary_priority="high",
                )
            except Exception:
                notify_admin(
                    payload["user_id"],
                    "Error Sparsifying storage",
                    f"There was an error creating a task for {storage_id}",
                    type="error",
                )

    @staticmethod
    def disconnect(
        payload: dict,
        storage_id: str,
        priority: str,
        retry: int = 0,
    ) -> str:
        """Disconnect a storage from its backing chain."""
        priority = check_task_priority(payload, priority)
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)
        try:
            return storage.disconnect_chain(
                user_id=payload.get("user_id"),
                priority=priority,
                retry=retry,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def check_backing_chain(payload: dict, storage_id: str) -> dict:
        """Create a task to check storage backing chain."""
        storage = get_storage(payload, storage_id)
        return storage.check_backing_chain(
            user_id=payload.get("user_id"), blocking=False
        )

    @staticmethod
    def convert(
        payload: dict,
        storage_id: str,
        new_storage_type: str,
        new_storage_status: str,
        compress: bool,
        priority: str,
    ) -> dict:
        """Convert a storage to a new format."""
        priority = check_task_priority(payload, priority)
        origin_storage = get_storage(payload, storage_id)
        origin_storage.set_maintenance("convert")

        new_storage = Storage.init_document(
            user_id=origin_storage.user_id,
            status="creating",
            type=new_storage_type.lower(),
            directory_path=origin_storage.directory_path,
            converted_from=origin_storage.id,
        )

        try:
            task_id = origin_storage.convert(
                user_id=payload["user_id"],
                new_storage=new_storage,
                new_storage_type=new_storage_type,
                new_storage_status=new_storage_status,
                compress=compress,
                priority=priority,
            )
            return {"new_storage_id": new_storage.id, "task_id": task_id}
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def recreate(
        payload: dict,
        storage_id: str,
        priority: str,
        retry: int,
    ) -> str:
        """Recreate a storage with the same specifications and parent."""
        priority = check_task_priority(payload, priority)
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)

        if len(storage.domains) > 1:
            raise Error(
                "precondition_required",
                "Unable to recreate storage with more than one domain attached",
            )
        domain_id = storage.domains[0].id if len(storage.domains) == 1 else None

        try:
            return storage.recreate(
                payload.get("user_id"),
                domain_id,
                priority=priority,
                retry=retry,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def virt_win_reg(
        payload: dict,
        storage_id: str,
        registry_patch: str,
        priority: str,
        retry: int,
    ) -> str:
        """Apply a Windows registry patch to a storage qcow2."""
        if len(registry_patch.encode()) > MAX_FILE_SIZE_BYTES:
            raise Error(
                "bad_request",
                "The registry file is too large, exceeding the 1MB maximum",
            )
        priority = check_task_priority(payload, priority)
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)
        try:
            return storage.virt_win_reg(
                payload["user_id"],
                registry_patch,
                priority,
                retry=retry,
            )
        except Exception as e:
            raise Error(*e.args)

    # ── MOVEMENT ───────────────────────────────────────────────────────

    @staticmethod
    def move_by_path(
        payload: dict,
        storage_id: str,
        dest_path: str,
        priority: str,
    ) -> str:
        """Move a storage to another path."""
        if not dest_path.startswith("/"):
            dest_path = f"/{dest_path}"
        priority = check_task_priority(payload, priority)

        storage = get_storage(payload, storage_id)
        if storage.directory_path == dest_path:
            raise Error(
                "bad_request",
                f"Storage {storage.id} already in destination path {dest_path}, no need to execute operation",
            )

        try:
            return storage.mv(
                payload["user_id"],
                dest_path,
                priority,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def rsync_to_path(
        payload: dict,
        storage_id: str,
        destination_path: str,
        bwlimit: int | None,
        remove_source_file: bool,
        priority: str,
    ) -> str:
        """Rsync a storage to a destination path."""
        storage = get_storage(payload, storage_id)
        storage_status(storage, "ready")
        not_storage_children(storage)
        storage_pool_destination = get_storage_pool_by_path(destination_path)

        dest = storage.path_in_pool(storage_pool_destination)
        if dest is None:
            raise Error(
                "not_found",
                "No pool found with the usage, it was not found to execute rsync operation",
            )

        try:
            return storage.rsync(
                payload["user_id"],
                dest,
                bwlimit,
                remove_source_file,
                priority,
            )
        except Exception as e:
            raise Error(*e.args)

    @staticmethod
    def rsync_to_storage_pool(
        payload: dict,
        storage_id: str,
        destination_storage_pool_id: str,
        bwlimit: int | None,
        remove_source_file: bool,
        priority: str,
    ) -> str:
        """Rsync a storage to a storage pool."""
        storage = get_storage(payload, storage_id)
        if not StoragePool.exists(destination_storage_pool_id):
            raise Error(
                "not_found",
                f"Storage pool {destination_storage_pool_id} not found",
            )
        destination_path = storage.path_in_pool(
            StoragePool(destination_storage_pool_id)
        )
        if destination_path is None:
            raise Error(
                "not_found",
                "No pool found with the usage, it was not found to execute rsync operation",
            )
        if storage.path == destination_path:
            raise Error(
                "bad_request",
                f"Storage {storage.id} already in destination pool path {destination_path} to execute rsync operation",
            )
        try:
            return storage.rsync(
                payload["user_id"],
                destination_path,
                bwlimit,
                remove_source_file,
                priority,
            )
        except Exception as e:
            raise Error(*e.args)

    # ── MANAGEMENT ─────────────────────────────────────────────────────

    @staticmethod
    def stop_desktops(payload: dict, storage_id: str) -> None:
        """Stop all desktops using a storage."""
        storage = get_storage(payload, storage_id)
        domains = [domain.id for domain in storage.domains if domain.kind == "desktop"]
        desktops_stop(domains, force=True)

    @staticmethod
    def abort_operations(payload: dict, storage_id: str) -> str:
        """Abort ongoing operations for a storage."""
        storage = get_storage(payload, storage_id)
        task_agent_id = Task(storage.task).user_id
        # Check ownership: only the user who initiated the task or admin can abort
        if payload["role_id"] != "admin" and task_agent_id != payload["user_id"]:
            raise Error(
                "forbidden",
                "You are not authorized to cancel this operation as it was not initiated by you",
                description_code="operation_not_owned",
            )
        return storage.abort_operations(payload.get("user_id"))

    @staticmethod
    def set_path(
        payload: dict,
        storage_id: str,
        path: str,
        priority: str,
        retry: int,
    ) -> str:
        """Set path for a storage."""
        priority = check_task_priority(payload, priority)
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)
        return storage.set_path(
            payload.get("user_id"),
            path,
            priority=priority,
            retry=retry,
        )

    @staticmethod
    def delete_path(
        payload: dict,
        storage_id: str,
        path: str,
        priority: str,
        retry: int,
    ) -> str:
        """Delete path for a storage."""
        priority = check_task_priority(payload, priority)
        retry = check_task_retry(payload, retry)
        storage = get_storage(payload, storage_id)
        return storage.delete_path(
            payload.get("user_id"),
            path,
            priority=priority,
            retry=retry,
        )

    # ── DISCOVERY ──────────────────────────────────────────────────────

    @staticmethod
    def find(payload: dict, storage_id: str) -> dict:
        """Find a storage on disk."""
        storage = get_storage(payload, storage_id)
        return storage.find(payload.get("user_id"))

    @staticmethod
    def batch_find(payload: dict, storage_ids: list[str]) -> None:
        """Find multiple storages on disk."""
        for storage_id in storage_ids:
            storage = get_storage(payload, storage_id)
            storage.find(payload.get("user_id"))
