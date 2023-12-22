#
#   Copyright © 2023 Naomi Hidalgo
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

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

from .api_users import ApiUsers
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

users = ApiUsers()


### PASSWORD POLICY


def add_password_policy(data):
    if not check_duplicate_policy(data["category"], data["role"], data["subtype"]):
        raise Error(
            "conflict",
            data["type"] + " policy for this category and role already exists",
        )

    with app.app_context():
        r.table("authentication").insert(data).run(db.conn)


def get_password_policies():
    with app.app_context():
        return list(
            r.table("authentication")
            .get_all(["local", "password"], index="type-subtype")
            .merge(
                lambda policy: {
                    "category_name": r.branch(
                        policy["category"].default(None).ne(None),
                        r.table("categories")
                        .get(policy["category"])
                        .default({"name": "all"})["name"],
                        "all",
                    )
                }
            )
            .run(db.conn)
        )


def get_password_policy(policy_id):
    with app.app_context():
        return r.table("authentication").get(policy_id).run(db.conn)


def edit_password_policy(policy_id, data):
    with app.app_context():
        r.table("authentication").get(policy_id).update(data).run(db.conn)


def delete_password_policy(policy_id):
    policy = get_password_policy(policy_id)
    if policy["role"] == "all" and policy["category"] == "all":
        raise Error("forbidden", "Can not delete default permissions")

    with app.app_context():
        r.table("authentication").get(policy_id).delete().run(db.conn)


def check_duplicate_policy(category, role, subtype):
    with app.app_context():
        return (
            len(
                list(
                    r.table("authentication")
                    .get_all([category, role, subtype], index="category-role-subtype")
                    .run(db.conn)
                )
            )
            <= 0
        )


###


def get_providers():
    providers = {}
    providers["local"] = not (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_LOCAL_ENABLED") == "false"
    )
    providers["google"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_GOOGLE_ENABLED") == "true"
    )
    providers["saml"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_SAML_ENABLED") == "true"
    )
    providers["ldap"] = (
        os.environ.get("AUTHENTICATION_AUTHENTICATION_LDAP_ENABLED") == "true"
    )
    return providers
