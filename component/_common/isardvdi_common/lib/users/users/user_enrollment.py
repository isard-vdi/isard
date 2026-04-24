#
#   Copyright © 2025 Pau Abril Iranzo
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


import random
import string
import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r

from ....helpers.error_factory import Error


class UserEnrollment(RethinkSharedConnection):

    _rdb_table = "users"

    @classmethod
    def enrollment_action(cls, data):
        """_From api/libv2/api_users.py ApiUsers.EnrollmentAction()_"""
        if data["action"] == "disable":
            with cls._rdb_context():
                r.table("groups").get(data["id"]).update(
                    {"enrollment": {data["role"]: False}}
                ).run(cls._rdb_connection)
            return True
        if data["action"] == "reset":
            chars = string.digits + string.ascii_lowercase
        code = False
        while code == False:
            code = "".join([random.choice(chars) for i in range(6)])
            if cls.enrollment_code_check(code) == False:
                with cls._rdb_context():
                    r.table("groups").get(data["id"]).update(
                        {"enrollment": {data["role"]: code}}
                    ).run(cls._rdb_connection)
                return code
        raise Error(
            "internal_server",
            "Unable to generate enrollment code",
            traceback.format_exc(),
            description_code="unable_to_gen_enrollment_code",
        )

    @classmethod
    def enrollment_code_check(cls, code):
        """_From api/libv2/api_users.py ApiUsers.enrollment_code_check()_"""
        with cls._rdb_context():
            found = list(
                r.table("groups")
                .filter({"enrollment": {"manager": code}})
                .run(cls._rdb_connection)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "manager",
                "category": category,
                "group": found[0]["id"],
            }
        with cls._rdb_context():
            found = list(
                r.table("groups")
                .filter({"enrollment": {"advanced": code}})
                .run(cls._rdb_connection)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "advanced",
                "category": category,
                "group": found[0]["id"],
            }
        with cls._rdb_context():
            found = list(
                r.table("groups")
                .filter({"enrollment": {"user": code}})
                .run(cls._rdb_connection)
            )
        if len(found) > 0:
            category = found[0]["parent_category"]  # found[0]['id'].split('_')[0]
            return {
                "code": code,
                "role": "user",
                "category": category,
                "group": found[0]["id"],
            }
        return False
