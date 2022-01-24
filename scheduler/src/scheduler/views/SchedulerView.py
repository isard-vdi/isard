# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
from datetime import datetime, timedelta

import pytz
from flask import request

#!flask/bin/python
# coding=utf-8
from scheduler import app

from ..lib.scheduler import Scheduler
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
    for job in jobs:
        job["date"] = job["date"].strftime("%Y-%m-%dT%H:%M%z")
    return (
        json.dumps(jobs),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/<kind>/<action>/<hour>/<minute>", methods=["POST"])
@is_admin
def add(payload, kind, action, hour, minute):
    log.debug("inside")
    try:
        custom_parameters = request.get_json()
    except:
        custom_parameters = None
    return (
        json.dumps(
            app.scheduler.add_job(kind, action, hour, minute, kwargs=custom_parameters)
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/advanced/interval/<action>", methods=["POST"])
@is_admin
def add_advanced_interval(payload, action):
    data = request.get_json()
    # id=None, weeks=0, days=0, hours=0, minutes=0, seconds=0, start_date=None, end_date=None, timezone=None, jitter=None, kwargs=None
    return json.dumps(
        app.scheduler.add_advanced_interval_job(
            action, data, data.pop("id", None), data.pop("kwargs", None)
        )
    )


@app.route("/scheduler/advanced/date/<action>", methods=["POST"])
@is_admin
def add_advanced_date(payload, action):
    data = request.get_json()
    return json.dumps(
        app.scheduler.add_advanced_date_job(
            action, data["date"], data.pop("id", None), data.pop("kwargs", None)
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
