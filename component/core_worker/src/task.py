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
from isardvdi_common.api_rest import ApiRest
from isardvdi_common.domain import Domain
from isardvdi_common.media import Media
from isardvdi_common.storage import Storage, StoragePool
from isardvdi_common.task import Task
from requests.exceptions import HTTPError
from rethink_custom_base import export_r as r
from rq import get_current_job


def socketio(data):
    ApiRest().post("/socketio", data=data)


@cached(TTLCache(maxsize=10, ttl=60))
def user_info(user_id):
    """Get cached user info form isard-api.

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
        except:
            user = None
        if user:
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
                    globals()[item_class.capitalize()](item_id, status=item_status)
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
        backing_file = getattr(storage, "qemu-img-info").get("full-backing-filename")
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
                storage.parent = Storage.create_from_path(backing_file).id
        else:
            storage.parent = None
        storage.status = "ready"


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
            storage_object = Storage(**storage_dict)
            if storage_dict.get("status") in ["deleted", "orphan", "broken_chain"]:
                for domain in (
                    storage_object.domains + storage_object.domains_derivatives
                ):
                    domain.status = "Failed"
                for child in storage_object.derivatives:
                    if child.status != "deleted":
                        child.status = "orphan"
            if storage_dict.get("status") == "ready":
                for domain in storage_object.domains:
                    domain.status = "Stopped"

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
                    "check_existence",
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
        storage_object = Storage(**storage_dict)
        if storage_dict.get("status") in ["deleted", "orphan", "broken_chain"]:
            for domain in storage_object.domains + storage_object.domains_derivatives:
                domain.status = "Failed"
            for child in storage_object.derivatives:
                if child.status != "deleted":
                    child.status = "orphan"
        if storage_dict.get("status") == "ready":
            for domain in storage_object.domains:
                domain.status = "Stopped"


def storage_add(**storage_dict):
    """
    Add storage to database.

    :param storage_dict: Storage data
    :type storage_dict: dict
    """
    Storage(**storage_dict)


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
        f"/recycle_bin/update_task",
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
            Media(**media_dict)
        else:
            for dependency in task.dependencies:
                if dependency.task in ("check_media_existence"):
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


def domain_change_storage(domain_id, storage_id):
    """
    Change a domain's storage.

    :param domain_id: Domain ID
    :type domain_id: str
    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Domain.exists(domain_id):
        return
    domain = Domain(domain_id)
    c_dict = domain.create_dict
    c_dict["hardware"]["disks"][0]["storage_id"] = storage_id
    domain.create_dict = c_dict
    domain.force_update = (
        True  # Engine will recreate it's hardware dict before next start
    )


def storage_domains_force_update(storage_id):
    """
    Force update domains of a storage.

    :param storage_id: Storage ID
    :type storage_id: str
    """
    if not Storage.exists(storage_id):
        return
    for domain in Storage(storage_id).domains:
        domain.force_update = (
            True  # Engine will recreate it's hardware dict before next start
        )


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
            storage_update(
                **{
                    "id": storage_id,
                    "status": matching_storage["storage_data"]["status"],
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
            storage_update(
                **{
                    "id": storage_id,
                    "status": first_storage["storage_data"]["status"],
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
        except:
            user = None

        if user:
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
