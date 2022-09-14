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

from .decorators import is_admin


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


@app.route("/scheduler/action/<action_id>", methods=["GET"])
@is_admin
def action(payload, action_id):
    return (
        json.dumps(app.scheduler.get_action_kwargs(action_id)),
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


@app.route("/scheduler/<type>/<kind>/<action>/<hour>/<minute>", methods=["POST"])
@is_admin
def add(payload, type, kind, action, hour, minute):
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
@is_admin
def delete(payload, job_id):
    return (
        json.dumps(app.scheduler.remove_job(job_id)),
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
