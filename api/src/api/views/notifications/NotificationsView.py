#   Copyright © 2025 Miriam Melina Gamboa Valdez
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

from api.libv2.notifications.notifications import (
    get_user_trigger_notifications,
    get_user_trigger_notifications_displays,
)

from api import app

from ..decorators import has_token


@app.route("/api/v3/notification/user/displays/<trigger>", methods=["GET"])
@has_token
def api_v3_user_notification_displays(payload, trigger):
    """
    Retrieve the users notifications displays for the given trigger.

    :param trigger: str
    :type trigger: str
    :return: A list of the users notifications displays for the given trigger.
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(
            {"displays": get_user_trigger_notifications_displays(payload, trigger)}
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/notification/user/<trigger>/<display>", methods=["GET"])
@has_token
def api_v3_user_notification_trigger(payload, trigger, display):
    """
    Retrieve the users notifications for the given trigger.

    :param trigger: str
    :type trigger: str
    :return: A list of the users notifications for the given trigger.
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(
            {"notifications": get_user_trigger_notifications(payload, trigger, display)}
        ),
        200,
        {"Content-Type": "application/json"},
    )
