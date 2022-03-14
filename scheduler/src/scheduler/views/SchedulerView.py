# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

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
    return (
        json.dumps(app.scheduler.load_jobs(job_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/<kind>/<action>/<hour>/<minute>", methods=["POST"])
@is_admin
def add(payload, kind, action, hour, minute):
    return (
        json.dumps(app.scheduler.add_job(kind, action, hour, minute)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/scheduler/<job_id>", methods=["DELETE"])
@is_admin
def delete(payload, job_id):
    return (
        json.dumps(app.scheduler.remove_job(job_id)),
        200,
        {"Content-Type": "application/json"},
    )
