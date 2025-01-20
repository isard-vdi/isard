# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

import gevent
from cachetools import TTLCache, cached
from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app, socketio

from ..libv2.api_admin import (
    ApiAdmin,
    admin_table_delete_list,
    admin_table_get,
    admin_table_update,
)
from ..libv2.api_desktop_events import templates_delete
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent, domain_template_tree
from ..libv2.api_domains import ApiDomains
from ..libv2.api_storage import get_domains_delete_pending
from ..libv2.datatables import LogsDesktopsQuery, LogsUsersQuery
from .decorators import is_admin, is_admin_or_manager, ownsDomainId

admins = ApiAdmin()
desktops_persistent = ApiDesktopsPersistent()
domains = ApiDomains()


@app.route("/api/v3/admin/domains", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_domains(payload):
    params = request.get_json(force=True)
    domains = []
    if params.get("kind") == "desktop":
        categories = (
            json.loads(params.get("categories")) if params.get("categories") else None
        )
        if payload["role_id"] == "manager":
            categories = [payload["category_id"]]
        domains = admins.ListDesktops(
            categories,
        )
    else:
        domains = admins.ListTemplates()
        if payload["role_id"] == "manager":
            domains = [d for d in domains if d["category"] == payload["category_id"]]
    return (
        json.dumps(domains),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/<domain_id>/details", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_details_data(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.DesktopDetailsData(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/<domain_id>/viewer_data", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_deployment_viewer_data(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.DesktopViewerData(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/deployment/<deployment_id>/viewer_data", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domain_viewer_data(payload, deployment_id):
    ownsDomainId(payload, deployment_id)
    return (
        json.dumps(admins.DeploymentViewerData(deployment_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains_status/<status>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domains_status(payload, status):
    if status == "delete_pending":
        domains = (
            get_domains_delete_pending()
            if payload.get("role_id", "") == "admin"
            else get_domains_delete_pending(payload["category_id"])
        )
    elif payload.get("role_id", "") == "admin":
        domains = admins.domains_status_minimal(status)
    return (
        json.dumps(domains),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/storage/<domain_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktop_storage(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.get_domain_storage(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains/xml/<domain_id>", methods=["POST", "GET"])
@is_admin
def api_v3_admin_domains_xml(payload, domain_id):
    if request.method == "POST":
        data = request.get_json(force=True)
        data["status"] = "Updating"
        data["id"] = domain_id
        admin_table_update("domains", data)
    return (
        json.dumps(admin_table_get("domains", domain_id, pluck="xml")["xml"]),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/desktops/tree_list/<id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktops_tree_list(payload, id):
    user_id = payload["user_id"]
    return (
        json.dumps(admins.get_template_tree_list(id, user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/template_tree/<desktop_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktop_template_tree(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    return (
        json.dumps(domain_template_tree(desktop_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/multiple_actions", methods=["POST"])
@is_admin_or_manager
def admin_multiple_actions_domains(payload):
    dict = request.get_json(force=True)
    for d_id in dict.get("ids"):
        ownsDomainId(payload, d_id)
    admins.multiple_actions(dict["action"], dict.get("ids"), payload["user_id"])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/templates/delete/<template_id>", methods=["DELETE"])
@is_admin_or_manager
def api_v3_admin_templates_delete(payload, template_id):
    templates_delete(template_id, payload["user_id"])
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@cached(TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/domains/<field>/<kind>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domains_field(payload, field, kind):
    return json.dumps(admins.get_domains_field(field, kind, payload))


# Render domain Hardware at domain details' Hardware table
@app.route("/api/v3/domain/hardware/<domain_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_domain_hardware(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(domains.get_domain_details_hardware(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/<current_status>/<target_status>", methods=["PUT"])
@is_admin
def api_v3_desktops_status(payload, current_status, target_status):
    if not (target_status in ["Shutting-down", "Stopping", "StartingPaused", "Failed"]):
        raise Error("bad_request", "Invalid target status")
    desktops_persistent.change_status(current_status, target_status)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@cached(TTLCache(maxsize=10, ttl=60))
@app.route("/api/v3/admin/logs_desktops", methods=["POST"])
@app.route("/api/v3/admin/logs_desktops/<view>", methods=["POST"])
@is_admin
def api_v3_logs_desktops(payload, view="raw"):
    if view == "raw":
        return (
            json.dumps(
                LogsDesktopsQuery(request.form).data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "desktop_grouping":
        ld = LogsDesktopsQuery(request.form)
        ld.group_by_desktop_id
        return (
            json.dumps(
                ld.data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "category_grouping":
        ld = LogsDesktopsQuery(request.form)
        return (
            json.dumps(
                ld.data_category_unique,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )


@app.route(
    "/api/v3/logs_desktops/config/old_entries/max_time/<max_time>", methods=["PUT"]
)
@is_admin
def api_v3_admin_logs_desktops_config_old_entries_max_time(payload, max_time):
    max_time = 24 if int(max_time) < 24 else int(max_time)
    return (
        json.dumps(admins.set_logs_desktops_old_entries_max_time(max_time)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_desktops/config/old_entries/action/<action>", methods=["PUT"])
@is_admin
def api_v3_admin_logs_desktops_config_old_entries_action(payload, action):
    # if action not in ["archive", "delete"]:
    #     raise Error("bad_request", 'Action must be "archive" or "delete"')
    if action not in ["delete", "none"]:
        raise Error("bad_request", 'Action must be "delete" or "none"')
    return (
        json.dumps(admins.set_logs_desktops_old_entries_action(action)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_desktops/config/old_entries", methods=["GET"])
@is_admin
def api_v3_admin_logs_desktops_config_old_entries(payload):
    return (
        json.dumps(admins.get_logs_desktops_old_entries_config()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_desktops/old_entries/delete", methods=["PUT"])
@is_admin
def logs_desktops_old_entries_delete(payload):
    old_logs = admins.get_older_than_old_entry_max_time("logs_desktops")

    def delete_old_logs_process():
        try:
            admin_table_delete_list("logs_desktops", old_logs)
            socketio.emit(
                "logs_desktops_action",
                json.dumps({"action": "delete_all", "status": "completed"}),
                namespace="/administrators",
                room="admins",
            )
        except Error as e:
            app.logger.error(traceback.format_exc())
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]

            socketio.emit(
                "logs_desktops_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": error_message,
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
        except Exception as e:
            app.logger.error(traceback.format_exc())
            socketio.emit(
                "logs_desktops_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": "Something went wrong",
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )

    gevent.spawn(delete_old_logs_process)

    return (
        json.dumps(len(old_logs)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_desktops/old_entries/delete/all", methods=["DELETE"])
@is_admin
def logs_desktops_old_entries_delete_all(payload):
    old_logs = admins.get_older_than_old_entry_max_time("logs_desktops", 0)

    def delete_old_logs_process():
        try:
            admin_table_delete_list("logs_desktops", old_logs)
            socketio.emit(
                "logs_desktops_action",
                json.dumps({"action": "delete_all", "status": "completed"}),
                namespace="/administrators",
                room="admins",
            )
        except Error as e:
            app.logger.error(traceback.format_exc())
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]

            socketio.emit(
                "logs_desktops_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": error_message,
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
        except Exception as e:
            app.logger.error(traceback.format_exc())
            socketio.emit(
                "logs_desktops_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": "Something went wrong",
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )

    gevent.spawn(delete_old_logs_process)

    return (
        json.dumps(len(old_logs)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(TTLCache(maxsize=10, ttl=60))
@app.route("/api/v3/admin/logs_users", methods=["POST"])
@app.route("/api/v3/admin/logs_users/<view>", methods=["POST"])
@is_admin
def api_v3_logs_users(payload, view="raw"):
    if view == "raw":
        return (
            json.dumps(
                LogsUsersQuery(request.form).data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "user_grouping":
        ld = LogsUsersQuery(request.form)
        ld.group_by_user_id
        return (
            json.dumps(
                ld.data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "category_grouping":
        ld = LogsUsersQuery(request.form)
        return (
            json.dumps(
                ld.data_category_unique,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_users/config/old_entries/max_time/<max_time>", methods=["PUT"])
@is_admin
def api_v3_admin_logs_users_config_old_entries_max_time(payload, max_time):
    max_time = 24 if int(max_time) < 24 else int(max_time)
    return (
        json.dumps(admins.set_logs_users_old_entries_max_time(max_time)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_users/config/old_entries/action/<action>", methods=["PUT"])
@is_admin
def api_v3_admin_logs_users_config_old_entries_action(payload, action):
    # if action not in ["archive", "delete"]:
    #     raise Error("bad_request", 'Action must be "archive" or "delete"')
    if action not in ["delete", "none"]:
        raise Error("bad_request", 'Action must be "delete" or "none"')
    return (
        json.dumps(admins.set_logs_users_old_entries_action(action)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_users/config/old_entries", methods=["GET"])
@is_admin
def api_v3_admin_logs_users_config_old_entries(payload):
    return (
        json.dumps(admins.get_logs_users_old_entries_config()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_users/old_entries/delete", methods=["PUT"])
@is_admin
def logs_users_old_entries_delete(payload):
    old_logs = admins.get_older_than_old_entry_max_time("logs_users")

    def delete_old_logs_process():
        try:
            admin_table_delete_list("logs_users", old_logs)
            socketio.emit(
                "logs_users_action",
                json.dumps({"action": "delete_all", "status": "completed"}),
                namespace="/administrators",
                room="admins",
            )
        except Error as e:
            app.logger.error(traceback.format_exc())
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]

            socketio.emit(
                "logs_users_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": error_message,
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
        except Exception as e:
            app.logger.error(traceback.format_exc())
            socketio.emit(
                "logs_users_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": "Something went wrong",
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )

    gevent.spawn(delete_old_logs_process)

    return (
        json.dumps(len(old_logs)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/logs_users/old_entries/delete/all", methods=["DELETE"])
@is_admin
def logs_users_old_entries_delete_all(payload):
    old_logs = admins.get_older_than_old_entry_max_time("logs_users", 0)

    def delete_old_logs_process():
        try:
            admin_table_delete_list("logs_users", old_logs)
            socketio.emit(
                "logs_users_action",
                json.dumps({"action": "delete_all", "status": "completed"}),
                namespace="/administrators",
                room="admins",
            )
        except Error as e:
            app.logger.error(traceback.format_exc())
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]

            socketio.emit(
                "logs_users_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": error_message,
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
        except Exception as e:
            app.logger.error(traceback.format_exc())
            socketio.emit(
                "logs_users_action",
                json.dumps(
                    {
                        "action": "delete_all",
                        "msg": "Something went wrong",
                        "status": "failed",
                    }
                ),
                namespace="/administrators",
                room="admins",
            )

    gevent.spawn(delete_old_logs_process)

    return (
        json.dumps(len(old_logs)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/desktops/category/<category>/status/<current_status>/<target_status>",
    methods=["PUT"],
)
@is_admin
def api_v3_desktops_status_category(payload, category, current_status, target_status):
    if not (current_status in ["Stopped", "Failed", "Started"]):
        raise Error("bad_request", "Invalid current status")
    if not (target_status in ["Shutting-down", "Stopping", "StartingPaused"]):
        raise Error("bad_request", "Invalid target status")

    desktops_persistent.change_status_category(category, current_status, target_status)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/domain/<domain_id>/storage_path", methods=["PUT"])
@is_admin
def api_v3_domain_update_storage_path(payload, domain_id):
    # ownsDomainId(payload, domain_id)
    return (
        json.dumps(
            domains.update_domain_path(
                domain_id, request.json["old_path"], request.json["new_path"]
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )
