#
#   Copyright © 2024 Miriam Melina Gamboa Valdez
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

import requests
from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest

authentication_client = ApiRest("isard-authentication")


def generate_migrate_user_token(user_id):
    try:
        user = authentication_client.post("/export-user", {"user_id": user_id})
        return user
    except:
        raise Error(
            "internal_server",
            "Exception when trying to generate migration token",
            traceback.format_exc(),
        )


def import_migrate_user_token(token):
    try:
        user = authentication_client.put("/import-user", {"migration_token": token})
        return user
    except requests.exceptions.HTTPError as e:
        if e.response.status_code in [401, 403, 498]:
            raise Error(
                "forbidden",
                "The migration token is invalid",
                description_code="token_invalid",
            )
        raise Error(
            "internal_server",
            "Exception when trying to import migration token",
            traceback.format_exc(),
        )
    except:
        raise Error(
            "internal_server",
            "Exception when trying to import migration token",
            traceback.format_exc(),
        )
