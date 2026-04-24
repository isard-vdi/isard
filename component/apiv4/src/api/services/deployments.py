#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

import traceback
from uuid import uuid4

import requests
from api.dependencies.jwt_token import TokenPayload
from api.services.desktops import DesktopService
from api.services.error import Error
from cachetools import TTLCache, cached
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed as CommonDeploymentDesktops,
)
from isardvdi_common.lib.deployments.deployment_direct_viewer import (
    DeploymentDirectViewer as CommonDeploymentDirectViewer,
)
from isardvdi_common.lib.deployments.deployment_users import (
    DeploymentUsers as CommonDeploymentUsers,
)
from isardvdi_common.lib.deployments.deployments import (
    DeploymentsProcessed as CommonDeployments,
)
from isardvdi_common.models.deployment import Deployment as RethinkDeployment
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.user import User as RethinkUser

deployment_cache = TTLCache(maxsize=1, ttl=360)


class DeploymentService:
    @staticmethod
    @cached(cache=deployment_cache)
    def get_all_deployments():
        return RethinkDeployment.get_all()

    @staticmethod
    def get_owned_deployments(user_payload):
        deployments = CommonDeployments.get_owned_deployments(
            user_payload
        ) + CommonDeployments.get_co_owned_deployments(user_payload)
        return deployments

    @staticmethod
    def get_deployment(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        deployment = CommonDeployments.retrieve_deployment(deployment_id)
        users = CommonDeploymentUsers.get_users_info(deployment_id)
        deployment["total_users"] = len(users)
        deployment["total_desktops"] = (
            len(deployment["create_dict"]) * deployment["total_users"]
        )
        deployment["desktops_each_user"] = len(deployment["create_dict"])
        return {"info": deployment, "users": users}

    @staticmethod
    def delete_deployment(
        deployment_id: str, user_id: str = None, permanent: bool = False
    ) -> bool | str:
        return DesktopEvents.deployment_delete(
            deployment_id=deployment_id, agent_id=user_id, permanent=permanent
        )

    @staticmethod
    def create_deployment(data, payload) -> str:
        deployment_id = CommonDeployments.create(
            payload=payload,
            name=data["name"],
            description=data.get("description"),
            selected=data["allowed"],
            desktops=data["desktops"],
            co_owners=data.get("co_owners", []),
            visible=data.get("visible", False),
            user_permissions=data.get("user_permissions", []),
            image=data.get("image"),
            create_owner_desktop=data.get("create_owner_desktop", True),
        )

        return deployment_id

    @staticmethod
    def toggle_visibility(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        deployment = RethinkDeployment(deployment_id)
        deployment.tag_visible = not deployment.tag_visible
        deployment_cache.clear()
        return deployment_id

    @staticmethod
    def update_deployment(
        payload: TokenPayload, deployment_id: str, deployment_data: dict
    ):
        if deployment_data.get("name"):
            Helpers.check_duplicate(
                "deployments",
                deployment_data["name"],
                user=payload["user_id"],
                item_id=deployment_id,
            )

        # Creation and edition could lead to permission errors
        # so we handle them first to avoid removing desktops and then failing
        if deployment_data.get("desktops_to_create"):
            ## Create and add new desktops
            CommonDeployments.add_desktops_to_deployment(
                payload,
                deployment_id,
                deployment_data.pop("desktops_to_create"),
            )
        if deployment_data.get("desktops_to_edit"):
            ## Edit desktops with tag_desktop_id
            CommonDeployments.edit_deployment_desktops(
                payload,
                deployment_id,
                deployment_data.pop("desktops_to_edit"),
            )

        if deployment_data.get("desktops_to_delete"):
            if (
                len(deployment_data["desktops_to_delete"])
                >= len(
                    Caches.get_document(
                        "deployments",
                        deployment_id,
                    )["create_dict"]
                )
            ) and not deployment_data.get("desktops_to_create"):
                raise Error(
                    "bad_request",
                    "Cannot delete all desktops from deployment. At least one desktop must remain.",
                )

            ## Delete desktops with tag_desktop_id
            CommonDeployments.remove_desktops_from_deployment(
                payload,
                deployment_id,
                deployment_data.pop("desktops_to_delete"),
            )

        CommonDeployments.edit_deployment_data(
            payload,
            deployment_id,
            deployment_data,
        )

    @staticmethod
    def recreate_desktops(payload, deployment_id):
        """
        Recreate all desktops for a deployment with updated parameters.
        This involves deleting existing desktops and creating new ones.

        Args:
            payload: The token payload of the requesting user
            deployment_id: The ID of the deployment

        Returns:
            str: The deployment ID
        """
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )

        deployment = RethinkDeployment(deployment_id)
        desktops_to_delete = CommonDeploymentDesktops.get_with_tag_dict(deployment.tag)

        for desktop in desktops_to_delete:
            RethinkDomain.delete(desktop["id"])

        CommonDeployments.recreate(payload, deployment_id)

        deployment_cache.clear()
        return deployment_id

    @staticmethod
    def stop_all_desktops(deployment_id: str):
        desktops = CommonDeploymentDesktops.get_desktop_ids(deployment_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found in deployment {deployment_id}.",
                traceback.format_exc(),
            )

        DesktopEvents.desktops_stop(desktops)

    @staticmethod
    def stop_user_desktops(deployment_id: str, user_id: str):
        desktops = CommonDeploymentDesktops.get_user_desktop_ids(deployment_id, user_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found for user {user_id} in deployment {deployment_id}.",
                traceback.format_exc(),
            )

        DesktopEvents.desktops_stop(desktops)

    @staticmethod
    def get_shared_deployments(user_payload):
        deployments = CommonDeployments.get_shared_deployments(user_payload)
        return deployments

    @staticmethod
    def get_deployment_user_desktops(deployment_id, user_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} does not exist.",
            )
        # Check if the user belongs to the deployment
        if user_id not in CommonDeploymentUsers.get_users(deployment_id):
            raise Error(
                "forbidden",
                f"User with ID {user_id} does not belong to deployment {deployment_id}.",
            )
        user_deployment = {
            "info": CommonDeployments.retrieve_user_deployment(deployment_id, user_id),
            "desktops": CommonDeploymentDesktops.get_deployment_user_desktops(
                deployment_id, user_id
            ),
        }
        for desktop in user_deployment["desktops"]:
            desktop["viewers"] = (
                desktop.get("guest_properties", {}).get("viewers", {}).keys()
            )
            del desktop["guest_properties"]["viewers"]
        return user_deployment

    @staticmethod
    def get_deployment_user_desktops_detail(deployment_id, user_id):
        user_desktops = CommonDeploymentDesktops.get_deployment_user_desktops(
            deployment_id, user_id
        )
        return [
            DesktopService.get_desktop_details(desktop["id"])
            for desktop in user_desktops
        ]

    @staticmethod
    def get_deployment_videowall(deployment_id):
        return CommonDeployments.get_deployment(
            deployment_id=deployment_id,
            desktops=True,
        )

    @staticmethod
    def check_quota(user_id, users=None):
        from isardvdi_common.helpers.quotas import Quotas

        Quotas.deployment_create(user_id, 1, None, users or None)

    @staticmethod
    def get_selected_users(payload, allowed):
        return CommonDeploymentUsers.get_selected_users(payload, allowed)

    @staticmethod
    def bulk_delete_deployments(deployment_ids, user_id, permanent=False):
        for d_id in deployment_ids:
            DesktopEvents.deployment_delete(
                deployment_id=d_id, agent_id=user_id, permanent=permanent
            )

    @staticmethod
    def start_all_desktops(deployment_id):
        desktops = CommonDeploymentDesktops.get_desktop_ids(deployment_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found in deployment {deployment_id}.",
                traceback.format_exc(),
            )
        DesktopEvents.desktops_start(desktops)

    @staticmethod
    def toggle_domain_visibility(domain_id):
        if not RethinkDomain.exists(domain_id):
            raise Error(
                "not_found",
                f"Domain with ID {domain_id} does not exist.",
            )
        RethinkDomain(domain_id).toggle_user_visible()

    @staticmethod
    def get_deployment_hardware(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_deployment_details_hardware()

    @staticmethod
    def get_deployment_info(deployment_id, payload):
        from isardvdi_common.helpers.quotas import Quotas

        deployment = CommonDeployments.get_deployment_info(
            deployment_id=deployment_id,
        )
        deployment = Quotas.limit_user_hardware_allowed(payload, deployment)
        return deployment

    @staticmethod
    def get_co_owners(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_co_owners().get("co_owners", [])

    @staticmethod
    def update_co_owners(deployment_id, co_owners):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        RethinkDeployment(deployment_id).update_co_owners(co_owners)

    @staticmethod
    def change_owner(payload, deployment_id, user_id):
        CommonDeployments.change_owner_deployment(payload, deployment_id, user_id)

    @staticmethod
    def get_permissions(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_deployment_permissions()

    @staticmethod
    def edit_deployment_users(payload, deployment_id, allowed):
        """Edit the allowed users/groups of a deployment.

        Updates the deployment's allowed list, deletes desktops for removed
        users, and recreates desktops for the new user set.
        """
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        # Strip categories and roles — deployments only allow by users/groups
        allowed.pop("categories", None)
        allowed.pop("roles", None)
        CommonDeploymentUsers.edit_deployment_users(payload, deployment_id, allowed)

    @staticmethod
    def check_desktops_started(deployment_id):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        RethinkDeployment(deployment_id).check_desktops_started()

    @staticmethod
    def delete_desktops(user_id, deployment_id, request):
        """
        Delete all desktops belonging to a specific user in a deployment.

        Args:
            user_id: The ID of the user
            deployment_id: The ID of the deployment (used as tag)
            request: The FastAPI request object for headers

        Returns:
            list[str]: List of storage-delete task IDs the client can track.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        desktops = CommonDeploymentDesktops.get_deployment_user_desktops(
            deployment_id, user_id
        )

        if not desktops:
            return []

        task_ids: list[str] = []

        for desktop in desktops:
            try:
                tasks = DesktopService.delete_desktop(
                    desktop["id"], user_id=user_id, permanent=True
                )
                if isinstance(tasks, list):
                    task_ids.extend(
                        t["id"] for t in tasks if isinstance(t, dict) and "id" in t
                    )
            except Exception:
                pass  # best-effort deletion
        deployment_cache.clear()

        return task_ids

    @staticmethod
    def direct_viewer_csv(deployment_id, regenerate=False):
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return CommonDeploymentDirectViewer.direct_viewer_csv(
            deployment_id, regenerate=regenerate
        )
