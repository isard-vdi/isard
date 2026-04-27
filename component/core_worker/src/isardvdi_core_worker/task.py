#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

import json

from cachetools import TTLCache, cached
from isardvdi_common.connections.api_rest import ApiRest
from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.media import Media
from isardvdi_common.models.storage import Storage, StoragePool
from isardvdi_common.models.task import Task
from requests.exceptions import HTTPError
from rq import get_current_job
from socketio import RedisManager

redis_manager = RedisManager(socketio_url(), write_only=True)

# Domain statuses that represent a domain that is not yet (or no longer) runnable
# and is waiting for its storage to be ready. Only these can be safely promoted to
# "Stopped" when a storage transitions to "ready" — running or transitional
# statuses must be left alone (otherwise we race with the engine/broom and create
# a Started↔Stopped flap loop).
_DOMAIN_PRE_READY_STATUSES = frozenset(
    {
        "Downloading",
        "Downloaded",
        "DiskNew",
        "Failed",
        "Unknown",
        # Creating / CreatingDisk / CreatingDiskFromScratch /
        # CreatingAndStarting are handled by the Phase A task chain —
        # ``domain_change_storage`` (the trailing dependent of
        # ``storage_update``) transitions them to ``CreatingDomain`` so
        # engine's libvirt-define can run. Promoting them here would
        # short-circuit the chain and leave the domain at ``Stopped``
        # with no libvirt XML, so non-persistent desktops never
        # auto-start.
        "CreatingDomain",
        "CreatingDomainFromDisk",
        # ``CreatingTemplate`` is set by ``CommonTemplates.new_template`` on
        # both the source desktop and the new template row before firing
        # ``Storage.enqueue_template_creation_chain_from_desktop``. The
        # chain's trailing pair of ``storage_update`` tasks (one for the
        # template storage, one for the desktop storage) call
        # ``_promote_domains_to_stopped`` once each storage transitions to
        # ``ready`` — that's the only path back to ``Stopped`` for the two
        # domains, so this entry is load-bearing. Without it, both rows
        # stay in ``CreatingTemplate`` indefinitely after a successful
        # chain. ``CreatingTemplateDisk`` and ``TemplateDiskCreated`` are
        # legacy engine-SSH-only states with no remaining writers and
        # stay out of the set.
        "CreatingTemplate",
        # Maintenance is set by Storage.set_maintenance(action) on every linked
        # domain when the storage enters a paired maintenance/ready cycle
        # (resize, sparsify, virt-win-reg, etc.). The cycle ends with
        # task.storage_update receiving status="ready", which is the only path
        # back to Stopped for those domains. Without this entry the desktops
        # are stuck in Maintenance after every successful resize.
        "Maintenance",
    }
)


def _promote_domains_to_stopped(storage_object):
    """Promote only domains waiting on storage to ``Stopped``.

    Skips domains currently running or in a transitional status so we never
    yank a live VM from under the engine's state machine.
    """
    for domain in storage_object.domains:
        if domain.status in _DOMAIN_PRE_READY_STATUSES:
            domain.status = "Stopped"
            domain.current_action = None


def socketio(data):
    for event in data:
        redis_manager.emit(**event)
    ApiRest().post("/admin/socketio", data=data)


@cached(TTLCache(maxsize=10, ttl=60))
def user_info(user_id):
    """Get cached user info from isard-apiv4.

    :param user_id: User ID
    :type user_id: str
    :return: User info
    :rtype: dict
    """
    try:
        return ApiRest().get(f"/admin/user/{user_id}/exists")
    except HTTPError as http_err:
        if http_err.response.status_code == 404:
            return None
        else:
            raise


def feedback(task_id=None):
    """
    Send task data to users via SocketIO. If no `task_id` provided, send data
    of the task that current job depends on.

    :param task_id: Changed task ID
    :type task_id: str
    :return: None
    :rtype: None
    """
    if task_id is None:
        task_id = get_current_job().dependency.id
    task = Task(task_id)
    task_as_json = json.dumps(task.to_dict())
    if task.user_id != "isard-scheduler":
        try:
            user = user_info(task.user_id)
        except Exception:
            user = None
        if isinstance(user, dict):
            socketio(
                [
                    {
                        "event": "task",
                        "data": task_as_json,
                        "namespace": "/administrators",
                        "room": "admins",
                    },
                    {
                        "event": "task",
                        "data": task_as_json,
                        "namespace": "/administrators",
                        "room": user.get("category"),
                    },
                    {
                        "event": "task",
                        "data": task_as_json,
                        "namespace": "/userspace",
                        "room": task.user_id,
                    },
                    # Task queue ws result
                    {
                        "event": task.queue.split(".")[0],
                        "data": json.dumps(task.result),
                        "namespace": "/administrators",
                        "room": "admins",
                    },
                    {
                        "event": task.queue.split(".")[0],
                        "data": json.dumps(task.result),
                        "namespace": "/administrators",
                        "room": user.get("category"),
                    },
                    {
                        "event": task.queue.split(".")[0],
                        "data": json.dumps(task.result),
                        "namespace": "/administrators",
                        "room": task.user_id,
                    },
                ]
            )
        else:
            socketio(
                [
                    {
                        "event": "task",
                        "data": task_as_json,
                        "namespace": "/administrators",
                        "room": "admins",
                    },
                    {
                        "event": task.queue.split(".")[0],
                        "data": json.dumps(task.result),
                        "namespace": "/administrators",
                        "room": "admins",
                    },
                ]
            )


def update_status(statuses={}):
    """
    Set status on items depending on task status

    :param statuses: Nested dictionary that contains task status and status for items.
        First level keys are the status of the task, nested keys are the status for items.
        First level "_all" key is to set status for all task status.
        Example:
        ```
            {
                "_all": {
                    # Set storage_id1 and media_id1 to "ready" for all task statuses
                    "ready": {
                        "storage": ["storage_id1"],
                        "media": ["media_id1"],
                    }
                },
                "finished": {
                    # Set storage_id2 to "ready" if task was finished
                    "ready": {
                        "storage": ["storage_id2"],
                    }
                    # Set storage_id4 to "deleted" if task was finished
                    "deleted": {
                        "storage": ["storage_id4"],
                    }
                },
                "canceled": {
                    # Set storage_id2 and storage_id3 to "deleted" if task was canceled
                    "deleted": {
                        storage: ["storage_id2", "storage_id3"],
                    }
                    # Set storage_id4 and media_id2 to "maintenance" if task was canceled
                    "maintenance": {
                        "storage": ["storage_id4"],
                        "media": ["media_id2"],
                    }
                },
                "failed": {
                    # Set storage_id2 to "maintenance" if task was failed
                    "maintenance": {
                        "storage": ["storage_id2"],
                    }
                }
            }
        ```
    :type statuses: dict
    """
    task = Task(get_current_job().id)
    for item_statuses_item_ids in [
        statuses.get("_all", {}),
        statuses.get(task.depending_status, {}),
    ]:
        for item_status, items in item_statuses_item_ids.items():
            for item_class, item_ids in items.items():
                for item_id in item_ids:
                    globals()[item_class.capitalize()].init_document(
                        item_id, status=item_status
                    )
                    if item_class.lower() == "storage":
                        send_storage_status_socket(item_id, item_status)


def storage_update_parent(storage_id):
    """
    Update storage parent.

    :param storage_id: Storage ID
    :type storage_id: str
    """
    task = Task(get_current_job().id)
    if task.depending_status == "finished":
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


def storage_update(**storage_dict):
    """
    Update storage if task success.

    :param storage_dict: Storage data
    :type storage_dict: dict
    """
    task = Task(get_current_job().id)
    if task.depending_status == "finished":
        if storage_dict:
            if not Storage.exists(storage_dict["id"]):
                return  # Storage was deleted
            storage_object = Storage.init_document(**storage_dict)
            if storage_dict.get("status") in ["deleted", "orphan", "broken_chain"]:
                for domain in (
                    storage_object.domains + storage_object.domains_derivatives
                ):
                    domain.status = "Failed"
                for child in storage_object.derivatives:
                    if child.status != "deleted":
                        child.status = "orphan"
            if storage_dict.get("status") == "ready":
                _promote_domains_to_stopped(storage_object)

            send_storage_status_socket(
                storage_dict["id"],
                storage_dict.get("status"),
                task.user_id,
            )
        else:
            for dependency in task.dependencies:
                if dependency.task in (
                    "qemu_img_info",
                    "qemu_img_info_backing_chain",
                ):
                    storage_update(**dependency.result)
                if dependency.task == "check_backing_filename":
                    for result in dependency.result:
                        storage_update(**result)


def storage_update_dict(**storage_dict):
    """
    Update storage with provided data.

    :param storage_dict: Storage data
    :type storage_dict: dict
    """
    if storage_dict:
        if not Storage.exists(storage_dict["id"]):
            return  # Storage was deleted
        storage_object = Storage.init_document(**storage_dict)
        if storage_dict.get("status") in ["deleted", "orphan", "broken_chain"]:
            for domain in storage_object.domains + storage_object.domains_derivatives:
                domain.status = "Failed"
            for child in storage_object.derivatives:
                if child.status != "deleted":
                    child.status = "orphan"
        if storage_dict.get("status") == "ready":
            _promote_domains_to_stopped(storage_object)

        send_storage_status_socket(
            storage_dict["id"],
            storage_dict.get("status"),
        )


def storage_add(**storage_dict):
    """
    Add storage to database.

    :param storage_dict: Storage data
    :type storage_dict: dict
    """
    Storage.init_document(**storage_dict)


def storage_delete(storage_id):
    """
    Delete storage from database

    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Storage.exists(storage_id):
        return
    if Storage(storage_id).status == "deleted":
        Storage.delete(storage_id)


def recycle_bin_update(**recycle_bin_dict):
    """
    Update recycle bin if task success.
    """
    task = Task(get_current_job().dependency.dependency.id)
    ApiRest().put(
        "/item/recycle-bin/update-task",
        data={
            "recycle_bin_id": recycle_bin_dict["recycle_bin_id"],
            "id": task.id,
            "status": task.status,
        },
    )


def media_update(**media_dict):
    """
    Update media if task success.

    :param media_dict: Media data
    :type media_dict: dict
    """
    task = Task(get_current_job().id)
    if task.depending_status == "finished":
        if media_dict:
            Media.init_document(**media_dict)
        else:
            for dependency in task.dependencies:
                if dependency.task in ("check_media_existence", "download_url"):
                    media_update(**dependency.result)


def delete_task(task_id):
    """
    Cancel task if task is queued.
    :param task_id: Task ID
    :type task_id: str
    """
    if Task.exists(task_id) and Task(task_id).status == "queued":
        Task(task_id).cancel()


def send_storage_socket_user(event, storage_id):
    """
    Send socket to user.
    :param event: Event name
    :type event: str
    :param storage_id: ID of the storage
    :type storage_id: str
    """
    if not Storage.exists(storage_id):
        return
    storage = Storage(storage_id)
    socketio(
        [
            {
                "event": event,
                "data": {
                    "id": storage.id,
                    "status": storage.status,
                    "size": getattr(storage, "qemu-img-info")["virtual-size"],
                },
                "namespace": "/userspace",
                "room": storage.user_id,
            }
        ]
    )


_DOMAIN_CREATE_TO_CREATING_DOMAIN = frozenset(
    {
        "Creating",
        "CreatingAndStarting",
        "CreatingDisk",
        "CreatingDiskFromScratch",
    }
)


_DOMAIN_CREATING_TO_CREATING_DISK = frozenset(
    {
        "Creating",
        "CreatingDiskFromScratch",
    }
)


def domain_creating_disk(domain_id):
    """Advance a domain from its initial create status to ``CreatingDisk``
    at the start of the task-based creation chain.

    Template-from-template and desktop-from-media both land here: apiv4
    inserts with ``Creating`` for the former and ``CreatingDiskFromScratch``
    for the latter; either one flips to ``CreatingDisk`` so the change-feed
    emits an intermediate signal while the storage worker is still
    producing the qcow2. ``parse_frontend_desktop_status`` collapses this
    to ``Creating`` for end-user display. Leaves any other status alone.

    :param domain_id: Domain ID
    :type domain_id: str
    """
    if not Domain.exists(domain_id):
        return
    domain = Domain(domain_id)
    if domain.status in _DOMAIN_CREATING_TO_CREATING_DISK:
        domain.status = "CreatingDisk"


def domain_change_storage(domain_id, storage_id):
    """
    Wire a storage into a domain's first disk and, when the domain is in
    a pre-libvirt creation status, advance it to ``CreatingDomain`` so the
    engine's libvirt-define handler takes over.

    Used in two flows:
      * the task-based create chain — finalizes a freshly-created qcow2
        by linking it to the domain and flipping the status forward.
      * the storage recreate chain — swaps a domain from its old storage
        to a newly-rebuilt one.

    In the create flow, when the upstream chain failed the storage row
    is left at a non-"ready" status; raising here propagates the failure
    to the trailing ``update_status`` dependent, which marks the domain
    and storage as ``Failed``. The recreate flow never puts the domain
    in a create allow-list status, so its ordering (storage still
    "non_existing" when this task runs) is unaffected.

    :param domain_id: Domain ID
    :type domain_id: str
    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Domain.exists(domain_id):
        return
    if not Storage.exists(storage_id):
        return
    domain = Domain(domain_id)
    storage = Storage(storage_id)

    if domain.status in _DOMAIN_CREATE_TO_CREATING_DOMAIN and storage.status != "ready":
        raise Exception(
            f"Cannot finalize domain {domain_id}: storage {storage_id} is "
            f"not ready (status={storage.status!r})."
        )

    c_dict = domain.create_dict
    disk = c_dict["hardware"]["disks"][0]
    disk["storage_id"] = storage_id
    disk["file"] = storage.path
    disk["parent"] = storage.parent
    domain.create_dict = c_dict

    if domain.status in _DOMAIN_CREATE_TO_CREATING_DOMAIN:
        domain.status = "CreatingDomain"


def _valid_storage_pool(storage, new_path):
    """
    Update the storage pool if the new path matches the expected pool path.

    :param storage: The storage object to update.
    :param new_path: The new path to check.
    :param storage_data: Data related to the storage.
    :return: True if updated, False otherwise.
    """
    storage_pools = StoragePool.get_by_path(new_path)
    if not storage_pools:
        return None

    pool_path = storage.get_storage_pool_path(storage_pools[0])

    expected_path = f"{pool_path}/{storage.id}.qcow2" if pool_path else None
    if expected_path == new_path:
        return storage_pools[0]

    return False


def storage_update_pool(storage_id):
    """
    Update storage pool paths based on task dependencies.

    :param storage_id: The ID of the storage to update.
    """
    task = Task(get_current_job().id)

    if task.depending_status != "finished":
        return

    if not Storage.exists(storage_id):
        return

    storage = Storage(storage_id)

    for dependency in task.dependencies:
        if dependency.task != "find":
            continue

        # Empty storages_with_uuid array before updating it
        storage.storages_with_uuid = list()

        dependency_results = dependency.result.get("matching_files", [])
        if not dependency_results:
            if dependency.result.get("status") == "deleted":
                storage_update(
                    **{
                        "id": storage_id,
                        "status": "deleted",
                        "storages_with_uuid": [],
                    }
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

        if (
            matching_storage
            and len(duplicated_storages)
            and matching_storage["path"] == duplicated_storages[0]["path"]
        ):
            # The actual storage is the most recent one
            storage.set_storage_pool(duplicated_storages[0]["storage_pool"])
            duplicated_storages.pop(0)
            # Preserve "recycled" status - don't overwrite with "ready"
            found_status = matching_storage["storage_data"]["status"]
            if found_status == "ready" and storage.status == "recycled":
                found_status = "recycled"
            storage_update(
                **{
                    "id": storage_id,
                    "status": found_status,
                    "qemu-img-info": matching_storage["storage_data"]["qemu-img-info"],
                    "storages_with_uuid": [
                        {"status": "duplicated", "path": s["path"]}
                        for s in duplicated_storages
                    ]
                    + [
                        {"status": "invalid", "path": s["path"]}
                        for s in invalid_storages
                    ]
                    + [
                        {"status": "move_deleted", "path": s["path"]}
                        for s in move_deleted_storages
                    ]
                    + [
                        {"status": "not_in_pool", "path": s["path"]}
                        for s in not_in_pool_storages
                    ]
                    + [
                        {"status": "bad_path", "path": s["path"]}
                        for s in bad_path_storages
                    ],
                }
            )
            return

        if len(duplicated_storages):
            first_storage = duplicated_storages.pop(0)
            storage.set_storage_pool(first_storage["storage_pool"])
            # Preserve "recycled" status - don't overwrite with "ready"
            found_status = first_storage["storage_data"]["status"]
            if found_status == "ready" and storage.status == "recycled":
                found_status = "recycled"
            storage_update(
                **{
                    "id": storage_id,
                    "status": found_status,
                    "qemu-img-info": first_storage["storage_data"]["qemu-img-info"],
                    "storages_with_uuid": [
                        {"status": "duplicated", "path": s["path"]}
                        for s in duplicated_storages
                    ]
                    + [
                        {"status": "invalid", "path": s["path"]}
                        for s in invalid_storages
                    ]
                    + [
                        {"status": "move_deleted", "path": s["path"]}
                        for s in move_deleted_storages
                    ]
                    + [
                        {"status": "not_in_pool", "path": s["path"]}
                        for s in not_in_pool_storages
                    ]
                    + [
                        {"status": "bad_path", "path": s["path"]}
                        for s in bad_path_storages
                    ],
                }
            )
            return

        storage_update(
            **{
                "id": storage_id,
                "status": "deleted",
                "storages_with_uuid": [
                    {"status": "duplicated", "path": s["path"]}
                    for s in duplicated_storages
                ]
                + [{"status": "invalid", "path": s["path"]} for s in invalid_storages]
                + [
                    {"status": "move_deleted", "path": s["path"]}
                    for s in move_deleted_storages
                ]
                + [
                    {"status": "not_in_pool", "path": s["path"]}
                    for s in not_in_pool_storages
                ]
                + [
                    {"status": "bad_path", "path": s["path"]} for s in bad_path_storages
                ],
            }
        )


def send_storage_status_socket(storage_id, status, user_id=None):
    """
    Send storage status to users.

    :param storage_id: Storage ID
    :type storage_id: str
    :param status: Storage status
    :type status: str
    """
    if user_id:
        try:
            user = user_info(user_id)
        except Exception:
            user = None

        if isinstance(user, dict):
            socketio(
                [
                    {
                        "event": "storage",
                        "data": json.dumps({"id": storage_id, "status": status}),
                        "namespace": "/administrators",
                        "room": user.get("category"),
                    },
                    {
                        "event": "storage",
                        "data": json.dumps({"id": storage_id, "status": status}),
                        "namespace": "/administrators",
                        "room": user_id,
                    },
                    {
                        "event": "storage",
                        "data": json.dumps({"id": storage_id, "status": status}),
                        "namespace": "/userspace",
                        "room": user_id,
                    },
                ]
            )

    socketio(
        [
            {
                "event": "storage",
                "data": json.dumps({"id": storage_id, "status": status}),
                "namespace": "/administrators",
                "room": "admins",
            }
        ]
    )
