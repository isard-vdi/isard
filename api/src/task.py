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

from api._common.storage import Storage
from api.libv2.api_users import ApiUsers
from api.libv2.task import Task
from rq import get_current_job

from api import socketio


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
    socketio.emit(
        "task",
        task_as_json,
        namespace="/administrators",
        room="admins",
    )
    socketio.emit(
        "task",
        task_as_json,
        namespace="/administrators",
        room=ApiUsers().Get(task.user_id).get("category"),
    )
    socketio.emit(
        "task",
        task_as_json,
        namespace="/userspace",
        room=task.user_id,
    )


def storage_status(statuses={}):
    """
    Set storage status depending on task status

    :param statuses: Nested dictionary that contains task status and status of storages.
        First level keys are the status of the task, nested keys are the status for storage.
        First level "_all" key is to set storage status for all task status.
        Example:
        ```
            {
                "_all": {
                    # Set storage_id1 to "ready" for all task statuses
                    "ready": ["storage_id1"],
                },
                "finished": {
                    # Set storage_id2 to "ready" if task was finished
                    "ready": ["storage_id2"],
                    # Set storage_id4 to "deleted" if task was finished
                    "deleted": ["storage_id4"],
                },
                "canceled": {
                    # Set storage_id2 and storage_id3 to "deleted" if task was canceled
                    "deleted": ["storage_id2", "storage_id3"],
                    # Set storage_id4 to "maintenance" if task was canceled
                    "maintenance": ["storage_id4"],
                },
                "failed": {
                    # Set storage_id2 to "maintenance" if task was failed
                    "maintenance": ["storage_id2"],
                }
            }
        ```
    :type statuses: dict
    """
    task = Task(get_current_job().id)
    for storage_statuses_storage_ids in [
        statuses.get("_all", {}),
        statuses.get(task.depending_status, {}),
    ]:
        for storage_status, storage_ids in storage_statuses_storage_ids.items():
            for storage_id in storage_ids:
                Storage(storage_id, status=storage_status)
