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

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_admin_notifications import (
    add_notification_template,
    delete_notification_template,
    get_notification_event_template,
    get_notification_template,
    get_notification_templates,
    get_status_bar_notification_by_provider,
    update_notification_template,
)
from ..libv2.api_authentication import get_provider_config
from ..libv2.api_users import ApiUsers
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin

users = ApiUsers()


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
