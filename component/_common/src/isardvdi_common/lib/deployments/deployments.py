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

import copy
import csv
import io
import logging as log
import os
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.recycle_bin import RecycleBinDeploymentDesktops
from isardvdi_common.helpers.rules import get_unused_item_timeout
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed,
)
from isardvdi_common.lib.deployments.deployment_users import DeploymentUsers
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from isardvdi_common.lib.domains.desktops.desktop_viewers import DesktopViewers
from isardvdi_common.lib.domains.desktops.desktops import DesktopsProcessed
from isardvdi_common.lib.domains.desktops.desktops import (
    DesktopsProcessed as CommonDesktops,
)
from isardvdi_common.lib.domains.templates.templates import TemplatesProcessed
from isardvdi_common.models.deployment import (
    Deployment,
    DeploymentModel,
    DeploymentUpdateModel,
)
from isardvdi_common.models.domain import DomainUpdateModel
from isardvdi_common.schemas.domains import DesktopStatusEnum
from isardvdi_common.schemas.shared.allowed import Allowed
from rethinkdb import r

_validate_tag_desktop_id_for_deployment_cache: TTLCache = TTLCache(maxsize=10, ttl=30)


class DeploymentsProcessed(RethinkSharedConnection):

    _rdb_table = "deployments"

    @classmethod
    def get_deployments_with_resource(cls, table, item):
        """From api/libv2/api_desktops_persistent.py get_deployments_with_resource()"""
        return Deployment.get_deployments_with_resource(table, item)

    @classmethod
    def _parse_booking(cls, deployment_id):
        # TODO(separate-common-classes): move to a helpers class
        deployment_domains = Caches.get_cached_deployment_desktops(deployment_id)
        if not len(deployment_domains):
            return {
                "needs_booking": False,
                "next_booking_start": None,
                "next_booking_end": None,
                "booking_id": False,
            }
        desktop = deployment_domains[0]
        return CommonDesktops._parse_desktop_booking(desktop)

    @classmethod
    def get_deployment_or_none(cls, deployment_id, desktops=True):
        """Like ``get_deployment`` but returns ``None`` for a missing row.

        Useful for change-handler emits triggered by the cascading
        domain-delete that follows a deployment delete: the parent
        deployment row may already be gone by the time the per-domain
        handler runs, and a raised ``Error("not_found")`` only spams the
        backend log without changing what the WebSocket consumers see
        (the deployment-delete event already fired upstream).
        """
        if Caches.get_document("deployments", deployment_id) is None:
            return None
        return cls.get_deployment(deployment_id, desktops=desktops)

    @classmethod
    def get_deployment(cls, deployment_id, desktops=True):
        deployment = Caches.get_document("deployments", deployment_id)
        if deployment is None:
            raise Error(
                "not_found",
                "Deployment id not found: " + str(deployment_id),
                description_code="not_found",
            )
        deployment_desktops = Caches.get_cached_deployment_desktops(deployment_id)
        deployment["totalDesktops"] = len(deployment_desktops)
        deployment["visibleDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["tag_visible"] is True
            ]
        )
        deployment["startedDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["status"]
                in [
                    "Started",
                    "Starting",
                    "StartingPaused",
                    "CreatingAndStarting",
                    "Shutting-down",
                ]
            ]
        )
        deployment["creatingDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["status"]
                in [
                    "Creating",
                    "CreatingAndStarting",
                ]
            ]
        )
        create_dict = deployment.get("create_dict", [{}])[0]
        # deployment["description"] = deployment.get("description")
        deployment["visible"] = deployment.get("tag_visible")
        deployment["desktop_name"] = create_dict.get("name")
        deployment["template"] = Caches.get_document(
            "domains", create_dict.get("template"), ["name"]
        )
        del deployment["create_dict"]

        deployment = {
            **deployment,
            **cls._parse_booking(deployment["id"]),
        }

        if desktops:
            parsed_desktops = []
            with cls._rdb_context():
                desktops = list(
                    r.table("domains")
                    .get_all(deployment_id, index="tag")
                    .pluck(
                        "id",
                        "user",
                        "group",
                        "category",
                        "name",
                        "description",
                        "status",
                        "icon",
                        "os",
                        "image",
                        "persistent",
                        "parents",
                        "create_dict",
                        "viewer",
                        "guest_properties",
                        "accessed",
                        "tag",
                        "booking_id",
                        "tag_visible",
                    )
                    .run(cls._rdb_connection)
                )

            for desktop in desktops:
                desktop["user_name"] = Caches.get_document(
                    "users", desktop["user"], ["name"]
                )
                desktop["user_photo"] = Caches.get_document(
                    "users", desktop["user"], ["photo"]
                )
                desktop["category_name"] = Caches.get_document(
                    "categories", desktop["category"], ["name"]
                )
                desktop["group_name"] = Caches.get_document(
                    "groups", desktop["group"], ["name"]
                )

                tmp_desktop = DeploymentDesktopsProcessed._parse_deployment_desktop(
                    desktop
                )
                parsed_desktops.append(tmp_desktop)
            deployment["desktops"] = parsed_desktops

        return deployment

    @classmethod
    def get_user_deployments(cls, user_id):
        with cls._rdb_context():
            deployments_owner = list(
                r.table("deployments")
                .get_all(user_id, index="user")
                .merge(
                    lambda deployment: {
                        # "description": deployment["description"],
                        "visible": deployment["tag_visible"],
                        "template": r.table("domains")
                        .get(deployment["create_dict"][0]["template"])
                        .default({"name": False})["name"],
                        "desktop_name": deployment["create_dict"][0]["name"],
                    }
                )
                .without("create_dict")
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            deployments_coowners = list(
                r.table("deployments")
                .get_all(user_id, index="co_owners")
                .merge(
                    lambda deployment: {
                        # "description": deployment["description"],
                        "visible": deployment["tag_visible"],
                        "template": r.table("domains")
                        .get(deployment["create_dict"][0]["template"])
                        .default({"name": False})["name"],
                        "desktop_name": deployment["create_dict"][0]["name"],
                    }
                )
                .without("create_dict")
                .run(cls._rdb_connection)
            )
        deployments = deployments_owner + deployments_coowners

        for deployment in deployments:
            deployment_desktops = Caches.get_cached_deployment_desktops(
                deployment["id"]
            )

            deployment["total_desktops"] = deployment["totalDesktops"] = len(
                deployment_desktops
            )
            deployment["visible_desktops"] = deployment["visibleDesktops"] = len(
                [
                    desktop
                    for desktop in deployment_desktops
                    if desktop["tag_visible"] is True
                ]
            )
            deployment["started_desktops"] = deployment["startedDesktops"] = len(
                [
                    desktop
                    for desktop in deployment_desktops
                    if desktop["status"]
                    in [
                        "Started",
                        "Starting",
                        "StartingPaused",
                        "CreatingAndStarting",
                        "Shutting-down",
                    ]
                ]
            )
            deployment["creating_desktops"] = deployment["creatingDesktops"] = len(
                [
                    desktop
                    for desktop in deployment_desktops
                    if desktop["status"]
                    in [
                        "Creating",
                        "CreatingAndStarting",
                    ]
                ]
            )

        deployments.sort(key=lambda x: x["name"].lower(), reverse=True)

        parsed_deployments = []
        for deployment in deployments:
            for create_dict in deployment.get("create_dict", []):
                template = Caches.get_document("domains", create_dict.get("template"))
                if not template:
                    # If the template does not exist, delete the deployment
                    DesktopEvents.deployment_delete(deployment["id"], "system")

            parsed_deployments.append(
                {**deployment, **cls._parse_booking(deployment["id"])}
            )
        return parsed_deployments

    @classmethod
    def get_owned_deployments(cls, user_payload):
        """
        Get all deployments owned by the user
        """
        with cls._rdb_context():
            deployments = list(
                r.table(cls._rdb_table)
                .get_all(user_payload["user_id"], index="user")
                .pluck(
                    "tag_visible",
                    "name",
                    "id",
                    "description",
                    "image",
                    {"create_dict": ["reservables", "name", "template"]},
                )
                .merge(
                    lambda deployment: {
                        "total_desktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .count(),
                        "started_desktops": r.table("domains")
                        .get_all([deployment["id"], "Started"], index="tag_status")
                        .count(),
                        "visible_desktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .filter({"tag_visible": True})
                        .count(),
                        "desktop_names": r.expr(deployment["create_dict"]).map(
                            lambda cd: cd["name"]
                        ),
                        "co_owner": False,
                    }
                )
                .run(cls._rdb_connection)
            )
        parsed_deployments = []
        for deployment in deployments:
            deployment = {
                **deployment,
                **cls._parse_booking(deployment_id=deployment["id"]),
            }
            deployment["total_users"] = len(DeploymentUsers.get_users(deployment["id"]))
            # Check that the templates used in the deployment still exist
            for create_dict in deployment.get("create_dict", []):
                template = Caches.get_document("domains", create_dict.get("template"))
                if not template:
                    DesktopEvents.deployment_delete(deployment["id"], "system")

            # Remove the create_dict from the deployment response
            deployment.pop("create_dict", None)
            parsed_deployments.append(deployment)
        return parsed_deployments

    @classmethod
    def get_co_owned_deployments(cls, user_payload):
        """
        Get all deployments that the user is co-owner, according to the deployments' co-owner list
        """
        with cls._rdb_context():
            deployments = list(
                r.table(cls._rdb_table)
                .get_all(user_payload["user_id"], index="co_owners")
                .pluck(
                    "tag_visible",
                    "name",
                    "id",
                    "description",
                    "image",
                    {"create_dict": {"reservables": True, "name": True}},
                )
                .merge(
                    lambda deployment: {
                        "total_desktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .count(),
                        "started_desktops": r.table("domains")
                        .get_all([deployment["id"], "Started"], index="tag_status")
                        .count(),
                        "visible_desktops": r.table("domains")
                        .get_all(deployment["id"], index="tag")
                        .filter({"tag_visible": True})
                        .count(),
                        "desktop_names": r.expr(deployment["create_dict"]).map(
                            lambda cd: cd["name"]
                        ),
                        "co_owner": True,
                    }
                )
                .run(cls._rdb_connection)
            )
        parsed_deployments = []
        for deployment in deployments:
            deployment = {
                **deployment,
                **cls._parse_booking(deployment_id=deployment["id"]),
            }
            deployment["total_users"] = len(DeploymentUsers.get_users(deployment["id"]))
            # Remove the create_dict from the deployment response
            deployment.pop("create_dict", None)
            parsed_deployments.append(deployment)
        return parsed_deployments

    @classmethod
    def retrieve_deployment(cls, deployment_id):
        """
        Get detailed information about a specific deployment by its ID.
        This includes the total number of desktops and their statuses.
        """
        with cls._rdb_context():
            deployment_info = (
                r.table(cls._rdb_table)
                .get(deployment_id)
                .pluck(
                    "id",
                    "name",
                    "description",
                    "tag_visible",
                    {"create_dict": {"template": True}},
                )
                .merge(
                    {
                        "started_desktops": r.table("domains")
                        .get_all([deployment_id, "Started"], index="tag_status")
                        .count(),
                        "visible_desktops": r.table("domains")
                        .get_all(deployment_id, index="tag")
                        .filter({"tag_visible": True})
                        .count(),
                    }
                )
                .run(cls._rdb_connection)
            )
        return deployment_info

    @classmethod
    def retrieve_user_deployment(cls, deployment_id, user_id):
        """
        Get detailed information about a specific deployment by its ID for a specific user.
        This includes the total number of desktops and their statuses.
        """
        with cls._rdb_context():
            deployment_info = (
                r.table(cls._rdb_table)
                .get(deployment_id)
                .pluck(
                    "id",
                    "name",
                    "description",
                    "tag_visible",
                    "user",
                    # TODO: Add a resources field to deployments and return it here
                )
                .run(cls._rdb_connection)
            )

        user = Caches.get_document(
            "users", user_id, ["id", "name", "photo", "username"]
        )
        owner = Caches.get_document(
            "users", deployment_info.get("user"), ["id", "name", "photo", "username"]
        )

        return {
            **deployment_info,
            **{
                "user": {
                    "id": user.get("id"),
                    "name": user.get("name"),
                    "photo": user.get("photo"),
                    "username": user.get("username"),
                },
                "owner": {
                    "id": owner.get("id"),
                    "name": owner.get("name"),
                    "photo": owner.get("photo"),
                    "username": owner.get("username"),
                },
            },
        }

    @classmethod
    def get_shared_deployments(cls, user_payload):
        """
        Get all deployments that the user has access to, according to the deployments' allowed lists
        """
        with cls._rdb_context():
            deployments = list(
                r.table(cls._rdb_table)
                .filter(
                    lambda deployment: r.and_(
                        deployment["allowed"].has_fields("users"),
                        deployment["allowed"].has_fields("groups"),
                        r.or_(
                            r.branch(
                                deployment["allowed"]["users"].eq(False),
                                False,
                                deployment["allowed"]["users"].contains(
                                    user_payload["user_id"]
                                ),
                            ),
                            r.branch(
                                deployment["allowed"]["groups"].eq(False),
                                False,
                                r.and_(
                                    deployment["allowed"]["groups"].count().gt(0),
                                    deployment["allowed"]["groups"].contains(
                                        user_payload["group_id"]
                                    ),
                                ),
                            ),
                        ),
                    )
                )
                .filter({"tag_visible": True})
                .pluck(
                    "image",
                    "name",
                    "id",
                    "description",
                    "user",
                    {"create_dict": {"reservables": True, "name": True}},
                )
                .merge(
                    lambda deployment: {
                        "total_desktops": r.table("domains")
                        .get_all(
                            ["desktop", user_payload["user_id"], deployment["id"]],
                            index="kind_user_tag",
                        )
                        .count(),
                        "started_desktops": r.table("domains")
                        .get_all(
                            ["desktop", user_payload["user_id"], deployment["id"]],
                            index="kind_user_tag",
                        )
                        .filter({"status": "Started"})
                        .count(),
                    }
                )
                .run(cls._rdb_connection)
            )
        parsed_deployments = []
        for deployment in deployments:
            deployment = {
                **deployment,
                **cls._parse_booking(deployment_id=deployment["id"]),
            }
            # Add deployment owner name and photo
            owner_id = deployment.pop("user", None)
            deployment["user"] = {
                "name": Caches.get_document("users", owner_id, ["name"]),
                "photo": Caches.get_document("users", owner_id, ["photo"]),
            }
            # Remove the create_dict from the deployment response
            deployment.pop("create_dict", None)
            parsed_deployments.append(deployment)
        return parsed_deployments

    @classmethod
    def check_deployment_bookings(cls, payload, deployment):
        with cls._rdb_context():
            deployment_bookings = list(
                r.table("bookings")
                .get_all(deployment["id"], index="item_id")
                .filter(lambda booking: booking["end"].gt(r.now()))
                .run(cls._rdb_connection)
            )

        deployment_users = DeploymentUsers.get_selected_users(
            payload,
            deployment["allowed"],
            deployment["create_dict"][0]["name"],
            deployment["id"],
            existing_desktops_error=False,
            include_existing_desktops=True,
        )

        for booking in deployment_bookings:
            if booking["units"] < len(deployment_users):
                raise Error(
                    "precondition_required",
                    f'The deployment {deployment["id"]} has a future booking ({booking["start"]} - {booking["end"]}) with only {booking["units"]} units booked and recreating would require {len(deployment_users)} units',
                    description_code="deployment_recreate_booking_not_enough_units",
                )

    @classmethod
    def edit_deployment(cls, payload, deployment_id, data):
        raise Error(
            "internal_server", "This function is deprecated. use apiv4 instead."
        )
        deployment_data = {}
        deployment = Caches.get_document("deployments", deployment_id)
        if not deployment:
            raise Error(
                "not_found",
                "Not found deployment id to edit: " + str(deployment_id),
                description_code="not_found",
            )
        deployment_data["name"] = data.get("name")
        deployment_data["description"] = data.get("description")
        data["name"] = data.pop("desktop_name")
        data["reservables"] = data.get("hardware").pop("reservables")
        data["hardware"]["memory"] = data["hardware"]["memory"] * 1048576
        DesktopViewers.check_viewers(data, deployment)
        deployment_booking = cls._parse_booking(deployment["id"])
        DeploymentUsers.get_selected_users(
            payload,
            deployment.get("allowed"),
            data.get("name"),
            existing_desktops_error=False,
            include_existing_desktops=True,
        )
        if data.get("reservables") != deployment["create_dict"][0].get(
            "reservables"
        ) and deployment_booking.get("next_booking_end"):
            raise Error(
                "precondition_required",
                "Can't edit a deployment with a scheduled booking",
                traceback.format_exc(),
                "cant_edit_booked_deployment",
            )
        if data["reservables"].get("vgpus") == ["None"]:
            data["reservables"]["vgpus"] = None
        user_permissions = data.pop("user_permissions")
        with cls._rdb_context():
            deployment_row = (
                r.table("deployments")
                .get(deployment_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if deployment_row is None:
            raise Error(
                "not_found",
                f"Deployment {deployment_id} not found",
                description_code="deployment_not_found",
            )
        create_dict_list = deployment_row.get("create_dict") or []
        if not create_dict_list:
            raise Error(
                "bad_request",
                f"Deployment {deployment_id} has no create_dict to update",
                description_code="deployment_invalid",
            )
        original_create_dict = create_dict_list[0]

        Deployment.update_document(
            deployment_id,
            {
                "create_dict": [
                    {
                        **original_create_dict,
                        **data,
                        "guest_properties": data["guest_properties"],
                    }
                ],
                "name": deployment_data["name"],
                "description": deployment_data["description"],
                "user_permissions": user_permissions,
            },
        )
        Caches.invalidate_cache("deployments", deployment_id)
        # If the networks have changed new macs should be generated for each domain
        if (
            deployment["create_dict"][0]["hardware"]["interfaces"]
            != data["hardware"]["interfaces"]
        ):
            with cls._rdb_context():
                domains = (
                    r.table("domains")
                    .get_all(deployment_id, index="tag")
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
            deployment_interfaces = data["hardware"]["interfaces"]
            data["hardware"]["memory"] = data["hardware"]["memory"] / 1048576
            for domain in domains:
                domain_data = copy.deepcopy(data)
                domain_update = DesktopsProcessed.parse_domain_update(
                    domain, domain_data
                )
                with cls._rdb_context():
                    r.table("domains").get(domain).update(
                        {
                            "status": "Updating",
                            "create_dict": {
                                "hardware": domain_update["create_dict"]["hardware"],
                                "reservables": r.literal(data.get("reservables")),
                            },
                            "name": data["name"],
                            "description": data["description"],
                            "guest_properties": data.get("guest_properties"),
                            "image": data["image"],
                        }
                    ).run(cls._rdb_connection)
                Caches.invalidate_cache("domains", domain)
                data["hardware"]["interfaces"] = deployment_interfaces

        # Otherwise the rest of the hardware can be updated at once
        else:
            data["hardware"].pop("interfaces")
            with cls._rdb_context():
                r.table("domains").get_all(deployment_id, index="tag").update(
                    {
                        "status": "Updating",
                        "create_dict": {
                            "hardware": data["hardware"],
                            "reservables": r.literal(data.get("reservables")),
                        },
                        "name": data["name"],
                        "description": data["description"],
                        "guest_properties": r.literal(data["guest_properties"]),
                        "image": data["image"],
                    }
                ).run(cls._rdb_connection)

    @classmethod
    def _change_owner_deployments(cls, deployments_ids, user_data, old_user_id):
        # TODO: change allowed to false if the target user is on a different category
        with cls._rdb_context():
            deployments_data = list(
                r.table("deployments")
                .get_all(r.args(deployments_ids))
                .pluck("id", "name")
                .run(cls._rdb_connection)
            )
        Helpers.update_duplicated_names(
            "deployments",
            deployments_data,
            user=user_data["new_user"]["user"],
        )
        if deployments_ids:
            # check if the new owner is role user
            if user_data["payload"]["role_id"] == "user":
                raise Error("bad_request", 'Role "user" can not own deployments.')

            # check deployment create quota, ignore number of users in the deployment
            if Quotas.get_user_migration_check_quota_config():
                Quotas.deployment_create(
                    owner_id=user_data["new_user"]["user"],
                    quantity=len(deployments_ids),
                    desktops_len=None,
                    users=None,
                )
            with cls._rdb_context():
                # for each deployment old_user_id is in co_owners, remove old_user_id from co_owners
                r.table("deployments").get_all(old_user_id, index="co_owners").update(
                    {"co_owners": r.row["co_owners"].difference([old_user_id])}
                ).run(cls._rdb_connection)

            # change owner
            for i in range(0, len(deployments_ids), 100):
                batch_deployments_ids = deployments_ids[i : i + 100]
                with cls._rdb_context():
                    r.table("deployments").get_all(
                        r.args(batch_deployments_ids)
                    ).update(
                        {
                            "user": user_data["new_user"]["user"],
                            "co_owners": r.literal([]),
                        }
                    ).run(
                        cls._rdb_connection
                    )

    @classmethod
    def change_owner_deployment(cls, payload, deployment_id, owner_id):
        deployment_user = Caches.get_document("deployments", deployment_id, ["user"])
        category = Caches.get_document("users", deployment_user, ["category"])
        user_data = Helpers.get_new_user_data(owner_id)
        if (
            user_data["new_user"].get("category") != category
            and user_data["new_user"].get("role") != "admin"
        ):
            DeploymentUsers.edit_deployment_users(
                payload,
                deployment_id,
                Allowed(**{}).model_dump(),
            )
        Caches.invalidate_cache("deployments", deployment_id)
        cls._change_owner_deployments([deployment_id], user_data, deployment_user)

    @classmethod
    def create_deployment_desktops(cls, deployment_tag, desktops_data, users):
        desktops = []
        for desktop_data in desktops_data:
            for user in users:
                desktop = desktop_data.copy()
                desktop["id"] = str(uuid.uuid4())
                desktops.append(
                    {
                        "name": desktop["name"],
                        "description": desktop.get("description"),
                        "template_id": desktop["template_id"],
                        "hardware": desktop.get("hardware"),
                        "guest_properties": desktop.get("guest_properties"),
                        "image": desktop.get("image"),
                        "user_id": user["id"],
                        "deployment_tag_dict": {
                            **deployment_tag,
                            "tag_desktop_id": desktop["tag_desktop_id"],
                        },
                        "domain_id": desktop["id"],
                        "new_data": desktop,
                    }
                )
        deployment = Caches.get_document("deployments", deployment_tag["tag"])
        DesktopsProcessed.new_from_templateTh(desktops, deployment)

    @classmethod
    def _prepare_recreate(cls, payload, deployment_id):
        """Validate and build the recreate plan without side effects.

        Returns a tuple ``(deployment, plan)`` where ``plan`` is a list of
        ``(deployment_tag, [desktop_dict], users)`` ready to be passed to
        ``create_deployment_desktops``. Raises ``Error`` on the first
        problem found so the caller can fail fast *before* deleting the
        live desktops — otherwise a recreate that 500s would leave the
        deployment empty.
        """
        if not Caches.get_document("deployments", deployment_id):
            raise Error(
                "not_found",
                "Not found deployment id to recreate: " + str(deployment_id),
                description_code="not_found",
            )

        with cls._rdb_context():
            deployment = (
                r.table("deployments").get(deployment_id).run(cls._rdb_connection)
            )

        # If the deployment has bookings check if the new deployment can be recreated considering the booked units
        deployment_booking = cls._parse_booking(deployment["id"])
        if deployment_booking.get("next_booking_end"):
            cls.check_deployment_bookings(payload, deployment)

        plan = []
        for create_dict in deployment.get("create_dict") or []:
            recipe_name = create_dict.get("name") or "<unnamed>"

            template_id = create_dict.get("template")
            if not template_id or not Caches.get_document("domains", template_id):
                raise Error(
                    "not_found",
                    f"Template {template_id} for recipe {recipe_name} not found",
                    description_code="not_found",
                )

            hardware = create_dict.get("hardware") or {}
            if "memory" not in hardware:
                raise Error(
                    "bad_request",
                    f"Recipe {recipe_name} is missing hardware.memory; the deployment cannot be recreated",
                )
            if "interfaces" not in hardware:
                raise Error(
                    "bad_request",
                    f"Recipe {recipe_name} is missing hardware.interfaces; the deployment cannot be recreated",
                )

            users = DeploymentUsers.get_selected_users(
                payload,
                deployment["allowed"],
                create_dict["name"],
                deployment["id"],
                existing_desktops_error=False,
                include_existing_desktops=False,
            )

            desktop = {
                "name": create_dict["name"],
                "description": create_dict.get("description"),
                "template_id": template_id,
                "hardware": {
                    **hardware,
                    "memory": hardware["memory"] / 1048576,
                    "interfaces": [
                        i["id"] if isinstance(i, dict) else i
                        for i in hardware["interfaces"]
                    ],
                },
                "tag_desktop_id": create_dict["tag_desktop_id"],
            }
            if create_dict.get("guest_properties"):
                desktop["guest_properties"] = create_dict["guest_properties"]
            if create_dict.get("reservables"):
                desktop["hardware"]["reservables"] = create_dict["reservables"]
            if create_dict.get("image"):
                desktop["image"] = create_dict["image"]

            deployment_tag = {
                "tag": deployment_id,
                "tag_visible": deployment["tag_visible"],
            }
            plan.append((deployment_tag, desktop, users))

        return deployment, plan

    @classmethod
    def recreate(cls, payload, deployment_id):
        """Create the desktops missing for the deployment's allowed users.

        Mirrors apiv3 ``api_deployments.recreate``: existing desktops are
        left untouched. ``_prepare_recreate`` resolves users with
        ``include_existing_desktops=False`` and builds the full plan
        (raising on any malformed create_dict) before a single desktop is
        created, so a bad recipe fails fast without partial side effects.
        """
        _, plan = cls._prepare_recreate(payload, deployment_id)
        for deployment_tag, desktop, users in plan:
            cls.create_deployment_desktops(deployment_tag, [desktop], users)

    @classmethod
    def create(
        cls,
        payload,
        name,
        description,
        selected,
        desktops: list[dict],
        co_owners=[],
        visible=False,
        user_permissions=[],
        image: dict = None,
        create_owner_desktop=True,
    ):
        # Add payload user if not in list
        if create_owner_desktop:
            if selected["users"]:
                if payload["user_id"] not in selected["users"]:
                    selected["users"].append(payload["user_id"])
            else:
                selected["users"] = [payload["user_id"]]

        # Get the users
        users = DeploymentUsers.get_selected_users(
            payload,
            selected,
            "",
            deployment_id=None,
            existing_desktops_error=False,
            include_existing_desktops=True,
        )

        Quotas.deployment_create(
            owner_id=payload["user_id"],
            quantity=1,
            desktops_len=len(desktops),
            users=users,
        )

        Helpers.check_duplicate(
            "deployments",
            name,
            user=payload["user_id"],
        )

        deployment_id = str(uuid.uuid4())

        for desktop in desktops:
            desktop["tag_desktop_id"] = str(uuid.uuid4())

        parsed_desktops = []

        for desktop in desktops:
            template = Caches.get_document("domains", desktop["template_id"])
            if not template:
                raise Error(
                    "not_found",
                    "Template not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )

            TemplatesProcessed.check_template_status(None, template)
            if not Alloweds.is_allowed(payload, template, "domains"):
                raise Error(
                    "forbidden",
                    "User not allowed to use this template",
                    description_code="template_not_allowed",
                )

            desktop["description"] = (
                desktop.get("description") or template["description"]
            )
            desktop["image"] = desktop.get("image") or template["image"]

            DesktopViewers.check_new_desktop_viewers(desktop, template)

            create_dict, guest_properties = (
                DesktopsProcessed.merge_new_data_with_template(
                    desktop["template_id"], desktop
                )
            )

            try:
                create_dict = Helpers._parse_media_info(create_dict)
            except Exception:
                raise Error(
                    "internal_server",
                    "new_from_template: unable to parse media info.",
                    description_code="unable_to_parse_media",
                )
            limited_hardware = Quotas.limit_user_hardware_allowed(payload, create_dict)[
                "limited_hardware"
            ]
            if limited_hardware:
                raise Error(
                    "bad_request",
                    "The following hardware cannot be used due to permissions: "
                    + str(limited_hardware),
                )
            desktop.update(
                {
                    "hardware": create_dict["hardware"],
                    "reservables": create_dict.get("reservables"),
                    "guest_properties": guest_properties,
                }
            )

            parsed_desktops.append(desktop)

        # Check the parsed desktops reservables, all of them must be the same, ignoring the ones that have the field vgpus as None
        # ``reservables`` itself is Optional on ``CreateDesktopRequest`` —
        # Vue 3 deployments without a GPU pin omit the key entirely, so
        # the entry is ``None``. Treat that as "no vgpus" rather than
        # crashing with ``NoneType.get``.
        valid_vgpus = [
            tuple((d.get("reservables") or {}).get("vgpus"))
            for d in parsed_desktops
            if (d.get("reservables") or {}).get("vgpus") is not None
        ]
        if valid_vgpus and any(v != valid_vgpus[0] for v in valid_vgpus):
            raise Error(
                "precondition_required",
                "Deployment reservables are not equal across all desktops.",
                description_code="deployment_reservables_not_equal",
            )

        deployment = {
            "allowed": selected,
            "description": description,
            "tag": deployment_id,
            "tag_visible": visible,
            "create_dict": [
                {
                    "description": desktop["description"],
                    "hardware": {
                        **desktop["hardware"],
                        # Must be in bytes for the deployment creation. When creating desktops its in MiB and will be converted later
                        "memory": desktop["hardware"]["memory"] * 1048576,
                    },
                    "reservables": desktop["reservables"],
                    "guest_properties": desktop["guest_properties"],
                    "name": desktop["name"],
                    "template": desktop["template_id"],
                    "image": desktop["image"],
                    "tag_desktop_id": desktop["tag_desktop_id"],
                }
                for desktop in parsed_desktops
            ],
            "id": deployment_id,
            "name": name,
            "user": payload["user_id"],
            "co_owners": co_owners,
            "user_permissions": user_permissions,
            "kind": "desktops",
            "image": image or parsed_desktops[0]["image"],
        }

        for d in parsed_desktops:

            # Check the desktop names
            DeploymentUsers.get_selected_users(
                payload,
                selected,
                d["name"],
                deployment_id=None,
                existing_desktops_error=True,
            )

        """Create deployment"""
        valid_deployment = DeploymentModel(**deployment).model_dump(
            mode="json", exclude_unset=False
        )
        with cls._rdb_context():
            r.table("deployments").insert(valid_deployment).run(cls._rdb_connection)

        """Create desktops for each user found"""
        deployment_tag = {
            "tag": deployment_id,
            "tag_visible": visible,
        }
        cls.create_deployment_desktops(deployment_tag, parsed_desktops, users)

        return deployment["id"]

    @classmethod
    def get_unused_deployments(cls):
        """
        Retrieve a list of unused deployments that have not been accessed considering the specified cutoff time in the unused_item_timeout table.

        :return: List of deployments that have not been accessed within the specified cutoff_time.
        :rtype: list
        """
        deployments = []
        start = absolute_start = time.time()

        with cls._rdb_context():
            users_with_deployments = list(
                r.table("deployments")
                .pluck("user")
                .distinct()["user"]
                .run(cls._rdb_connection)
            )

        log.debug(
            "api_deployments get unused desktops: Retrieved users with desktops in %s seconds",
            time.time() - start,
        )

        for user in users_with_deployments:
            start = time.time()
            try:
                payload = Helpers.gen_payload_from_user(user)
                user_timeout_rule = get_unused_item_timeout(
                    payload, "send_unused_deployments_to_recycle_bin"
                )
            except TypeError as e:
                # If the user does not exist then send to the recycle bin all of its deployments
                log.error(
                    "api_deployments get unused deployments: Could not generate payload for user %s",
                    user,
                )
                user_timeout_rule = {"cutoff_time": 0}
                pass

            log.debug(
                "api_deployments get unused desktops: User %s applied rule %s",
                user,
                user_timeout_rule,
            )
            if user_timeout_rule is False or user_timeout_rule["cutoff_time"] is None:
                continue
            cutoff_time = timedelta(days=user_timeout_rule["cutoff_time"] * 30)
            cutoff_timestamp = (datetime.now(timezone.utc) - cutoff_time).timestamp()
            with cls._rdb_context():
                user_deployments = list(
                    r.table("deployments")
                    .get_all(user, index="user")
                    .eq_join("id", r.table("domains"), index="tag")
                    .pluck(
                        {"left": ["id", "user", "name", "co_owners"]},
                        {"right": ["accessed"]},
                    )
                    .group(r.row["left"]["id"])
                    .max(r.row["right"]["accessed"])
                    .ungroup()
                    .filter(
                        lambda row: row["reduction"]["right"]["accessed"]
                        < cutoff_timestamp
                    )
                    .map(
                        lambda row: {
                            "id": row["reduction"]["left"]["id"],
                            "accessed": row["reduction"]["right"]["accessed"],
                            "user": row["reduction"]["left"]["user"],
                            "name": row["reduction"]["left"]["name"],
                            "co_owners": row["reduction"]["left"]["co_owners"],
                        }
                    )
                    .run(cls._rdb_connection)
                )

            log.debug(
                "api_deployments get unused desktops: Retrieved deployments and applied rule in %s seconds",
                time.time() - start,
            )

            deployments += user_deployments

        log.debug(
            "api_deployments get unused deployments: Retrieved users with deployments in %s seconds",
            time.time() - absolute_start,
        )

        return deployments

    @staticmethod
    def deployment_delete_desktops(
        agent_id, desktops_ids, permanent=False, owner_id=None, name=None
    ):
        rcb = RecycleBinDeploymentDesktops(user_id=agent_id)
        rcb.add(desktops_ids, owner_id=owner_id, name=name)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(
            owner_id or agent_id
        )
        if max_time == 0 or permanent:
            rcb.delete_storage(agent_id)

    @classmethod
    def get_unused_deployment_desktops(cls):
        """
        Retrieve cold desktops belonging to deployments, grouped by deployment.

        Unlike ``get_unused_deployments``, this does NOT delete the parent
        deployment: only individual desktops whose ``accessed`` is older than
        the matching rule's cutoff are returned. The deployment row stays
        alive even if every one of its desktops is reaped.

        Rule resolution is keyed on the deployment **creator** (consistent
        with ``send_unused_deployments_to_recycle_bin``), using the op
        ``send_unused_deployment_desktops_to_recycle_bin``. Only desktops
        in ``Stopped``, ``Maintenance`` or ``Failed`` are eligible (mirrors
        ``get_unused_desktops``).

        :return: List of dicts ``{"creator": <user_id>, "deployment_id": <id>,
                 "desktops": [{"id", "user", "name", "accessed"}, ...]}``,
                 one entry per deployment with at least one cold desktop.
        :rtype: list
        """
        result = []

        with cls._rdb_context():
            users_with_deployments = list(
                r.table("deployments")
                .pluck("user")
                .distinct()["user"]
                .run(cls._rdb_connection)
            )

        for user in users_with_deployments:
            try:
                payload = Helpers.gen_payload_from_user(user)
                user_timeout_rule = get_unused_item_timeout(
                    payload, "send_unused_deployment_desktops_to_recycle_bin"
                )
            except TypeError:
                log.error(
                    "api_deployments get unused deployment desktops: Could not generate payload for user %s",
                    user,
                )
                continue

            if user_timeout_rule is False or user_timeout_rule["cutoff_time"] is None:
                continue

            cutoff_time = timedelta(days=user_timeout_rule["cutoff_time"] * 30)
            cutoff_timestamp = (datetime.now(timezone.utc) - cutoff_time).timestamp()

            with cls._rdb_context():
                deployment_ids = list(
                    r.table("deployments")
                    .get_all(user, index="user")["id"]
                    .run(cls._rdb_connection)
                )
                if not deployment_ids:
                    continue
                tag_status_keys = [
                    [d_id, status]
                    for d_id in deployment_ids
                    for status in ("Stopped", "Maintenance", "Failed")
                ]
                cold_desktops = list(
                    r.table("domains")
                    .get_all(r.args(tag_status_keys), index="tag_status")
                    .filter(
                        (r.row["kind"] == "desktop")
                        & (r.row["accessed"] < cutoff_timestamp)
                    )
                    .pluck("id", "user", "name", "accessed", "tag")
                    .run(cls._rdb_connection)
                )

            if not cold_desktops:
                continue

            by_deployment = {}
            for desk in cold_desktops:
                by_deployment.setdefault(desk["tag"], []).append(
                    {
                        "id": desk["id"],
                        "user": desk["user"],
                        "name": desk["name"],
                        "accessed": desk["accessed"],
                    }
                )
            for deployment_id, desktops in by_deployment.items():
                result.append(
                    {
                        "creator": user,
                        "deployment_id": deployment_id,
                        "desktops": desktops,
                    }
                )

        return result

    @classmethod
    def get_deployment_info(cls, deployment_id):
        create_dict = Caches.get_document(
            "deployments", deployment_id, ["create_dict"]
        )[0]
        deployment_data = Caches.get_document("deployments", deployment_id)
        if deployment_data.get("kind") != "desktops":
            raise Error(
                "not_found",
                "Deployment id not found: " + str(deployment_id),
                description_code="not_found",
            )
        create_dict = {
            **create_dict,
            "allowed": deployment_data.get("allowed"),
            "tag": deployment_data.get("tag"),
            "tag_name": deployment_data.get("name"),
            "tag_visible": deployment_data.get("tag_visible"),
            "tag_description": deployment_data.get("description"),
        }
        template = Caches.get_document(
            "domains",
            create_dict["template"],
            ["create_dict", "guest_properties", "image"],
        )

        template["hardware"] = template["create_dict"].pop("hardware")
        template.pop("create_dict")
        template["guest_properties"] = template.pop("guest_properties")
        template["image"] = template.pop("image")
        template.update(create_dict)
        if "isos" in create_dict["hardware"]:
            isos = create_dict["hardware"]["isos"]
            create_dict["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                create_dict["hardware"]["isos"].append(
                    Caches.get_document("media", iso["id"], ["id", "name"])
                )
        if "floppies" in create_dict["hardware"]:
            with cls._rdb_context():
                create_dict["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in create_dict["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(cls._rdb_connection)
                )

        create_dict["hardware"]["interfaces"] = [
            {"id": i, "mac": ""} for i in create_dict["hardware"]["interfaces"]
        ]
        create_dict["hardware"]["memory"] = create_dict["hardware"]["memory"] / 1048576
        create_dict["id"] = deployment_id
        create_dict["allowed"] = Alloweds.get_allowed(create_dict.get("allowed"))
        return create_dict

    @classmethod
    @cached(cache=_validate_tag_desktop_id_for_deployment_cache)
    def validate_tag_desktop_id_for_deployment(
        cls,
        deployment_id: str,
        tag_desktop_id: str,
    ):
        deployment = Caches.get_document("deployments", deployment_id)
        if not deployment:
            raise Error(
                "not_found",
                f"Deployment not found: {deployment_id}",
                traceback.format_exc(),
            )

        existing_tag_desktop_ids = [
            desktop["tag_desktop_id"] for desktop in deployment["create_dict"]
        ]
        if tag_desktop_id not in existing_tag_desktop_ids:
            raise Error(
                "bad_request",
                f"tag_desktop_id {tag_desktop_id} is not from deployment {deployment_id}",
                traceback.format_exc(),
                description_code="invalid_tag_desktop_id_for_deployment",
            )

    @classmethod
    def clear_validate_tag_desktop_id_for_deployment_cache(cls):
        _validate_tag_desktop_id_for_deployment_cache.clear()

    @classmethod
    def validate_tag_desktop_ids_for_deployment(
        cls,
        deployment_id: str,
        tag_desktop_ids: list[str],
    ):
        for tag_desktop_id in tag_desktop_ids:
            cls.validate_tag_desktop_id_for_deployment(deployment_id, tag_desktop_id)

    @classmethod
    def remove_desktops_from_deployment(
        cls,
        payload: dict,
        deployment_id: str,
        tag_desktop_ids_to_delete: list[str],
    ):
        """
        Remove a desktop from a deployment's create_dict_list and delete all
        desktops with the corresponding `tag_desktop_id`
        """
        deployment = Caches.get_document("deployments", deployment_id)
        if not deployment:
            raise Error(
                "not_found",
                f"Deployment not found: {deployment_id}",
                traceback.format_exc(),
            )

        cls.validate_tag_desktop_ids_for_deployment(
            deployment_id, tag_desktop_ids_to_delete
        )

        with cls._rdb_context():
            r.table("deployments").get(deployment_id).update(
                {
                    "create_dict": r.row["create_dict"].filter(
                        lambda desktop: (
                            ~r.expr(tag_desktop_ids_to_delete).contains(
                                desktop["tag_desktop_id"]
                            )
                        )
                    )
                }
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("deployments", deployment_id)

        with cls._rdb_context():
            domains_to_delete = list(
                r.table("domains")
                .get_all(r.args(tag_desktop_ids_to_delete), index="tag_desktop_id")
                .pluck("id")["id"]
                .run(cls._rdb_connection)
            )

        DesktopEvents.deployment_delete_desktops(
            agent_id=payload["user_id"],
            desktops_ids=domains_to_delete,
            permanent=True,
        )

    @classmethod
    def merge_new_data_with_deployment(cls, create_dict, new_data):
        """

        Parse and merge new_data with the deployment's create_dict and guest_properties.
        This is used when editing a deployment's desktops,
        allowing to override specific fields such as hardware, reservables, and guest_properties.
        :param deployment_id: The ID of the deployment to inherit from.
        :param new_data: A dictionary containing the new data to merge with the deployment.
        :return: A tuple containing the merged create_dict and guest_properties.

        """

        merged_create_dict = copy.deepcopy(create_dict)
        guest_properties = copy.deepcopy(merged_create_dict.pop("guest_properties", {}))

        # Memory must be in MB, transform it from bytes to MB when inheriting from template
        if merged_create_dict["hardware"].get("memory"):
            merged_create_dict["hardware"]["memory"] = float(
                create_dict["hardware"]["memory"] / 1048576
            )

        # If new_data is provided, we need to update the deployment with the new data
        if new_data and (
            new_data.get("hardware")
            or new_data.get("reservables")
            or new_data.get("guest_properties")
            or new_data.get("name") is not None
            or new_data.get("description") is not None
        ):
            # The deployment's create_dict is also the source of truth the
            # edit form re-loads from via /info → it must reflect the
            # latest desktop name and description, not just hardware.
            if new_data.get("name") is not None:
                merged_create_dict["name"] = new_data["name"]
            if new_data.get("description") is not None:
                merged_create_dict["description"] = new_data["description"]
            if new_data.get("hardware"):
                # If hardware is provided, we need to update the template with the new data
                merged_create_dict["hardware"].update(new_data["hardware"])
                if new_data["hardware"].get("isos") or new_data["hardware"].get(
                    "floppies"
                ):
                    merged_create_dict = Helpers._parse_media_info(merged_create_dict)

            if new_data.get("reservables"):
                # If reservables are provided, update them at create_dict level
                merged_create_dict["reservables"] = new_data["reservables"]

            # If new_data contains guest_properties, merge only the provided keys
            if new_data.get("guest_properties"):
                guest_properties.update(new_data["guest_properties"])
                guest_properties["viewers"] = new_data["guest_properties"]["viewers"]
        return merged_create_dict, guest_properties

    @classmethod
    def edit_deployment_desktops(
        cls,
        payload: dict,
        deployment_id: str,
        desktops_data: list[dict],
    ):
        """
        Edit a deployment's desktops by it's tag_desktop_ids
        """
        if not Caches.get_document("deployments", deployment_id):
            raise Error(
                "not_found",
                f"Deployment not found: {deployment_id}",
                traceback.format_exc(),
            )

        cls.validate_tag_desktop_ids_for_deployment(
            deployment_id,
            [desktop["tag_desktop_id"] for desktop in desktops_data],
        )

        with cls._rdb_context():
            create_dicts = list(
                r.table("deployments")
                .get(deployment_id)
                .pluck("create_dict")["create_dict"]
                .run(cls._rdb_connection)
            )

        deployment_create_dict_object = {
            desktop["tag_desktop_id"]: desktop for desktop in create_dicts
        }

        for i, desktop_data in enumerate(desktops_data):
            # Search the create_dicts with the tag_desktop_id
            create_dict = deployment_create_dict_object[desktop_data["tag_desktop_id"]]
            # Beware that deployments are different to domains, and the guest_properties are merged inside the create_dict
            (
                deployment_create_dict_object[desktop_data["tag_desktop_id"]],
                deployment_create_dict_object[desktop_data["tag_desktop_id"]][
                    "guest_properties"
                ],
            ) = cls.merge_new_data_with_deployment(create_dict, desktop_data)
            limited_hardware = Quotas.limit_user_hardware_allowed(
                payload, deployment_create_dict_object[desktop_data["tag_desktop_id"]]
            )["limited_hardware"]
            if limited_hardware:
                raise Error(
                    "bad_request",
                    "The following hardware cannot be used due to permissions: "
                    + str(limited_hardware),
                )
            # Convert the memory to bytes. Must be after the limit hardware since the quota is checked in GB
            deployment_create_dict_object[desktop_data["tag_desktop_id"]]["hardware"][
                "memory"
            ] = int(
                deployment_create_dict_object[desktop_data["tag_desktop_id"]][
                    "hardware"
                ]["memory"]
                * 1048576
            )

        with cls._rdb_context():
            r.table("deployments").get(deployment_id).update(
                DeploymentUpdateModel(
                    create_dict=deployment_create_dict_object.values(),
                ).model_dump(mode="json", exclude_unset=True)
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("deployments", deployment_id)

        deployment_create_dict_object = {
            desktop["tag_desktop_id"]: desktop for desktop in create_dicts
        }
        for desktop_data in desktops_data:
            # Each deployment desktop owns its derived disk; the deployment
            # create_dict carries the template's own storage_id, so never let
            # it overwrite the domain's disk or deleting the deployment would
            # delete the template's storage.
            desktop_data.get("hardware", {}).pop("disks", None)
            # If the networks have changed new macs should be generated for each domain
            if (
                desktop_data.get("hardware", {}).get("interfaces")
                and deployment_create_dict_object[desktop_data["tag_desktop_id"]][
                    "hardware"
                ]["interfaces"]
                != desktop_data["hardware"]["interfaces"]
            ):
                with cls._rdb_context():
                    desktop_ids = list(
                        r.table("domains")
                        .get_all(
                            [deployment_id, desktop_data["tag_desktop_id"]],
                            index="tag_tag_desktop_id",
                        )
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
                # Parse the domain interfaces to have the macs generated
                DesktopsProcessed.update_desktop(
                    desktop_ids,
                    desktop_data,
                    bulk=True,
                )

            # Otherwise the rest of the hardware can be updated at once
            else:
                # If interfaces are present but not changed, remove them from the update
                # Since in domains is stored with macs and in deployments not
                if "interfaces" in desktop_data.get("hardware", {}):
                    desktop_data["hardware"].pop("interfaces")
                with cls._rdb_context():
                    # ``hardware`` is optional — the legacy apiv3 flat
                    # edit fan-out in apiv4's ``update_deployment``
                    # builds entries with only the fields the caller
                    # provided (``name``, ``desktop_visible``, etc.),
                    # so unconditionally indexing ``desktop_data["hardware"]``
                    # would KeyError on a vanilla rename.
                    r.table("domains").get_all(
                        [deployment_id, desktop_data["tag_desktop_id"]],
                        index="tag_tag_desktop_id",
                    ).update(
                        DomainUpdateModel(
                            **(
                                {
                                    "create_dict": {
                                        "reservables": desktop_data.pop("reservables"),
                                    }
                                }
                                if desktop_data.get("reservables")
                                else {}
                            ),
                            **(
                                {
                                    "create_dict": {
                                        "hardware": desktop_data["hardware"],
                                    }
                                }
                                if desktop_data.get("hardware")
                                else {}
                            ),
                            **desktop_data,
                        ).model_dump(mode="json", exclude_unset=True)
                    ).run(
                        cls._rdb_connection
                    )

                if desktop_data.get("guest_properties"):
                    with cls._rdb_context():
                        r.table("domains").get_all(
                            [deployment_id, desktop_data["tag_desktop_id"]],
                            index="tag_tag_desktop_id",
                        ).update(
                            {
                                "guest_properties": r.literal(
                                    desktop_data["guest_properties"]
                                )
                            }
                        ).run(
                            cls._rdb_connection
                        )

    @classmethod
    def add_desktops_to_deployment(
        cls,
        payload: dict,
        deployment_id: str,
        desktops: list[dict],
    ):
        """
        Add new desktops to an existing deployment's create_dict list
        """
        if not Caches.get_document("deployments", deployment_id):
            raise Error(
                "not_found",
                f"Deployment not found: {deployment_id}",
                traceback.format_exc(),
            )

        for desktop in desktops:
            desktop["tag_desktop_id"] = str(uuid.uuid4())

        parsed_desktops = []
        # TODO: Unify with create deployment code
        for desktop in desktops:
            desktop = copy.deepcopy(desktop)

            template = Caches.get_document("domains", desktop["template_id"])
            if not template:
                raise Error(
                    "not_found",
                    "Template not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )

            TemplatesProcessed.check_template_status(None, template)
            if not Alloweds.is_allowed(payload, template, "domains"):
                raise Error(
                    "forbidden",
                    "User not allowed to use this template",
                    description_code="template_not_allowed",
                )

            desktop["description"] = (
                desktop.get("description") or template["description"]
            )
            desktop["image"] = desktop.get("image") or template["image"]

            DesktopViewers.check_new_desktop_viewers(desktop, template)

            create_dict, guest_properties = (
                DesktopsProcessed.merge_new_data_with_template(
                    desktop["template_id"], desktop
                )
            )

            try:
                create_dict = Helpers._parse_media_info(create_dict)
            except Exception:
                raise Error(
                    "internal_server",
                    "new_from_template: unable to parse media info.",
                    description_code="unable_to_parse_media",
                )
            limited_hardware = Quotas.limit_user_hardware_allowed(payload, create_dict)[
                "limited_hardware"
            ]
            if limited_hardware:
                raise Error(
                    "bad_request",
                    "The following hardware cannot be used due to permissions: "
                    + str(limited_hardware),
                )
            desktop.update(
                {
                    "hardware": create_dict["hardware"],
                    "reservables": create_dict.get("reservables"),
                    "guest_properties": guest_properties,
                }
            )

            parsed_desktops.append(desktop)

        # Check the parsed desktops reservables, all of them must be the same, ignoring the ones that have the field vgpus as None
        # ``reservables`` itself is Optional on ``CreateDesktopRequest`` —
        # Vue 3 deployments without a GPU pin omit the key entirely, so
        # the entry is ``None``. Treat that as "no vgpus" rather than
        # crashing with ``NoneType.get``.
        valid_vgpus = [
            tuple((d.get("reservables") or {}).get("vgpus"))
            for d in parsed_desktops
            if (d.get("reservables") or {}).get("vgpus") is not None
        ]
        if valid_vgpus and any(v != valid_vgpus[0] for v in valid_vgpus):
            raise Error(
                "precondition_required",
                "Deployment reservables are not equal across all desktops.",
                description_code="deployment_reservables_not_equal",
            )

        with cls._rdb_context():
            deployment = (
                r.table("deployments").get(deployment_id).run(cls._rdb_connection)
            )

        create_dict_list = deployment["create_dict"] + [
            {
                "description": desktop["description"],
                "hardware": {
                    **desktop["hardware"],
                    # Must be in bytes for the deployment creation. When creating desktops its in MiB and will be converted later
                    "memory": desktop["hardware"]["memory"] * 1048576,
                },
                "reservables": desktop["reservables"],
                "guest_properties": desktop["guest_properties"],
                "name": desktop["name"],
                "template": desktop["template_id"],
                "image": desktop["image"],
                "tag_desktop_id": desktop["tag_desktop_id"],
            }
            for desktop in parsed_desktops
        ]

        for desktop in parsed_desktops:

            # Check the desktop names
            DeploymentUsers.get_selected_users(
                payload,
                deployment["allowed"],
                desktop["name"],
                deployment_id=None,
                existing_desktops_error=True,
            )

        # Get the users
        users = DeploymentUsers.get_selected_users(
            payload,
            deployment["allowed"],
            "",
            deployment_id=None,
            existing_desktops_error=False,
            include_existing_desktops=True,
        )

        # TODO: check if quantity=0 works, else create `deployment_add` function to only check deployment desktops quota
        Quotas.deployment_create(
            owner_id=payload["user_id"],
            quantity=0,
            desktops_len=len(desktops),
            users=users,
        )

        """Create deployment"""
        with cls._rdb_context():
            r.table("deployments").get(deployment_id).update(
                DeploymentUpdateModel(
                    create_dict=create_dict_list,
                ).model_dump(mode="json", exclude_unset=False)
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("deployments", deployment_id)

        """Create desktops for each user found"""
        deployment_tag = {
            "tag": deployment_id,
            "tag_visible": deployment["tag_visible"],
        }
        cls.create_deployment_desktops(deployment_tag, desktops, users)

        return deployment["id"]

    @classmethod
    def edit_deployment_data(cls, payload: dict, deployment_id: str, data: dict):
        """
        Edit the deployment data without modifying it's desktops
        """
        deployment = Caches.get_document("deployments", deployment_id)
        if not deployment:
            raise Error(
                "not_found",
                f"Deployment not found: {deployment_id}",
                traceback.format_exc(),
            )

        if "allowed" in data:
            alloweds = data.pop("allowed")
            DeploymentUsers.edit_deployment_users(
                payload=payload,
                deployment_id=deployment_id,
                allowed=alloweds,
            )
            cls.recreate(payload, deployment_id)

        with cls._rdb_context():
            r.table("deployments").get(deployment_id).update(
                DeploymentUpdateModel(**data).model_dump(
                    mode="json", exclude_unset=True
                )
            ).run(cls._rdb_connection)
        Caches.invalidate_cache("deployments", deployment_id)

        if "visible" in data:
            with cls._rdb_context():
                r.table("domains").get_all(deployment_id, index="tag").update(
                    {"tag_visible": data["visible"]}
                ).run(cls._rdb_connection)
