#!flask/bin/python
# coding=utf-8
import json

from api.libv2 import api_analytics
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from .decorators import is_admin_or_manager


@app.route("/api/v3/analytics/storage", methods=["POST"])
@is_admin_or_manager
def storage_resource(payload):
    params = request.get_json(force=True)
    categories = (
        [payload["category_id"]]
        if payload["role_id"] == "manager"
        else params.get("categories")
    )

    storage = api_analytics.storage_usage(categories)
    return json.dumps(storage), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/resources/count", methods=["POST"])
@is_admin_or_manager
def count_resource(payload):
    params = request.get_json(force=True)
    categories = (
        [payload["category_id"]]
        if payload["role_id"] == "manager"
        else params.get("categories")
    )

    count = api_analytics.resource_count(categories)
    return json.dumps(count), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/suggested_removals", methods=["POST"])
@is_admin_or_manager
def suggested_removals(payload):
    params = request.get_json(force=True)
    if not params.get("months_without_use"):
        raise Error(
            "bad_request", "Missing months_without_use parameter, it's required"
        )
    categories = (
        [payload["category_id"]]
        if payload["role_id"] == "manager"
        else params.get("categories")
    )
    suggested_removals = api_analytics.suggested_removals(
        categories, months_without_use=params["months_without_use"]
    )
    return json.dumps(suggested_removals), 200, {"Content-Type": "application/json"}
