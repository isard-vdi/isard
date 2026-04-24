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


from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.isard_viewer import IsardViewer
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from isardvdi_common.lib.domains.desktops.desktop_viewers import DesktopViewers
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r

isard_viewer = IsardViewer()


class DeploymentDesktopsProcessed(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def get_deployment_desktops_grouped_by_user_status(cls, deployment_id):
        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .group(r.row["user"])
                .map(
                    lambda domain: {
                        "status": domain["status"],
                        "accessed": domain["accessed"],
                        "tag_visible": domain["tag_visible"],
                    }
                )
                .ungroup()
                .map(
                    lambda group: {
                        "user": group["group"],
                        "statuses": group["reduction"]
                        .group("status")
                        .count()
                        .ungroup()
                        .map(
                            lambda status_group: {
                                "status": status_group["group"],
                                "amount": status_group["reduction"],
                            }
                        ),
                        "last_access": group["reduction"]
                        .filter(lambda d: d["accessed"].ne(None))
                        .max("accessed")
                        .default(None)
                        .get_field("accessed")
                        .default(None),
                        "visible": group["reduction"]
                        .filter(lambda d: d["tag_visible"].eq(True))
                        .count()
                        .gt(0),
                    }
                )
                .run(cls._rdb_connection)
            )
        return list(desktops)

    @classmethod
    def get_with_tag_dict(cls, tag):
        """
        Get domains with specific deployment tag
        """
        with cls._rdb_context():
            desktops = list(
                r.table(cls._rdb_table)
                .get_all(tag, index="tag")
                .filter(lambda domain: domain["kind"] == "desktop")
                .pluck(
                    "status",
                    "user",
                    "viewer",
                    "tag_visible",
                    "id",
                    "viewers",
                    "name",
                    "username",
                    "accessed",
                    "booking_id",
                )
                .run(cls._rdb_connection)
            )

        # TODO: do this at once with all viewers, like in the old api
        # see `api/libv2/isardViewer.py` for reference
        for desktop in desktops:
            # TODO(separate-common-classes): move get_novnc_data to a DesktopHelpers class
            desktop["viewer"] = DesktopViewers.get_novnc_data(desktop)
        return desktops

    @classmethod
    def get_deployment_user_desktops(cls, deployment_id, user_id):
        """
        Get the deployment for a specific user
        """
        with cls._rdb_context():
            desktops = (
                r.table(cls._rdb_table)
                .get_all(deployment_id, index="tag")
                .filter(lambda domain: (domain["user"].eq(user_id)))
                .merge(
                    lambda lab: {
                        "total_desktops": r.table("domains")
                        .get_all(lab["tag"], index="tag")
                        .count()
                    }
                )
                .pluck(
                    "image",
                    "name",
                    "id",
                    "status",
                    "ip",
                    "description",
                    "accessed",
                    "total_desktops",
                    "tag_visible",
                    {"viewer": {"guest_ip", "passwd"}},
                    "guest_properties",
                )
                .run(cls._rdb_connection)
            )
        return list(desktops)

    @classmethod
    def update_desktops_visibility(cls, desktop_ids, visible):
        """
        Update the visibility of desktops by a list of IDs.
        """
        with cls._rdb_context():
            return (
                r.table(cls._rdb_table)
                .get_all(r.args(desktop_ids))
                .update(lambda desktop: {"tag_visible": visible})
                .run(cls._rdb_connection)
            )

    @classmethod
    def _parse_deployment_desktop(cls, desktop):
        # TODO(separate-common-classes): move this to a desktop helpers class
        if desktop["status"] in [
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.waiting_ip.value,
        ] and desktop.get("viewer", {}).get("static"):
            try:
                viewer = isard_viewer.viewer_data(
                    desktop["id"],
                    "browser-vnc",
                )
            except Exception:
                viewer = False
        else:
            viewer = False
        user_photo = desktop.get("user_photo")
        desktop = DesktopsProcessed._parse_desktop(desktop)
        desktop["viewer"] = viewer
        desktop["user_photo"] = user_photo
        desktop["user_name"] = Caches.get_document("users", desktop["user"], ["name"])
        desktop["group_name"] = Caches.get_document(
            "groups", desktop["group"], ["name"]
        )
        return desktop

    @classmethod
    def jumper_url_reset(cls, deployment_id):
        with cls._rdb_context():
            deployment_desktops = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id", "user", "jumperurl")
                .run(cls._rdb_connection)
            )

        for deployment_desktop in deployment_desktops:
            DesktopDirectViewer.gen_jumpertoken(deployment_desktop["id"])

    @classmethod
    def get_deployment_user_desktop(cls, user_id, deployment_id):
        """_From api/libv2/api_desktops_persistent.py get_deployment_user_desktop()_

        Retrieve the user desktop associated with a deployment.

        :param user_id: The ID of the user.
        :param deployment_id: The deployment ID.
        :return: The user desktop associated with the deployment.
        :rtype: dict
        """
        with cls._rdb_context():
            return (
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .filter({"user": user_id})
                .pluck(
                    "id",
                    "name",
                    "description",
                    "user",
                    "category",
                    "group",
                    "status",
                    "accessed",
                    "tag_visible",
                )
                .nth(0)
                .default(None)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_desktop_ids(cls, deployment_id: str, user_id: str):
        """
        Get the all the desktop ids of a user in a deployment
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(["desktop", user_id, deployment_id], index="kind_user_tag")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_desktop_ids(cls, deployment_id: str):
        """
        Get the all the desktop ids of a deployment
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )
