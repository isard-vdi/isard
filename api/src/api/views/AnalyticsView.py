#!flask/bin/python
# coding=utf-8
import json

from api.libv2 import api_analytics
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.validators import _validate_item
from .decorators import is_admin, is_admin_or_manager


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


## USAGE ##


@app.route("/api/v3/analytics/graph", methods=["GET"])
@is_admin_or_manager
def get_analytics_graphs_conf(payload):
    conf = api_analytics.get_usage_graphs_conf()
    return json.dumps(conf), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/graph/<conf_id>", methods=["GET"])
@is_admin
def get_analytics_graph_conf(payload, conf_id):
    conf = api_analytics.get_usage_graph_conf(conf_id)
    return json.dumps(conf), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/graph", methods=["POST"])
@is_admin
def add_analytics_graph_conf(payload):
    data = request.get_json(force=True)

    data = _validate_item("analytics_graph", data)
    api_analytics.add_usage_graph_conf(data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/graph/<conf_id>", methods=["PUT"])
@is_admin
def update_analytics_graph_conf(payload, conf_id):
    data = request.get_json(force=True)

    data = _validate_item("analytics_graph_update", data)
    api_analytics.update_usage_graph_conf(conf_id, data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/graph/<conf_id>", methods=["DELETE"])
@is_admin
def delete_analytics_graph_conf(payload, conf_id):
    api_analytics.delete_usage_graph_conf(conf_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/analytics/desktops/less_used", methods=["POST"])
@is_admin
def desktops_less_usage(payload):
    params = request.get_json(force=True)
    days_before = params.get("days_before", 30)
    limit = params.get("limit", 10)
    not_in_directory_path = params.get("not_in_directory_path")
    status = params.get("status", False)
    return (
        json.dumps(
            api_analytics.get_desktops_less_used(
                days_before, limit, not_in_directory_path, status
            ),
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/analytics/desktops/recently_used", methods=["POST"])
@is_admin
def desktops_most_usage(payload):
    params = request.get_json(force=True)
    days_before = params.get("days_before", 30)
    limit = params.get("limit", 10)
    not_in_directory_path = params.get("not_in_directory_path")
    status = params.get("status", False)
    return (
        json.dumps(
            api_analytics.get_desktops_recently_used(
                days_before, limit, not_in_directory_path, status
            ),
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/analytics/desktops/most_used", methods=["POST"])
@is_admin
def desktops_most_used(payload):
    params = request.get_json(force=True)
    days_before = params.get("days_before", 30)
    limit = params.get("limit", 10)
    not_in_directory_path = params.get("not_in_directory_path")
    status = params.get("status", False)
    return (
        json.dumps(
            api_analytics.get_desktops_most_used(
                days_before, limit, not_in_directory_path, status
            ),
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )
