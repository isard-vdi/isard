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
from isardvdi_common.storage import Storage
from isardvdi_common.task import Task
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
    return ApiRest().get(f"/admin/user/{user_id}")


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
    user = user_info(task.user_id)
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
            storage_object = Storage(**storage_dict)
            for domain in Domain.get_with_storage(storage_object):
                domain.force_update = True
            if storage_dict.get("status") == "deleted":
                for child in storage_object.children:
                    if child.status != "deleted":
                        child.status = "orphan"
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
