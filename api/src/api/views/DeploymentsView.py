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

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_deployments import ApiDeployments

deployments = ApiDeployments()

from .decorators import allowedTemplateId, has_token, is_admin


@app.route("/api/v3/deployment/<deployment_id>", methods=["GET"])
@has_token
def api_v3_deployment(payload, deployment_id):

    try:
        deployment = deployments.Get(payload["user_id"], deployment_id)
        return json.dumps(deployment), 200, {"Content-Type": "application/json"}
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DeploymentGet general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/deployments", methods=["GET"])
@has_token
def api_v3_deployments(payload):

    try:
        deployments_list = deployments.List(payload["user_id"])
        return json.dumps(deployments_list), 200, {"Content-Type": "application/json"}
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DeploymentsList general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
