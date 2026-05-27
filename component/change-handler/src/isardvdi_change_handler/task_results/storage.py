#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
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

"""Storage-side task_results handlers ported from core_worker.

Each ``handle_<name>`` takes a :class:`Task` (the *dependent* RQ job
that core_worker would have picked up) plus its declared kwargs and
performs the same rethinkdb writes core_worker performs today. The
``send_status_socket`` helper is the change-handler equivalent of
core_worker's ``send_storage_status_socket`` — write-only fan-out via
the existing :class:`AsyncRedisManager`.

The ``send`` helper takes the manager from the consumer rather than
constructing its own so unit tests can pass an ``AsyncMock``.
"""

import json
import logging as log

from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage, StoragePool
from isardvdi_common.models.user import User

# Domain statuses that represent a domain that is not yet (or no longer)
# runnable and is waiting for its storage to be ready. Only these can be
# safely promoted to "Stopped" when a storage transitions to "ready" —
# running or transitional statuses must be left alone (otherwise we race
# with the engine/broom and create a Started↔Stopped flap loop).
#
# Kept in sync with core_worker.task._DOMAIN_PRE_READY_STATUSES — same
# set, same load-bearing reasons (Maintenance, CreatingTemplate, etc.).
_DOMAIN_PRE_READY_STATUSES = frozenset(
    {
        "Downloading",
        "Downloaded",
        "DiskNew",
        "Failed",
        "Unknown",
        "CreatingDomain",
        "CreatingDomainFromDisk",
        "CreatingTemplate",
        "Maintenance",
    }
)


def _promote_domains_to_stopped(storage_object):
    """Promote only domains waiting on storage to ``Stopped``.

    Skips domains currently running or in a transitional status so we
    never yank a live VM from under the engine's state machine.
    """
    for domain in storage_object.domains:
        if domain.status in _DOMAIN_PRE_READY_STATUSES:
            domain.status = "Stopped"
            domain.current_action = None


def _apply_storage_update(storage_dict):
    """Run the rethinkdb writes from a storage_update payload.

    Factored out of :func:`handle_storage_update` so
    :func:`handle_storage_update_pool` (which composes multiple
    storage updates inline) can reuse the same body without
    re-checking ``depending_status``.
    """
    if not storage_dict or not Storage.exists(storage_dict["id"]):
        return None
    storage_object = Storage.init_document(**storage_dict)
    if storage_dict.get("status") in ("deleted", "orphan", "broken_chain"):
        for domain in storage_object.domains + storage_object.domains_derivatives:
            domain.status = "Failed"
        for child in storage_object.derivatives:
            if child.status != "deleted":
                child.status = "orphan"
    if storage_dict.get("status") == "ready":
        _promote_domains_to_stopped(storage_object)
    return storage_object


def _resolve_user_category(user_id):
    if not user_id:
        return None
    try:
        return User(user_id).category
    except Exception:
        return None


async def send_status_socket(redis_manager, storage_id, status, user_id=None):
    """Fan-out the ``storage`` SocketIO event identically to
    core_worker.task.send_storage_status_socket.
    """
    payload = json.dumps({"id": storage_id, "status": status})
    if user_id:
        category = _resolve_user_category(user_id)
        if category:
            for room in (category, user_id):
                try:
                    await redis_manager.emit(
                        "storage",
                        payload,
                        namespace="/administrators",
                        room=room,
                    )
                except Exception:
                    log.exception(
                        "task_results.storage: emit storage on /administrators/%s failed",
                        room,
                    )
            try:
                await redis_manager.emit(
                    "storage",
                    payload,
                    namespace="/userspace",
                    room=user_id,
                )
            except Exception:
                log.exception(
                    "task_results.storage: emit storage on /userspace/%s failed",
                    user_id,
                )
    try:
        await redis_manager.emit(
            "storage",
            payload,
            namespace="/administrators",
            room="admins",
        )
    except Exception:
        log.exception(
            "task_results.storage: emit storage on /administrators/admins failed"
        )


def handle_storage_update_parent(task, storage_id):
    """Port of core_worker.task.storage_update_parent."""
    if task.depending_status != "finished":
        return
    if not Storage.exists(storage_id):
        return
    storage = Storage(storage_id)
    qemu_img_info = getattr(storage, "qemu-img-info")
    if qemu_img_info is None:
        return
    backing_file = qemu_img_info.get("full-backing-filename")
    if backing_file:
        backing_storage = Storage.get_by_path(backing_file)
        if backing_storage:
            storage.parent = backing_storage.id
            if storage.status == "orphan":
                backing_storage.status = "deleted"
                return
        elif storage.status == "orphan":
            return
        else:
            storage.parent = Storage.create_from_path(
                backing_file, user_id=task.user_id
            ).id
    else:
        storage.parent = None


async def handle_storage_update(redis_manager, task, **storage_dict):
    """Port of core_worker.task.storage_update.

    Direct call site (``storage_dict`` provided) writes the payload and
    fans out the ``storage`` SocketIO. Indirect call site (no
    ``storage_dict``) walks the task's dependencies to find a
    qemu_img_info / qemu_img_info_backing_chain / check_backing_filename
    result and applies it.
    """
    if task.depending_status != "finished":
        return
    if storage_dict:
        if _apply_storage_update(storage_dict) is None:
            return
        await send_status_socket(
            redis_manager,
            storage_dict["id"],
            storage_dict.get("status"),
            task.user_id,
        )
        return
    for dependency in task.dependencies:
        if dependency.task in (
            "qemu_img_info",
            "qemu_img_info_backing_chain",
        ):
            # R-7: a dependency that finished with no result payload yields
            # ``dependency.result is None``; ``**None`` raised
            # ``TypeError: argument after ** must be a mapping`` and crashed
            # the whole handler, silently dropping the storage state change.
            # Skip it (NOT ``or {}`` — an empty storage_dict makes
            # handle_storage_update re-walk the dependencies and recurse).
            if dependency.result is None:
                continue
            await handle_storage_update(redis_manager, task, **dependency.result)
        if dependency.task == "check_backing_filename":
            for result in dependency.result or []:
                if result is None:
                    continue
                await handle_storage_update(redis_manager, task, **result)


async def handle_storage_update_dict(redis_manager, task, **storage_dict):
    """Port of core_worker.task.storage_update_dict.

    Same body as ``storage_update`` minus the depending_status guard —
    callers (notably the ``set_path`` chain) want the update applied
    unconditionally.
    """
    if not storage_dict:
        return
    if _apply_storage_update(storage_dict) is None:
        return
    await send_status_socket(
        redis_manager,
        storage_dict["id"],
        storage_dict.get("status"),
    )


def handle_storage_add(task, **storage_dict):
    """Port of core_worker.task.storage_add."""
    Storage.init_document(**storage_dict)


def handle_storage_delete(task, storage_id):
    """Port of core_worker.task.storage_delete."""
    if not Storage.exists(storage_id):
        return
    if Storage(storage_id).status == "deleted":
        Storage.delete(storage_id)


async def handle_update_status(redis_manager, task, statuses=None):
    """Port of core_worker.task.update_status.

    The same nested dict structure (``_all`` plus per-status overrides)
    is honoured; storage rows additionally trigger
    :func:`send_status_socket` to keep the admin storage event flowing.
    Media and Domain rows update without a SocketIO emit — that's
    handled by change-handler's existing per-table changefeed listener.
    """
    statuses = statuses or {}
    for item_statuses_item_ids in (
        statuses.get("_all", {}),
        statuses.get(task.depending_status, {}),
    ):
        for item_status, items in item_statuses_item_ids.items():
            for item_class, item_ids in items.items():
                model = _ITEM_CLASS_MAP.get(item_class.lower())
                if model is None:
                    log.warning(
                        "task_results.update_status: unknown item_class %r",
                        item_class,
                    )
                    continue
                for item_id in item_ids:
                    model.init_document(item_id, status=item_status)
                    if item_class.lower() == "storage":
                        await send_status_socket(redis_manager, item_id, item_status)


def _valid_storage_pool(storage, new_path):
    storage_pools = StoragePool.get_by_path(new_path)
    if not storage_pools:
        return None
    pool_path = storage.get_storage_pool_path(storage_pools[0])
    expected_path = f"{pool_path}/{storage.id}.qcow2" if pool_path else None
    if expected_path == new_path:
        return storage_pools[0]
    return False


async def handle_storage_update_pool(redis_manager, task, storage_id):
    """Port of core_worker.task.storage_update_pool.

    Walks the task's ``find`` dependency results, classifies every
    matching path (duplicated / invalid / move_deleted / not_in_pool /
    bad_path), picks the most-recent valid copy if any, and feeds the
    result back through :func:`_apply_storage_update`.
    """
    if task.depending_status != "finished":
        return
    if not Storage.exists(storage_id):
        return
    storage = Storage(storage_id)
    for dependency in task.dependencies:
        if dependency.task != "find":
            continue
        storage.storages_with_uuid = list()
        dependency_results = (dependency.result or {}).get("matching_files", [])
        if not dependency_results:
            if (dependency.result or {}).get("status") == "deleted":
                _apply_storage_update(
                    {
                        "id": storage_id,
                        "status": "deleted",
                        "storages_with_uuid": [],
                    }
                )
                await send_status_socket(
                    redis_manager, storage_id, "deleted", task.user_id
                )
            return

        invalid_storages = []
        move_deleted_storages = []
        duplicated_storages = []
        not_in_pool_storages = []
        bad_path_storages = []
        matching_storage = None
        for storage_data in dependency_results:
            path = storage_data["path"]
            data = storage_data.get("storage_data", {})
            if (
                not data
                or f"/{storage_id}.qcow2" not in path
                or data.get("qemu-img-info", {}).get("virtual-size", 0) == 0
            ):
                invalid_storages.append(storage_data)
                continue
            if f"/deleted/{storage_id}" in path:
                move_deleted_storages.append(storage_data)
                continue
            if path == storage.path:
                matching_storage = storage_data
            valid_pool = _valid_storage_pool(storage, path)
            storage_data["storage_pool"] = valid_pool
            if valid_pool is None:
                not_in_pool_storages.append(storage_data)
            elif valid_pool is False:
                bad_path_storages.append(storage_data)
            else:
                duplicated_storages.append(storage_data)

        duplicated_storages.sort(key=lambda x: x["mtime"], reverse=True)

        def _uuid_list_from(pool_duplicates):
            return (
                [{"status": "duplicated", "path": s["path"]} for s in pool_duplicates]
                + [{"status": "invalid", "path": s["path"]} for s in invalid_storages]
                + [
                    {"status": "move_deleted", "path": s["path"]}
                    for s in move_deleted_storages
                ]
                + [
                    {"status": "not_in_pool", "path": s["path"]}
                    for s in not_in_pool_storages
                ]
                + [{"status": "bad_path", "path": s["path"]} for s in bad_path_storages]
            )

        if (
            matching_storage
            and duplicated_storages
            and matching_storage["path"] == duplicated_storages[0]["path"]
        ):
            storage.set_storage_pool(duplicated_storages[0]["storage_pool"])
            duplicated_storages.pop(0)
            found_status = matching_storage["storage_data"]["status"]
            # Preserve "recycled" status - don't overwrite with "ready"
            if found_status == "ready" and storage.status == "recycled":
                found_status = "recycled"
            update_payload = {
                "id": storage_id,
                "status": found_status,
                "qemu-img-info": matching_storage["storage_data"]["qemu-img-info"],
                "storages_with_uuid": _uuid_list_from(duplicated_storages),
            }
            _apply_storage_update(update_payload)
            await send_status_socket(
                redis_manager, storage_id, found_status, task.user_id
            )
            return

        if duplicated_storages:
            first_storage = duplicated_storages.pop(0)
            storage.set_storage_pool(first_storage["storage_pool"])
            found_status = first_storage["storage_data"]["status"]
            if found_status == "ready" and storage.status == "recycled":
                found_status = "recycled"
            update_payload = {
                "id": storage_id,
                "status": found_status,
                "qemu-img-info": first_storage["storage_data"]["qemu-img-info"],
                "storages_with_uuid": _uuid_list_from(duplicated_storages),
            }
            _apply_storage_update(update_payload)
            await send_status_socket(
                redis_manager, storage_id, found_status, task.user_id
            )
            return

        _apply_storage_update(
            {
                "id": storage_id,
                "status": "deleted",
                "storages_with_uuid": _uuid_list_from([]),
            }
        )
        await send_status_socket(redis_manager, storage_id, "deleted", task.user_id)


# Resolved lazily at module load — keeps the import side-effect-free.
# Used only by handle_update_status.
_ITEM_CLASS_MAP = {
    "storage": Storage,
    "domain": Domain,
    # ``media`` is registered by task_results.media to avoid a circular
    # import between storage/media handler modules; see media.py.
}


def register_item_class(name, model):
    """Register an item class for :func:`handle_update_status` dispatch.

    Exists so ``task_results.media`` can register the ``Media`` model
    after import without storage.py importing media.py.
    """
    _ITEM_CLASS_MAP[name.lower()] = model
