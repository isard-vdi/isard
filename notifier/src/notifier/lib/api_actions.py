#
#   Copyright © 2023 Miriam Melina Gamboa Valdez
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

import traceback

from isardvdi_common.connections.api_rest import ApiRest
from isardvdi_common.helpers.api_exceptions_flask import Error

api_client = ApiRest("isard-apiv4")


def get_user(user_id):
    try:
        # apiv4 has /item/user (self-only) and /admin/user/<id>. The
        # notifier runs with a service JWT carrying the admin role, so
        # /admin/user/<id> is the right endpoint for fetching any user.
        user = api_client.get(
            "/admin/user/" + user_id,
        )
        return user
    except:
        raise Error(
            "internal_server",
            "Exception when retrieving user data from user" + user_id,
            traceback.format_exc(),
        )


def get_user_by_email_and_category(email, category):
    try:
        user_id = api_client.get(
            "/admin/user/email-category/" + email + "/" + category,
        )["id"]
        return user_id
    except:
        raise Error(
            "internal_server",
            "Exception when retrieving user data from user",
            traceback.format_exc(),
        )


def get_notification_message(data):
    try:
        # v3 used PUT /admin/notifications/template to render a template;
        # v4 split CRUD (POST/DELETE /admin/notifications/template) from
        # the render operation and moved the latter to
        # PUT /admin/notifications/template/preview.
        message = api_client.put("/admin/notifications/template/preview", data)
        return message
    except:
        raise Error(
            "internal_server",
            "Exception when retrieving notification template",
            traceback.format_exc(),
        )


def is_smtp_enabled():
    return api_client.get("/smtp/enabled")
