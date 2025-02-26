#
#   Copyright © 2024 Naomi Hidalgo Piñar
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import json
from datetime import datetime

import pytz
from api.libv2.helpers import gen_payload_from_user
from api.libv2.notifications.notifications import (
    get_user_trigger_notifications_displays,
)
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_admin_notifications import (
    add_notification,
    add_notification_template,
    delete_notification,
    delete_notification_template,
    get_all_notifications,
    get_notification,
    get_notification_event_template,
    get_notification_template,
    get_notification_templates,
    get_status_bar_notification_by_provider,
    update_notification,
    update_notification_template,
)
from ..libv2.api_authentication import get_provider_config
from ..libv2.api_users import ApiUsers
from ..libv2.helpers import gen_payload_from_user
from ..libv2.notifications.notifications import get_user_trigger_notifications_displays
from ..libv2.notifications.notifications_action import get_all_notification_actions
from ..libv2.notifications.notifications_data import (
    delete_all_notification_data,
    delete_notifications_data,
    delete_users_notifications_data,
    get_notification_statuses,
    get_notifications_data_by_status,
    get_notifications_grouped_by_status,
)
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin

users = ApiUsers()


### NOTIFICATIONS TEMPLATES ###


@app.route("/api/v3/admin/notifications/template/", methods=["POST"])
@is_admin
def api_v3_admin_add_notification_template(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    for tag in ["<script>", "<iframe>", "javascript:"]:
        if tag in data["body"] or tag in data["footer"]:
            raise Error("bad_request", "Invalid expression in body or footer")

    data["lang"] = {
        data["language"]: {
            "title": data["title"],
            "body": data["body"],
            "footer": data["footer"],
        }
    }

    data = _validate_item("notification_templates", data)
    return (
        json.dumps(add_notification_template(data)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/templates", methods=["GET"])
@is_admin
def api_v3_admin_notification_templates(payload):
    return (
        json.dumps(get_notification_templates()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/templates/custom", methods=["GET"])
@is_admin
def api_v3_admin_notification_templates_custom(payload):
    return (
        json.dumps(get_notification_templates("custom")),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/templates/system", methods=["GET"])
@is_admin
def api_v3_admin_notification_templates_system(payload):
    return (
        json.dumps(get_notification_templates("system")),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/template/<template_id>", methods=["GET"])
@is_admin
def api_v3_admin_notification_template(payload, template_id):
    return (
        json.dumps(get_notification_template(template_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/template/<template_id>", methods=["PUT"])
@is_admin
def api_v3_admin_update_notification_template(payload, template_id):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    for tag in ["<script>", "<iframe>", "javascript:"]:
        if tag in data["body"] or tag in data["footer"]:
            raise Error("bad_request", "Invalid expression in body or footer")

    data["lang"] = {
        data["language"]: {
            "title": data["title"],
            "body": data["body"],
            "footer": data["footer"],
        }
    }
    data = _validate_item("notification_template_update", data)
    return (
        json.dumps(update_notification_template(template_id, data)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/template", methods=["PUT"])
@is_admin
def api_v3_admin_get_notification_template(payload):
    data = request.get_json()
    texts = get_notification_event_template(
        data["event"], data["user_id"], data["data"]
    )
    return (
        json.dumps(texts),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/template/<template_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_notification_templates(payload, template_id):
    return (
        json.dumps(delete_notification_template(template_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/notifications/status_bar", methods=["GET"])
@has_token
def api_v3_get_status_bar_notifications(payload):
    lang = users.get_lang(payload["user_id"])
    notification = get_status_bar_notification_by_provider(payload["provider"])
    provider_config = get_provider_config(payload["provider"])

    if notification["enabled"] and (
        provider_config["migration"]["export"] or provider_config["migration"]["import"]
    ):
        notification_tmpl = get_notification_template(notification.get("template"))
        if notification_tmpl["lang"].get(lang):
            notification_text = notification_tmpl["lang"][lang]
        else:
            notification_text = notification_tmpl["lang"][notification_tmpl["default"]]
        return (
            json.dumps(
                {
                    "text": notification_text["body"],
                    "level": notification["level"],
                    "migration_config": {
                        "import": provider_config["migration"]["import"],
                        "export": provider_config["migration"]["export"],
                    },
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )
    else:
        return (
            json.dumps(None),
            200,
            {"Content-Type": "application/json"},
        )


@app.route(
    "/api/v3/admin/notifications/user/displays/<user_id>/<trigger>", methods=["GET"]
)
@is_admin
def api_v3_admin_get_user_notifications_displays(payload, user_id, trigger):
    user_payload = gen_payload_from_user(user_id)
    return (
        json.dumps(
            {"displays": get_user_trigger_notifications_displays(user_payload, trigger)}
        ),
        200,
        {"Content-Type": "application/json"},
    )


### NOTIFICATIONS MANAGEMENT ###


@app.route("/api/v3/admin/notifications", methods=["GET"])
@is_admin
def api_v3_user_all_notifications(payload):
    """
    Retrieve all notifications for the user.

    :return: A list of all the user's notifications.
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(get_all_notifications(), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notification", methods=["POST"])
@is_admin
def api_v3_admin_add_notification(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    if data.get("ignore_after"):
        data["ignore_after"] = datetime.strptime(
            data.get("ignore_after"), "%Y-%m-%dT%H:%M"
        ).astimezone(pytz.UTC)

    data = _validate_item("notification", data)
    add_notification(data)

    return (
        json.dumps({"id": data["id"]}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notification/actions/all", methods=["GET"])
@is_admin
def api_v3_user_all_notification_actions(payload):
    """
    Retrieve all notification actions.

    :return: A list of all the notification actions.
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(get_all_notification_actions(), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notification/<notification_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_notification(payload, notification_id):
    """
    Delete a notification by its ID.

    :param notification_id: The ID of the notification to delete.
    :return: A success message.
    :rtype: Set with Flask response values and data in JSON
    """
    delete_logs = request.get_json("delete_logs")["delete_logs"]
    delete_notification(notification_id, delete_logs=delete_logs)
    return (
        json.dumps({"delete_logs": delete_logs}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notification/<notification_id>", methods=["GET"])
@is_admin
def api_v3_admin_get_notification(payload, notification_id):
    """
    Retrieve a notification by its ID.

    :param notification_id: The ID of the notification to retrieve.
    :return: The notification.
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(get_notification(notification_id), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notification/<notification_id>", methods=["PUT"])
@is_admin
def api_v3_admin_update_notification(payload, notification_id):
    """
    Update a notification by its ID.

    :param notification_id: The ID of the notification to update.
    :return: The updated notification.
    :rtype: Set with Flask response values and data in JSON
    """
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")
    if data.get("ignore_after"):
        data["ignore_after"] = datetime.strptime(
            data.get("ignore_after"), "%Y-%m-%dT%H:%M"
        ).astimezone(pytz.UTC)

    data = _validate_item("notification_update", data)
    update_notification(notification_id, data)

    return (
        json.dumps({"id": notification_id}),
        200,
        {"Content-Type": "application/json"},
    )


### NOTIFICATIONS DATA ###


@app.route("/api/v3/admin/notifications/data/<status>/<user_id>", methods=["GET"])
@is_admin
def api_v3_admin_get_notifications_data_by_status(payload, status, user_id):
    return (
        json.dumps(get_notifications_data_by_status(status, user_id), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/statuses", methods=["GET"])
@is_admin
def api_v3_admin_get_notification_statuses(payload):
    statuses = get_notification_statuses()
    return (
        json.dumps(statuses),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/data/user/<status>", methods=["GET"])
@is_admin
def api_v3_admin_get_notifications_data_by_status(payload, status):
    return (
        json.dumps(get_notifications_grouped_by_status(status), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/data/<user_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_notifications_data_by_user(payload, user_id):
    delete_users_notifications_data([user_id])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/notifications/data/<notification_data_id>", methods=["DELETE"]
)
@is_admin
def api_v3_admin_delete_notification_data(payload, notification_data_id):
    delete_notifications_data(notification_data_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/notifications/data", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_all_notification_data(payload):
    delete_all_notification_data()
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
