import json
import traceback
from datetime import datetime, timedelta

import gevent
import pytz
from api.libv2.api_admin_notifications import get_notification_template
from api.libv2.api_desktop_events import desktop_delete
from api.libv2.api_desktops_persistent import get_unused_desktops
from api.libv2.api_notify import notify_admins
from api.libv2.notifications.notifications import get_notifications_by_action_id
from api.libv2.notifications.notifications_action import get_notification_action
from api.libv2.notifications.notifications_data import add_notification_data
from flask import request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest

from api import app, socketio

from ..libv2.recycle_bin import (
    RecycleBin,
    RecycleBinDeleteQueue,
    check_older_than_old_entry_max_time,
    get,
    get_default_delete,
    get_delete_action,
    get_item_count,
    get_old_entries_config,
    get_recicle_delete_time,
    get_recycle_bin_by_period,
    get_status,
    get_unused_desktops_cutoff_time,
    get_user_amount,
    get_user_recycle_bin_ids,
    set_unused_desktops_cutoff_time,
    update_task_status,
)
from .decorators import has_token, is_admin, is_admin_or_manager, ownsRecycleBinId

rb_delete_queue = RecycleBinDeleteQueue()
scheduler_client = ApiRest("isard-scheduler")


@app.route("/api/v3/recycle_bin/<recycle_bin_id>", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_get(payload, recycle_bin_id):
    ownsRecycleBinId(payload, recycle_bin_id)
    return (
        json.dumps(get(recycle_bin_id, all_data=True)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/count", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_count(payload):
    return (
        json.dumps(get_user_amount(payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/item_count", methods=["GET"])
@app.route("/api/v3/recycle_bin/item_count/<kind>", methods=["GET"])
@app.route("/api/v3/recycle_bin/item_count/status/<status>", methods=["GET"])
@has_token
def api_v3_admin_recycle_bin_item_count(payload, kind=None, status=None):
    if kind == "user":
        recycle_bins = get_item_count(payload["user_id"])
    elif payload["role_id"] in ["manager", "admin"]:
        recycle_bins = get_item_count(
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


@app.route("/api/v3/recycle_bin/restore/<recycle_bin_id>", methods=["PUT"])
@has_token
def api_v3_admin_recycle_bin_restore(payload, recycle_bin_id=None):
    recycle_bin_ids = [recycle_bin_id]
    ownsRecycleBinId(payload, recycle_bin_id)

    rb = RecycleBin(id=recycle_bin_id)
    rb._update_agent(payload["user_id"])
    rb.restore()

    return (
        json.dumps({"recycle_bin_ids": recycle_bin_ids}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/restore/", methods=["PUT"])
@has_token
def api_v3_admin_recycle_bin_restore_bulk(payload):
    data = request.get_json(force=True)
    recycle_bin_ids = data.get("recycle_bin_ids")
    for recycle_bin_id in recycle_bin_ids:
        ownsRecycleBinId(payload, recycle_bin_id)

    def process_bulk_restore():
        try:
            for recycle_bin_id in recycle_bin_ids:
                rb = RecycleBin(id=recycle_bin_id)
                rb._update_agent(payload["user_id"])
                rb.restore()
            notify_admins(
                "recyclebin_action",
                {
                    "action": "restore",
                    "count": len(recycle_bin_ids),
                    "errors": [],
                    "status": "completed",
                },
            )
        except Error as e:
            app.logger.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "recyclebin_action",
                {
                    "action": "restore",
                    "count": len(recycle_bin_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            app.logger.error(e.args[0])
            notify_admins(
                "recyclebin_action",
                {
                    "action": "restore",
                    "count": len(recycle_bin_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    gevent.spawn(process_bulk_restore)
    return (
        json.dumps({"recycle_bin_ids": recycle_bin_ids}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/<recycle_bin_id>", methods=["DELETE"])
@has_token
def rcb_delete(payload, recycle_bin_id=None):
    ownsRecycleBinId(payload, recycle_bin_id)
    rb_delete_queue.enqueue(
        {
            "action": "delete",
            "recycle_bin_id": recycle_bin_id,
            "user_id": payload["user_id"],
        }
    )
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/delete", methods=["PUT"])
@has_token
def rcb_delete_bulk(payload):
    data = request.get_json(force=True)
    if data.get("recycle_bin_ids"):
        recycle_bin_ids = data["recycle_bin_ids"]
    else:
        recycle_bin_ids = get_recycle_bin_by_period(
            data.get("max_delete_period"), data.get("category")
        )

    def process_bulk_delete():
        exceptions = []
        try:
            for rb_id in recycle_bin_ids:
                try:
                    ownsRecycleBinId(payload, rb_id)
                    rb_delete_queue.enqueue(
                        {
                            "action": "delete",
                            "recycle_bin_id": rb_id,
                            "user_id": payload["user_id"],
                        }
                    )
                except Error as e:
                    exceptions.append(e.args[1])
            notify_admins(
                "recyclebin_action",
                {
                    "action": "delete",
                    "count": len(recycle_bin_ids),
                    "status": "completed",
                },
            )

        except Error as e:
            app.logger.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                (
                    "recyclebin_action",
                    {
                        "action": "delete",
                        "count": len(recycle_bin_ids),
                        "msg": error_message,
                        "status": "failed",
                    },
                )
            )

        except Exception as e:
            app.logger.error(e)
            notify_admins(
                "recyclebin_action",
                {
                    "action": "delete",
                    "count": len(recycle_bin_ids),
                    "msg": str(e),
                    "status": "failed",
                },
            )

    gevent.spawn(process_bulk_delete)
    return (
        json.dumps({}),
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
    rcbs = get_item_count(status="deleted")
    for rcb in rcbs:
        if check_older_than_old_entry_max_time(rcb["last"]["time"]):
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
    update_task_status(task)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/empty", methods=["DELETE"])
@has_token
def recycle_bin_empty(payload):
    rb_ids = get_user_recycle_bin_ids(payload["user_id"], "recycled")
    for rb_id in rb_ids:
        rb_delete_queue.enqueue(
            {"recycle_bin_id": rb_id, "user_id": payload["user_id"]}
        )
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
        json.dumps(get_old_entries_config()),
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
        json.dumps(get_default_delete()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle_bin/config/delete-action/<action>", methods=["PUT"])
@is_admin
def api_v3_admin_recycle_bin_delete_action_set(payload, action):
    if action not in ["move", "delete"]:
        raise Error("bad_request", 'Action must be "move" or "delete"')
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
        json.dumps(get_delete_action()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle-bin/unused-desktops/cutoff-time", methods=["GET"])
@is_admin
def recycle_bin_cutoff_time(payload):
    """
    Get the cutoff time for unused desktops.

    :param payload: Data from JWT
    :type payload: dict
    :return: Cutoff time
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps({"cutoff_time": get_unused_desktops_cutoff_time()}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle-bin/unused-desktops/cutoff-time", methods=["PUT"])
@is_admin
def recycle_bin_set_cutoff_time(payload):
    """

    Set the cutoff time for unused desktops.

    Configuration specifications in JSON:
    {
        "cutoff_time": "Cutoff time in months"
    }
    :param payload: Data from JWT
    :type payload: dict
    :return: None
    :rtype: Set with Flask response values and data in JSON

    """
    data = request.get_json(force=True)
    cutoff_time = data.get("cutoff_time")
    set_unused_desktops_cutoff_time(cutoff_time)

    return (
        json.dumps({"cutoff_time": cutoff_time}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/recycle-bin/unused-items", methods=["POST"])
@is_admin
def recycle_bin_add_unused_items(payload):
    """
    Send unused items to the recycle bin.

    :param payload: Data from JWT
    :type payload: dict
    :return: Task ID
    :rtype: Set with Flask response values and data in JSON
    """
    # Send unused desktops to recycle bin
    desktops = get_unused_desktops()
    notification = get_notifications_by_action_id("unused_desktops")
    notification_data = []

    if notification and notification[0]["trigger"]:
        notification = notification[0]
        notification_action = get_notification_action(notification["action_id"])
        max_delete_period = get_recicle_delete_time()

    for desktop in desktops:
        desktop_delete(desktop["id"], "isard-scheduler")
        if notification:
            notification_data.append(
                {
                    "item_id": desktop["id"],
                    "item_type": "desktop",
                    "status": "pending",
                    "user_id": desktop["user"],
                    "created_at": datetime.now().astimezone(pytz.UTC),
                    "notified_at": None,
                    "accepted_at": None,
                    "notification_id": notification["id"],
                    "vars": {
                        var: desktop[var] for var in notification_action["kwargs"]
                    },
                    "ignore_after": (
                        datetime.now() + timedelta(hours=int(max_delete_period))
                    ).astimezone(pytz.UTC),
                }
            )

    if notification_data:
        add_notification_data(notification_data)

    # TODO: Send unused deployments to recycle bin

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
