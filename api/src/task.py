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


def storage_ready(
    storage_ids=None,
    on_finished_storage_ids=None,
    on_failed_storage_ids=None,
    on_canceled_delete_storage_ids=None,
):
    """
    Set storage as ready

    :param storage_ids: Storage IDs to be ready always
    :type storage_ids: list
    :param on_failed_storage_ids: Storage IDs to be ready if depending tasks failed
    :type on_failed_storage_ids: list
    :param on_finished_storage_ids: Storage IDs to be ready if depending tasks success
    :type on_finished_storage_ids: list
    :param on_canceled_delete_storage_ids: Storage IDs to be marked as teleted if depending tasks was canceled
    :type on_canceled_delete_storage_ids: list
    """
    task = Task(get_current_job().id)
    ready_storage_ids = []
    if storage_ids:
        ready_storage_ids.extend(storage_ids)
    if on_finished_storage_ids and task.depending_status == "finished":
        ready_storage_ids.extend(on_finished_storage_ids)
    if on_failed_storage_ids and task.depending_status == "failed":
        ready_storage_ids.extend(on_failed_storage_ids)
    for storage_id in ready_storage_ids:
        Storage(storage_id, status="ready")
    if on_canceled_delete_storage_ids and task.depending_status == "canceled":
        for storage_id in on_canceled_delete_storage_ids:
            Storage(storage_id, status="deleted")
