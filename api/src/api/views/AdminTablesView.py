# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import (
    admin_table_delete,
    admin_table_get,
    admin_table_insert,
    admin_table_list,
    admin_table_update,
    manager_table_get,
    manager_table_list,
)
from ..libv2.api_admin_notifications import sanitizer
from ..libv2.api_desktops_persistent import (
    unassign_resource_from_desktops_and_deployments,
)
from .decorators import checkDuplicate, is_admin, is_admin_or_manager


@app.route("/api/v3/admin/table/<table>", methods=["GET", "POST"])
@is_admin_or_manager
def api_v3_admin_table(payload, table):
    if request.method == "GET":
        options = request.args
    else:
        options = request.get_json(force=True)
    if options.get("id") and not options.get("index"):
        if payload["role_id"] == "admin":
            result = admin_table_get(
                table, options.get("id"), pluck=options.get("pluck")
            )
        elif payload["role_id"] == "manager":
            result = manager_table_get(
                table,
                payload["category_id"],
                options.get("id"),
                pluck=options.get("pluck"),
            )

    else:
        if payload["role_id"] == "admin":
            result = admin_table_list(
                table,
                options.get("order_by"),
                options.get("pluck"),
                options.get("without"),
                options.get("id"),
                options.get("index"),
            )
        elif payload["role_id"] == "manager":
            result = manager_table_list(
                table,
                payload["category_id"],
                options.get("order_by"),
                options.get("pluck"),
                options.get("without"),
                options.get("id"),
                options.get("index"),
            )
    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


def _validate_desktops_priority_extend(data):
    op = data.get("op", "shutdown")
    op_data = data.get(op, {})
    if not op_data.get("extend_enabled", False):
        return
    extend_time = op_data.get("extend_time", 0)
    notify_intervals = op_data.get("notify_intervals", [])
    if not notify_intervals:
        return
    max_notify_offset = max(
        abs(i["time"]) for i in notify_intervals if i.get("time", 0) != 0
    )
    if extend_time <= max_notify_offset:
        raise Error(
            "bad_request",
            f"Extend time ({extend_time} min) must be greater than the earliest notification offset ({max_notify_offset} min) so all notifications fire again after extending",
            description_code="desktop_extend_time_too_short",
        )


@app.route("/api/v3/admin/table/add/<table>", methods=["POST"])
@is_admin
def api_v3_admin_insert_table(payload, table):
    data = request.get_json()
    if table in [
        "interfaces",
        "graphics",
        "videos",
        "qos_net",
        "qos_disk",
        "remotevpn",
        "bookings_priority",
        "desktops_priority",
    ]:
        checkDuplicate(table, data["name"])
    if table in ("domains", "notification_tmpls", "config"):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = sanitizer.sanitize(value)
    if table == "desktops_priority":
        _validate_desktops_priority_extend(data)
    admin_table_insert(table, data)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@app.route("/api/v3/admin/table/update/<table>", methods=["PUT"])
@is_admin
def api_v3_admin_update_table(payload, table):
    data = request.get_json()
    if table in [
        "interfaces",
        "graphics",
        "videos",
        "qos_net",
        "qos_disk",
        "remotevpn",
        "bookings_priority",
        "desktops_priority",
    ]:
        checkDuplicate(table, data["name"], item_id=data["id"])
    if table in ("domains", "notification_tmpls", "config"):
        for key, value in data.items():
            if isinstance(value, str):
                data[key] = sanitizer.sanitize(value)
    if table == "desktops_priority":
        _validate_desktops_priority_extend(data)
    admin_table_update(table, data)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@app.route("/api/v3/admin/table/<table>/<item_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_table(payload, table, item_id):
    if table in ["interfaces", "reservables_vgpus", "boots", "videos", "qos_disk"]:
        unassign_resource_from_desktops_and_deployments(table, {"id": item_id})
    admin_table_delete(table, item_id)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})
