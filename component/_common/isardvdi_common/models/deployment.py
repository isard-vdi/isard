#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import traceback
from typing import List

from isardvdi_common.connections.rethink_base import PydanticBase, pydantic_optional
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.log import logger
from rethinkdb import r

from ..helpers.desktop_events import DesktopEvents
from ..schemas.deployment import CreateDictDeployment
from ..schemas.shared.allowed import Allowed
from ..schemas.shared.image import Image


class DeploymentModel(PydanticBase):
    name: str = None
    description: str | None = None
    tag: str = None
    tag_visible: bool = False
    user: str = None
    allowed: Allowed = None
    co_owners: List[str] | None = None
    create_dict: List[CreateDictDeployment] = None
    user_permissions: List[str] = []
    kind: str = None
    image: Image = None


@pydantic_optional
class DeploymentUpdateModel(DeploymentModel):
    pass


class Deployment(RethinkCustomBase):
    """
    Manage Deployment Objects

    Use constructor with keyword arguments to create new Deployment Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Deployment Object.
    """

    _rdb_table = "deployments"

    _rdb_table_schema = DeploymentModel

    def toggle_visible(self, stop_started_domains=True):
        # Only the "self.id not in the deployments table" case should map
        # to 404. Any other error (connection, permissions, stream
        # failure) is a real server fault and must propagate, not be
        # re-dressed as "deployment not found".
        if not self.__class__.exists(self.id):
            raise Error(
                "not_found",
                "Deployment id not found: " + str(self.id),
                description_code="not_found" + str(self.id),
            )
        try:
            visible = not self.tag_visible
            if visible:
                stop_started_domains = False
            with self._rdb_context():
                r.table("domains").get_all(self.id, index="tag").update(
                    {"tag_visible": visible}
                ).run(self._rdb_connection)
            self.tag_visible = visible
            Caches.invalidate_cache("deployments", self.id)
        except Exception:
            logger.error(
                "toggle_visible failed for deployment %s: %s",
                self.id,
                traceback.format_exc(),
            )
            raise

        if stop_started_domains:
            with self._rdb_context():
                desktops_ids = list(
                    r.table("domains")
                    .get_all(self.id, index="tag")["id"]
                    .run(self._rdb_connection)
                )
                DesktopEvents.desktops_stop(desktops_ids, force=True)

    @classmethod
    def get(cls, id):
        # TODO(separate-common-classes): remove this as it will be implemented in the RethinkBase class
        """
        Get a deployment by its ID
        """
        with cls._rdb_context():
            deployment = r.table(cls._rdb_table).get(id).run(cls._rdb_connection)
        return deployment

    ##### TODO: Check the following methods for correctness and completeness #####

    def check_desktops_started(self):
        with self._rdb_context():
            started_desktops = list(
                r.table("domains")
                .get_all(self.id, index="tag")
                .filter(
                    lambda desktop: r.not_(
                        r.expr(["Stopped", "Failed", "Unknown"]).contains(
                            desktop["status"]
                        )
                    )
                )
                .pluck("status")
                .run(self._rdb_connection)
            )
        if len(started_desktops) > 0:
            raise Error(
                "precondition_required",
                "The deployment " + str(self.id) + " desktops must be stopped ",
                description_code="deployment_stop",
            )
        if any(
            [desktop["status"].startswith("Creating") for desktop in started_desktops]
        ):
            raise Error(
                "precondition_required",
                "The deployment " + str(self.id) + " desktops are being created",
                description_code="deployment_stop",
            )

    def get_co_owners(self):
        try:
            with self._rdb_context():
                deployment = (
                    r.table("deployments").get(self.id).run(self._rdb_connection)
                )
            return {
                "owner": Alloweds.get_allowed({"users": [deployment.get("user")]})[
                    "users"
                ][0],
                "co_owners": Alloweds.get_allowed(
                    {"users": deployment.get("co_owners")}
                )["users"],
            }
        except Exception:
            raise Error(
                "not_found",
                f"Not found deployment id to get co-owners: {self.id}",
                description_code="not_found",
            )

    def update_co_owners(self, co_owners: list):
        try:
            with self._rdb_context():
                deployment = (
                    r.table("deployments").get(self.id).run(self._rdb_connection)
                )
        except Exception:
            raise Error(
                "not_found",
                f"Not found deployment id to update co-owners: {self.id}",
                description_code="not_found",
            )

        try:
            owner = deployment.get("user")
            if owner in co_owners:
                co_owners.remove(owner)

            with self._rdb_context():
                co_owners = (
                    r.table("users")
                    .get_all(r.args(co_owners))
                    .filter(lambda doc: doc["role"].ne("user"))
                    .pluck("id")
                    .map(lambda doc: doc["id"])
                    .coerce_to("array")
                    .run(self._rdb_connection)
                )

            with self._rdb_context():
                r.table("deployments").get(self.id).update(
                    {"co_owners": co_owners}
                ).run(self._rdb_connection)
            Caches.invalidate_cache("deployments", self.id)
        except Exception:
            raise Error(
                "internal_server",
                f"Unable to update co-owners for deployment: {self.id}",
                description_code="unable_to_update",
            )

    def get_deployment_permissions(self):
        users_permissions = Caches.get_document(
            "deployments", self.id, ["user_permissions"]
        )
        if users_permissions is None:
            raise Error(
                "not_found",
                "Could not find deployment",
                description_code="not_found",
            )
        return users_permissions

    def get_deployment_details_hardware(self):
        with self._rdb_context():
            hardware = (
                r.table("deployments")
                .get(self.id)
                .pluck("create_dict")["create_dict"][0]
                .merge(
                    lambda domain: {
                        "video_name": domain["hardware"]["videos"].map(
                            lambda video: r.table("videos").get(video)["name"]
                        ),
                        "boot_name": domain["hardware"]["boot_order"].map(
                            lambda boot_order: r.table("boots").get(boot_order)["name"]
                        ),
                        "reservable_name": r.branch(
                            domain["reservables"]["vgpus"].default(None),
                            domain["reservables"]["vgpus"].map(
                                lambda reservable: r.table("reservables_vgpus").get(
                                    reservable
                                )["name"]
                            ),
                            False,
                        ),
                    }
                )
                .run(self._rdb_connection)
            )
        if "interfaces" in hardware["hardware"]:
            interfaces = hardware["hardware"]["interfaces"]
            hardware["hardware"]["interfaces"] = []
            # Loop instead of a get_all query to keep the interfaces array order
            for interface in interfaces:
                with self._rdb_context():
                    hardware["hardware"]["interfaces"].append(
                        r.table("interfaces")
                        .get(interface)
                        .pluck("id", "name")
                        .run(self._rdb_connection)
                    )
        if "isos" in hardware["hardware"]:
            isos = hardware["hardware"]["isos"]
            hardware["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                with self._rdb_context():
                    hardware["hardware"]["isos"].append(
                        r.table("media")
                        .get(iso["id"])
                        .pluck("id", "name")
                        .run(self._rdb_connection)
                    )
        if "floppies" in hardware["hardware"]:
            with self._rdb_context():
                hardware["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(self._rdb_connection)
                )
        hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576
        return hardware

    def stop(self):
        try:
            with self._rdb_context():
                domains_ids = [
                    d["id"]
                    for d in r.table("domains")
                    .get_all(self.id, index="tag")
                    .pluck("id")
                    .run(self._rdb_connection)
                ]
        except Exception:
            raise Error(
                "not_found",
                "Deployment id not found: " + str(self.id),
                description_code="not_found" + str(self.id),
            )

        DesktopEvents.desktops_stop(domains_ids, force=True)

    @classmethod
    def get_deployments_with_resource(cls, table, item):
        """Get deployments that use a specific resource"""
        if table in ["media", "reservables_vgpus", "interfaces", "boots", "videos"]:
            indexes = {
                "media": "isos",
                "reservables_vgpus": "vgpus",
                "interfaces": "interfaces",
                "boots": "boot_order",
                "videos": "videos",
            }
            with cls._rdb_context():
                return list(
                    r.table("deployments")
                    .get_all(item["id"], index=indexes[table])
                    .eq_join("user", r.table("users"))
                    .pluck(
                        {
                            "left": {"id": True},
                            "right": {
                                "id": True,
                                "group": True,
                                "category": True,
                                "role": True,
                            },
                        }
                    )
                    .map(
                        lambda doc: {
                            "id": doc["left"]["id"],
                            "user_data": {
                                "role_id": doc["right"]["role"],
                                "category_id": doc["right"]["category"],
                                "group_id": doc["right"]["group"],
                                "user_id": doc["right"]["id"],
                            },
                        }
                    )
                    .run(cls._rdb_connection)
                )
        else:
            raise Error(
                "forbidden",
                "Table without deployments",
            )
