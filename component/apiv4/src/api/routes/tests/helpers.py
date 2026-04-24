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


import gc
import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from cachetools import Cache
from rethinkdb import r


class MockJWT:
    def __init__(
        self,
        provider="local",
        user_id="local-default-admin-admin",
        role_id="admin",
        category_id="default",
        group_id="default-default",
        name="Administrator",
        expiration=60,
        token_type="",
    ):
        self.provider = provider
        self.user_id = user_id
        self.role_id = role_id
        self.category_id = category_id
        self.group_id = group_id
        self.name = name
        self.expiration = expiration
        self.type = token_type

    def __str__(self):
        return self.token

    def __dict__(self):
        return self.payload

    @property
    def payload(
        self,
    ) -> dict[
        Literal[
            "provider", "user_id", "role_id", "category_id", "group_id", "name", "type"
        ],
        str,
    ]:
        return {
            "provider": self.provider,
            "user_id": self.user_id,
            "role_id": self.role_id,
            "category_id": self.category_id,
            "group_id": self.group_id,
            "name": self.name,
            "type": self.type,
        }

    @property
    def token(self):
        return jwt.encode(
            {
                "iss": "isard-authentication",
                "sub": self.user_id,
                "exp": datetime.now(timezone.utc) + timedelta(seconds=self.expiration),
                "kid": "isardvdi",
                "session_id": "isardvdi-service",
                "data": self.payload,
            },
            os.environ["API_ISARDVDI_SECRET"],
            algorithm="HS256",
        )

    @property
    def header(self):
        return {
            "Authorization": f"Bearer {self.token}",
        }


def create_indexes(
    db_tables_data: dict[str, list[dict]],
    conn: "MockThinkConn",  # noqa: F821
):
    """
    Create indexes for the provided tables in the mock database connection.
    """
    # TODO: Add all secondary indexes

    for table in db_tables_data:
        match table:
            case "domains":
                r.table("domains").index_create("kind").run(conn)
                r.table("domains").index_create("tag").run(conn)
                r.table("domains").index_create(
                    "kind_user", [r.row["kind"], r.row["user"]]
                ).run(conn)
                r.table("domains").index_wait().run(conn)

            case "users":
                r.table("users").index_create("active").run(conn)
                r.table("users").index_create("category").run(conn)
                r.table("users").index_create("group").run(conn)
                r.table("users").index_create("name").run(conn)
                r.table("users").index_create("provider").run(conn)
                r.table("users").index_create("role").run(conn)
                r.table("users").index_create("uid").run(conn)

                r.table("users").index_wait().run(conn)

            case "groups":
                r.table("groups").index_create("name").run(conn)
                r.table("groups").index_create("parent_category").run(conn)

                r.table("groups").index_wait().run(conn)

            case "targets":
                r.table("targets").index_create("user_id").run(conn)

                r.table("targets").index_wait().run(conn)

            case "media":
                r.table("media").index_create("category").run(conn)
                r.table("media").index_create("group").run(conn)
                r.table("media").index_create("kind").run(conn)
                r.table("media").index_create("name").run(conn)
                r.table("media").index_create("status").run(conn)
                r.table("media").index_create(
                    "status_category", [r.row["status"], r.row["category"]]
                ).run(conn)
                r.table("media").index_create(
                    "status_group", [r.row["status"], r.row["group"]]
                ).run(conn)
                r.table("media").index_create(
                    "status_user", [r.row["status"], r.row["user"]]
                ).run(conn)
                r.table("media").index_create("url-isard").run(conn)
                r.table("media").index_create("url-web").run(conn)
                r.table("media").index_create("user").run(conn)

                r.table("media").index_wait().run(conn)

            case "deployments":
                r.table("deployments").index_create("user").run(conn)
                r.table("deployments").index_create("co_owners", multi=True).run(conn)
                r.table("deployments").index_wait().run(conn)
