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

from flask import jsonify

from api import app

from ..libv2.task import Task
from .decorators import has_token, is_admin_or_manager, ownsUserId


@app.route("/api/v3/tasks", methods=["GET"])
@has_token
def user_tasks(payload):
    """
    Endpoint to get user tasks.

    :param payload: Data from JWT
    :type payload: dict
    :return: User tasks as dict
    :rtype: flask.Response
    """
    return jsonify(
        [task.to_dict() for task in Task.get_by_user(payload.get("user_id"))]
    )


@app.route("/api/v3/admin/tasks", methods=["GET"])
@is_admin_or_manager
def admin_tasks(payload):
    """Endpont to get all tasks.

    :param payload: Data from JWT
    :type payload: dict
    :return: As admin a list of all user tasks as dict, as manager a list of
        all tasks of users in their category
    :rtype: flask.Response
    """
    tasks = []
    for task in Task.get_all():
        if task.user_id:
            try:
                ownsUserId(payload, task.user_id)
            except Error as error:
                if error.args[0] == "forbidden":
                    pass
                else:
                    raise error
            else:
                tasks.append(task)
    return jsonify([task.to_dict() for task in tasks])
