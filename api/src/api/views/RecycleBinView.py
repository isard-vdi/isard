import json
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.recycle_bin import *
from .decorators import (
    has_token,
    is_admin,
    is_admin_or_manager,
    ownsCategoryId,
    ownsRecycleBinId,
)


@app.route("/api/v3/recycle_bin/<recycle_bin_id>", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_get(payload, recycle_bin_id):
    ownsRecycleBinId(payload, recycle_bin_id)
    return (
        json.dumps(RecycleBin.get(recycle_bin_id, all_data=True)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/count", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_count(payload):
    return (
        json.dumps(RecycleBin.get_user_amount(payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/item_count", methods=["GET"])
@app.route("/api/v3/recycle_bin/item_count/<kind>", methods=["GET"])
@app.route("/api/v3/recycle_bin/item_count/status/<status>", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_item_count(payload, kind=None, status=None):
    if kind == "user":
        recycle_bins = RecycleBin.get_item_count(payload["user_id"])
    elif payload["role_id"] in ["manager", "admin"]:
        recycle_bins = RecycleBin.get_item_count(
            None,
            payload["category_id"] if payload["role_id"] == "manager" else None,
            status,
        )
    else:
        raise Error(
            "forbidden",
            "Only administrators and managers can access to recycle bin data",
            traceback.format_exc(),
        )

    return (
        json.dumps(recycle_bins),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/restore/<recycle_bin_id>", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_restore(payload, recycle_bin_id):
    ownsRecycleBinId(payload, recycle_bin_id)
    rb = RecycleBin(id=recycle_bin_id)
    rb._update_agent(payload["user_id"])
    rb.restore()

    return (
        json.dumps({"recycle_bin_id": recycle_bin_id}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/delete/", methods=["PUT"])
@app.route("/api/v3/recycle_bin/delete/<recycle_bin_id>", methods=["DELETE"])
@has_token
def storage_delete_bulk(payload, recycle_bin_id=None):
    if request.method == "PUT":
        data = request.get_json(force=True)
        recycle_bin_ids = RecycleBin.get_recycle_bin_by_period(
            data.get("max_delete_period"), data.get("category")
        )
    else:
        recycle_bin_ids = [recycle_bin_id]

    tasks = {}
    for recycle_bin_id in recycle_bin_ids:
        ownsRecycleBinId(payload, recycle_bin_id)
        try:
            rb = RecycleBin(recycle_bin_id)
            tasks = rb.delete_storage(payload["user_id"])
        except:
            continue
    return (
        json.dumps(tasks),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/old_entries/archive", methods=["PUT"])
@is_admin
def recycle_bin_old_entries_archive(payload):
    return (
        json.dumps({}),
        501,
        {"Content-Type": "application/json"},
    )
    # rcb_list = []
    # rcbs = RecycleBin.get_all()
    # for rcb in rcbs:
    #     if rcb[
    #         "status"
    #     ] == "deleted" and RecycleBin.check_older_than_old_entry_max_time(
    #         rcb["logs"][-1]["time"]
    #     ):
    #         rcb_list.append(rcb)

    # RecycleBin.archive_old_entries(rcb_list)
    # return (
    #     json.dumps({}),
    #     200,
    #     {"Content-Type": "application/json"},
    # )


@app.route("/api/v3/recycle_bin/old_entries/delete", methods=["PUT"])
@is_admin
def recycle_bin_old_entries_delete(payload):
    rcb_list = []
    rcbs = RecycleBin.get_item_count(status="deleted")
    for rcb in rcbs:
        if RecycleBin.check_older_than_old_entry_max_time(rcb["last"]["time"]):
            rcb_list.append(rcb["id"])
    RecycleBin.delete_old_entries(rcb_list)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/update_task", methods=["PUT"])
@is_admin_or_manager
def recycle_bin_update_task(payload):
    task = request.get_json(force=True)
    RecycleBin.update_task_status(task)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/empty", methods=["DELETE"])
@has_token
def recycle_bin_empty(payload):
    rb_ids = RecycleBin.get_user_recycle_bin_ids(payload["user_id"], "recycled")
    for rb_id in rb_ids:
        try:
            rb = RecycleBin(rb_id)
            rb.delete_storage(payload["user_id"])
        except:
            continue
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/status", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_recycle_bin_status(payload):
    return (
        json.dumps(
            get_status(
                payload["category_id"] if payload["role_id"] == "manager" else None
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/recycle_bin/config/old_entries/max_time/<max_time>", methods=["PUT"]
)
@is_admin
def api_v3_admin_recycle_bin_config_old_entries_max_time(payload, max_time):
    return (
        json.dumps(RecycleBin.set_old_entries_max_time(max_time)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/old_entries/action/<action>", methods=["PUT"])
@is_admin
def api_v3_admin_recycle_bin_config_old_entries_action(payload, action):
    # if action not in ["archive", "delete"]:
    #     raise Error("bad_request", 'Action must be "archive" or "delete"')
    if action not in ["delete", "none"]:
        raise Error("bad_request", 'Action must be "delete" or "none"')
    return (
        json.dumps(RecycleBin.set_old_entries_action(action)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/old_entries", methods=["GET"])
@is_admin
def api_v3_admin_recycle_bin_config_old_entries(payload):
    return (
        json.dumps(RecycleBin.get_old_entries_config()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/default-delete", methods=["PUT"])
@is_admin
def api_v3_admin_recycle_bin_default_delete_set(payload):
    """
    Ednpoint to set whether by default an item is sent to the recycle bin or deleted permanently.

    Configuration specifications in JSON:
    {
        "set_default": "whether by default an item is sent to the recycle bin or deleted permanently."
    }
    :param payload: Data from JWT
    :type payload: dict
    :return: None
    :rtype: Set with Flask response values and data in JSON
    """
    if not request.is_json:
        raise Error(
            description="No JSON in body request with configuration specifications",
        )
    request_json = request.get_json()
    rb_default = request_json.get("rb_default")
    RecycleBin.set_default_delete(rb_default)
    return (
        {},
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/default-delete", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_default_delete(payload):
    return (
        json.dumps(RecycleBin.get_default_delete()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/delete-action/<action>", methods=["PUT"])
@is_admin
def api_v3_admin_recycle_bin_delete_action_set(payload, action):
    if action not in ["archive", "delete"]:
        raise Error("bad_request", 'Action must be "archive" or "delete"')
    RecycleBin.set_delete_action(action)
    return (
        {},
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/delete-action", methods=["GET"])
@is_admin
def api_v3_admin_recycle_bin_delete_action(payload):
    return (
        json.dumps(RecycleBin.get_delete_action()),
        200,
        {"Content-Type": "application/json"},
    )
