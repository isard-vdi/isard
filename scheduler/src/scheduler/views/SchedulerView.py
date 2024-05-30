#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

from flask import request

from scheduler import app

from ..lib.exceptions import Error
from .decorators import (
    has_token,
    is_admin,
    is_admin_or_manager,
    itemExists,
    ownsCategoryId,
)


@app.route("/scheduler/healthcheck", methods=["GET"])
def healthcheck():
    return ""


@app.route("/scheduler/actions", methods=["GET"])
@is_admin
def actions(payload):
    return (
        json.dumps(app.scheduler.list_actions()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/recycle_bin_delete/max_time", methods=["GET"])
@has_token
def max_time(payload):
    max_time = app.scheduler.get_max_time(
        None if payload["role_id"] == "admin" else payload["category_id"]
    )
    max_time_admin = app.scheduler.get_max_time_admin()
    return (
        json.dumps({"time": max_time, "max_time": max_time_admin}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/action/<action_id>", methods=["GET"])
@is_admin
def action(payload, action_id):
    return (
        json.dumps(app.scheduler.get_action_kwargs(action_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/scheduler/recycle_bin_delete/max_time_category/<category_id>", methods=["GET"]
)
@is_admin_or_manager
def max_time_category(payload, category_id=None):
    if category_id:
        ownsCategoryId(payload, category_id)
    max_time = app.scheduler.get_max_time_category(category_id)
    return (
        json.dumps(max_time),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler", methods=["GET"])
@app.route("/scheduler/<job_id>", methods=["GET"])
@is_admin
def get(payload, job_id=None):
    jobs = app.scheduler.load_jobs(job_id)
    for job in jobs:
        job["date"] = job["date"].strftime("%Y-%m-%dT%H:%M%z")
    return (
        json.dumps(jobs),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/kind/<kind>", methods=["GET"])
@is_admin
def get_kind(payload, kind):
    jobs = [job for job in app.scheduler.load_jobs() if job["kind"] == kind]
    for job in jobs:
        job["date"] = job["date"].strftime("%Y-%m-%dT%H:%M%z")
    return (
        json.dumps(jobs),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/not_date", methods=["GET"])
@is_admin
def get_not_date(payload):
    jobs = [job for job in app.scheduler.load_jobs() if job["kind"] != "date"]
    return (
        json.dumps(jobs),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/<type>/<kind>/<action>/<hour>/<minute>/<id>", methods=["POST"])
@app.route("/scheduler/<type>/<kind>/<action>/<hour>/<minute>", methods=["POST"])
@is_admin
def add(payload, type, kind, action, hour, minute, id=None):
    try:
        custom_parameters = request.get_json()
    except:
        custom_parameters = None
    return (
        json.dumps(
            app.scheduler.add_job(
                type,
                kind,
                action,
                hour,
                minute,
                id,
                kwargs=custom_parameters.pop("kwargs", None),
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/advanced/interval/<type>/<action>", methods=["POST"])
@is_admin
def add_advanced_interval(payload, type, action):
    data = request.get_json()
    # id=None, weeks=0, days=0, hours=0, minutes=0, seconds=0, start_date=None, end_date=None, timezone=None, jitter=None, kwargs=None
    return json.dumps(
        app.scheduler.add_advanced_interval_job(
            type, action, data, data.pop("id", None), data.pop("kwargs", None)
        )
    )


@app.route("/scheduler/advanced/date/<type>/<action>", methods=["POST"])
@is_admin
def add_advanced_date(payload, type, action):
    data = request.get_json()
    return json.dumps(
        app.scheduler.add_advanced_date_job(
            type, action, data["date"], data.pop("id", None), data.pop("kwargs", None)
        )
    )


@app.route("/scheduler/<job_id>", methods=["DELETE"])
@app.route("/scheduler/delete_jobs", methods=["DELETE"])
@is_admin
def delete(payload, job_id=False):
    if not job_id:
        data = request.get_json()
        jobs_ids = data.get("jobs_ids")
        for job_id in jobs_ids:
            app.scheduler.remove_job(job_id)
    else:
        app.scheduler.remove_job(job_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/startswith/<job_id>", methods=["DELETE"])
@is_admin
def delete_startswith(payload, job_id):
    return (
        json.dumps(app.scheduler.remove_job_startswith(job_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/delete/recycle_bin/<category>", methods=["DELETE"])
@is_admin_or_manager
def delete_action(payload, category):
    return (
        json.dumps(app.scheduler.remove_job(category + ".recycle_bin_delete")),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/recycle_bin/<max_time>/<category_id>", methods=["PUT"])
@app.route("/scheduler/recycle_bin/<max_time>", methods=["PUT"])
@is_admin_or_manager
def add_recyclebin(payload, max_time, category_id=None):
    kwargs = {"max_delete_period": max_time}

    action = (
        "recycle_bin_delete"
        if payload["role_id"] == "manager" or category_id
        else "recycle_bin_delete_admin"
    )
    if payload["role_id"] == "manager" or category_id:
        if payload["role_id"] == "manager":
            category_id = payload["category_id"]
        ownsCategoryId(payload, category_id)
        kwargs["category"] = category_id
        itemExists("categories", category_id)
        admin_max_time = app.scheduler.get_max_time()
        if admin_max_time != "null" and int(max_time) > int(admin_max_time):
            raise Error(
                "forbidden",
                "Category max_time can not be greater than " + admin_max_time,
            )
        try:
            app.scheduler.remove_job(category_id + ".recycle_bin_delete")
        except:
            pass
        job_id = category_id + ".recycle_bin_delete"
    else:
        if payload["role_id"] != "admin":
            raise Error("forbidden", "Not enough rights")
        app.scheduler.remove_job_action("recycle_bin_delete")
        try:
            app.scheduler.remove_job("admin.recycle_bin_delete_admin")
        except:
            pass
        job_id = "admin.recycle_bin_delete_admin"
    if max_time != "null":
        try:
            job_id = app.scheduler.add_job(
                "system",
                "interval",
                action,
                "00",
                "05",
                id=job_id,
                kwargs=kwargs,
            )
            return (
                json.dumps(job_id),
                200,
                {"Content-Type": "application/json"},
            )
        except:
            raise Error("bad_request", "Unable to add job")
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/recycle_bin/old_entries/<action>", methods=["PUT"])
@is_admin
def add_recyclebin_old_entries(payload, action):
    # if action not in ["archive", "delete"]:
    #     raise Error("bad_request", 'Action must be "archive" or "delete"')
    if action not in ["delete", "none"]:
        raise Error("bad_request", 'Action must be "delete"')
    app.scheduler.remove_job(f"recycle_bin_old_entries_action_delete")
    # app.scheduler.remove_job(f"recycle_bin_old_entries_action_archive")
    if action == "none":
        return (json.dumps({}), 200, {"Content-Type": "application/json"})
    else:
        return (
            json.dumps(
                app.scheduler.add_job(
                    "system",
                    "interval",
                    f"recycle_bin_old_entries_action_{action}",
                    "00",
                    "05",
                    f"recycle_bin_old_entries_action_{action}",
                    kwargs={},
                )
            ),
            200,
            {"Content-Type": "application/json"},
        )
