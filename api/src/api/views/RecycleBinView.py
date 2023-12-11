import json
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.recycle_bin import *
from .decorators import has_token, is_admin_or_manager, ownsCategoryId, ownsRecycleBinId


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
@has_token
def api_v3_admin_recycle_bin_item_count(payload, kind=None):
    if kind == "user":
        recycle_bins = RecycleBin.get_item_count(payload["user_id"])
    elif payload["role_id"] in ["manager", "admin"]:
        recycle_bins = RecycleBin.get_item_count(
            None,
            payload["category_id"] if payload["role_id"] == "manager" else None,
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
