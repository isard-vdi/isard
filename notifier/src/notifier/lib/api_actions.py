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

from isardvdi_apiv4_client.api.role_admin import (
    admin_get_user_by_email_category,
    admin_preview_notification_template,
    admin_smtp_enabled_get,
)
from isardvdi_apiv4_client.api.role_manager import admin_get_user
from isardvdi_apiv4_client.models import TemplatePreviewRequest
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from isardvdi_common.helpers.api_exceptions_flask import Error


def get_user(user_id):
    try:
        with build_client("isard-notifier") as client:
            resp = admin_get_user.sync_detailed(client=client, user_id=user_id)
            raise_for_status(resp)
            return resp.parsed
    except (ApiV4Error, Exception):
        raise Error(
            "internal_server",
            "Exception when retrieving user data from user" + user_id,
            traceback.format_exc(),
        )


def get_user_by_email_and_category(email, category):
    try:
        with build_client("isard-notifier") as client:
            resp = admin_get_user_by_email_category.sync_detailed(
                client=client, email=email, category=category
            )
            raise_for_status(resp)
            return resp.parsed.id
    except (ApiV4Error, Exception):
        raise Error(
            "internal_server",
            "Exception when retrieving user data from user",
            traceback.format_exc(),
        )


def get_notification_message(data):
    try:
        body = TemplatePreviewRequest(event=data["event"])
        for k, v in data.items():
            if k != "event":
                body[k] = v
        with build_client("isard-notifier") as client:
            resp = admin_preview_notification_template.sync_detailed(
                client=client, body=body
            )
            raise_for_status(resp)
            return resp.parsed.to_dict()
    except (ApiV4Error, Exception):
        raise Error(
            "internal_server",
            "Exception when retrieving notification template",
            traceback.format_exc(),
        )


def is_smtp_enabled():
    with build_client("isard-notifier") as client:
        resp = admin_smtp_enabled_get.sync_detailed(client=client)
        raise_for_status(resp)
        return resp.parsed
