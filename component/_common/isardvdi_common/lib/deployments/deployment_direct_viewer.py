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


import csv
import io
import os

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from rethinkdb import r


class DeploymentDirectViewer(RethinkSharedConnection):

    _rdb_table = "deployments"

    @classmethod
    def direct_viewer_csv(cls, deployment_id, regenerate=False):
        with cls._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id", "user", "name", "jumperurl")
                .run(cls._rdb_connection)
            )

        if regenerate:
            domains_to_generate = [d["id"] for d in domains]
        else:
            domains_to_generate = [d["id"] for d in domains if not d.get("jumperurl")]

        for domain_id in domains_to_generate:
            DesktopDirectViewer.gen_jumpertoken(domain_id)

        ## Re-fetch to get updated jumperurls
        if domains_to_generate:
            with cls._rdb_context():
                domains = list(
                    r.table("domains")
                    .get_all(deployment_id, index="tag")
                    .has_fields("jumperurl")
                    .pluck("id", "user", "name", "jumperurl")
                    .run(cls._rdb_connection)
                )

        fieldnames = ["username", "name", "email", "desktop_name", "url"]

        if len(domains) == 0:
            return ",".join(fieldnames)

        user_ids = list(set(d["user"] for d in domains))
        with cls._rdb_context():
            users = list(
                r.table("users")
                .get_all(r.args(user_ids))
                .pluck("id", "username", "name", "email")
                .run(cls._rdb_connection)
            )
        users_by_id = {u["id"]: u for u in users}

        result = []
        for d in domains:
            u = users_by_id[d["user"]]
            result.append(
                {
                    "username": u["username"],
                    "name": u["name"],
                    "email": u["email"],
                    "desktop_name": d["name"],
                    "url": "https://"
                    + os.environ.get("DOMAIN")
                    + "/vw/"
                    + d["jumperurl"],
                }
            )

        result.sort(key=lambda row: (row["username"], row["desktop_name"]))

        with io.StringIO() as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            for row in result:
                writer.writerow(row)
            return csvfile.getvalue()
