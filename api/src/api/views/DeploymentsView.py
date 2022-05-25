# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import jsonify, request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_deployments import ApiDeployments

deployments = ApiDeployments()

from .decorators import allowedTemplateId, has_token, is_admin


@app.route("/api/v3/deployment/<deployment_id>", methods=["GET"])
@has_token
def api_v3_deployment(payload, deployment_id):
    return (
        json.dumps(deployments.Get(payload["user_id"], deployment_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployments", methods=["GET"])
@has_token
def api_v3_deployments(payload):
    return (
        json.dumps(deployments.List(payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )
