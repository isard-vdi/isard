#
#   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_queues import (
    QUEUE_REGISTRIES,
    delete_jobs,
    get_auto_delete_kwargs,
    get_old_jobs,
    get_queue_jobs,
    get_queues,
    set_auto_delete_enabled,
    set_auto_delete_max_time,
    set_auto_delete_queue_registries,
    workers_with_subscribers,
)
from .decorators import is_admin


@app.route("/api/v3/queues", methods=["GET"])
@is_admin
def queues_jobs(payload):
    data = []
    for queue in get_queues():
        q = get_queue_jobs(queue.name)
        q["id"] = queue.name
        data.append(q)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/consumers", methods=["GET"])
@is_admin
def queues(payload):
    return (
        json.dumps(workers_with_subscribers()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/old_tasks/<older_than>", methods=["GET"])
@is_admin
def get_queues_old_tasks(payload, older_than):
    return json.dumps(get_old_jobs(int(older_than)))


@app.route("/api/v3/queues/old_tasks", methods=["DELETE"])
@is_admin
def api_v3_delete_queues_old_tasks(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    if not data.get("older_than"):
        raise Error(
            "bad_request",
            "older_than parameter is required.",
            traceback.format_exc(),
        )

    old_jobs = get_old_jobs(data["older_than"], rtype="job")
    delete_ok, delete_errors = delete_jobs(old_jobs)

    return json.dumps(
        {
            "ok": delete_ok,
            "errors": delete_errors,
        }
    )


@app.route("/api/v3/queues/old_tasks/config/max_time/<max_time>", methods=["PUT"])
@is_admin
def api_v3_set_queues_old_tasks_max_time_config(payload, max_time):
    max_time = 86400 if int(max_time) < 86400 else int(max_time)  # 24 hours

    set_auto_delete_enabled(True)

    return (
        json.dumps(set_auto_delete_max_time(max_time)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/old_tasks/config/queue_registries", methods=["PUT"])
@is_admin
def api_v3_set_queues_old_tasks_queue_registries_config(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    if not data.get("queue_registries"):
        data["queue_registries"] = []

    return (
        json.dumps(set_auto_delete_queue_registries(data["queue_registries"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/old_tasks/config/enabled", methods=["PUT"])
@is_admin
def api_v3_disable_queues_old_tasks_config(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    if not data.get("enabled") and not isinstance(data["enabled"], bool):
        raise Error(
            "bad_request",
            "enabled parameter is required.",
            traceback.format_exc(),
        )

    return (
        json.dumps(set_auto_delete_enabled(data["enabled"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/old_tasks/config", methods=["GET"])
@is_admin
def api_v3_get_queues_old_tasks_config(payload):
    return (
        json.dumps(get_auto_delete_kwargs()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/queues/old_tasks/auto", methods=["DELETE"])
@is_admin
def api_v3_delete_queues_old_tasks_auto(payload):
    """
    Deletes all tasks based on the configuration in the db
    """
    kwargs = get_auto_delete_kwargs()
    if kwargs.get("enabled", False) == False:
        return json.dumps(
            {
                "ok": [],
                "errors": [],
            }
        )

    if kwargs.get("older_than") is None:
        raise Error(
            "bad_request",
            "No max_time set in the db.",
        )

    if kwargs.get("queue_registries") is None:
        raise Error(
            "bad_request",
            "No queue_registries set in the db.",
        )

    old_jobs = get_old_jobs(
        kwargs["older_than"],
        rtype="job",
        registries=kwargs["queue_registries"],
    )
    delete_ok, delete_errors = delete_jobs(old_jobs)

    return json.dumps(
        {
            "ok": delete_ok,
            "errors": delete_errors,
        }
    )
