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

import os
import traceback

from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest

notifier_client = ApiRest("isard-notifier")


def send_verification_email(email, token):
    try:
        data = {
            "email": email,
            "url": "https://"
            + os.environ.get("DOMAIN")
            + "/verify-email?token={token}".format(token=token),
        }
        user = notifier_client.post("/mail/email-verify", data)
        return user
    except:
        raise Error(
            "internal_server",
            "Exception when sending verification email to user",
            traceback.format_exc(),
        )
