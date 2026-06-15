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

import csv
import io
import logging
import os
import traceback
from uuid import uuid4

import requests
from api.dependencies.jwt_token import TokenPayload
from api.services.bastion import BastionService
from api.services.desktops import DesktopService
from api.services.error import Error
from cachetools import TTLCache, cached
from fastapi import Request
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
from isardvdi_common.models.targets import Targets
from isardvdi_common.models.user import User as RethinkUser

deployment_cache = TTLCache(maxsize=1, ttl=360)


class DeploymentService:
    @staticmethod
    @cached(cache=deployment_cache)
    def get_all_deployments() -> list[dict]:
        return RethinkDeployment.get_all()

    @staticmethod
    def get_owned_deployments(user_payload: dict) -> list[dict]:
        deployments = CommonDeployments.get_owned_deployments(
            user_payload
        ) + CommonDeployments.get_co_owned_deployments(user_payload)
        return deployments

    @staticmethod
    def get_deployment(deployment_id: str) -> dict:
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
    def create_deployment(data: dict, payload: dict) -> str:
        allowed = dict(data.get("allowed") or {})
        for _k in ("groups", "users", "categories", "roles"):
            allowed.setdefault(_k, False)

        deployment_id = CommonDeployments.create(
            payload=payload,
            name=data["name"],
            description=data.get("description"),
            selected=allowed,
            desktops=data["desktops"],
            co_owners=data.get("co_owners", []),
            visible=data.get("visible", False),
            user_permissions=data.get("user_permissions", []),
            image=data.get("image"),
            create_owner_desktop=data.get("create_owner_desktop", True),
        )

        return deployment_id

    @staticmethod
    def toggle_visibility(deployment_id: str, stop_started_domains: bool = True) -> str:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        # Use the model method, not the property setter: the property setter
        # only flips the deployment row's `tag_visible`, while toggle_visible
        # also cascades the new value to every tagged desktop (all-or-none
        # per deployment, via the `tag` index — independent of `tag_desktop_id`)
        # and optionally stops Started desktops when going invisible.
        RethinkDeployment(deployment_id).toggle_visible(stop_started_domains)
        deployment_cache.clear()
        return deployment_id

    @staticmethod
    def update_deployment(
        payload: TokenPayload, deployment_id: str, deployment_data: dict
    ) -> None:
        if deployment_data.get("name"):
            Helpers.check_duplicate(
                "deployments",
                deployment_data["name"],
                user=payload["user_id"],
                item_id=deployment_id,
            )

        # Translate the apiv3 flat-shape fields (sent by old-frontend)
        # into a desktops_to_edit list so the rest of the service runs
        # the same code path for both client versions.
        legacy_desktop_name = deployment_data.pop("desktop_name", None)
        legacy_desktop_description = deployment_data.pop("desktop_description", None)
        legacy_hardware = deployment_data.pop("hardware", None)
        legacy_guest_properties = deployment_data.pop("guest_properties", None)
        if (
            legacy_desktop_name is not None
            or legacy_desktop_description is not None
            or legacy_hardware is not None
            or legacy_guest_properties is not None
        ):
            if not deployment_data.get("desktops_to_edit"):
                deployment = Caches.get_document("deployments", deployment_id)
                if deployment:
                    fanout_template = {}
                    if legacy_desktop_name is not None:
                        fanout_template["name"] = legacy_desktop_name
                    if legacy_desktop_description is not None:
                        fanout_template["description"] = legacy_desktop_description
                    if legacy_hardware is not None:
                        fanout_template["hardware"] = legacy_hardware
                    if legacy_guest_properties is not None:
                        fanout_template["guest_properties"] = legacy_guest_properties
                    deployment_data["desktops_to_edit"] = [
                        {**fanout_template, "tag_desktop_id": cd["tag_desktop_id"]}
                        for cd in deployment.get("create_dict", [])
                        if cd.get("tag_desktop_id")
                    ]

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

        # invalidate cache
        Caches.invalidate_cache("deployments", deployment_id)

    @staticmethod
    def recreate_desktops(payload: dict, deployment_id: str) -> str:
        """
        Recreate a deployment by creating the desktops that are missing
        for its currently allowed users.

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

        CommonDeployments.recreate(payload, deployment_id)

        deployment_cache.clear()
        return deployment_id

    @staticmethod
    def stop_all_desktops(deployment_id: str) -> None:
        desktops = CommonDeploymentDesktops.get_desktop_ids(deployment_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found in deployment {deployment_id}.",
                traceback.format_exc(),
            )

        DesktopEvents.desktops_stop(desktops)

    @staticmethod
    def stop_user_desktops(deployment_id: str, user_id: str) -> None:
        desktops = CommonDeploymentDesktops.get_user_desktop_ids(deployment_id, user_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found for user {user_id} in deployment {deployment_id}.",
                traceback.format_exc(),
            )

        DesktopEvents.desktops_stop(desktops)

    @staticmethod
    def get_shared_deployments(user_payload: dict) -> list[dict]:
        deployments = CommonDeployments.get_shared_deployments(user_payload)
        return deployments

    @staticmethod
    def get_deployment_user_desktops(deployment_id: str, user_id: str) -> dict:
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
            # ``guest_properties.viewers`` keys are the underscored DB form
            # (``browser_vnc`` / ``file_spice`` / ...). The Pydantic
            # response model (``UserDeploymentDesktop``) hyphenates on
            # output via ``_hyphenate_viewers_for_clients`` so old- and
            # new-frontend i18n lookups resolve.
            viewers = (desktop.get("guest_properties") or {}).get("viewers") or {}
            desktop["viewers"] = list(viewers.keys())
            if "guest_properties" in desktop and "viewers" in (
                desktop["guest_properties"] or {}
            ):
                del desktop["guest_properties"]["viewers"]
        return user_deployment

    @staticmethod
    def get_deployment_user_desktops_detail(
        deployment_id: str, user_id: str
    ) -> list[dict]:
        user_desktops = CommonDeploymentDesktops.get_deployment_user_desktops(
            deployment_id, user_id
        )
        return [
            DesktopService.get_desktop_details(desktop["id"])
            for desktop in user_desktops
        ]

    @staticmethod
    def get_deployment_videowall(deployment_id: str) -> dict:
        deployment = CommonDeployments.get_deployment(
            deployment_id=deployment_id,
            desktops=True,
        )
        # Enrich with counts that the detail-page consumers (old-frontend
        # Deployment.vue, recreate confirmation) compute from. Mirrors the
        # same fields the wrapped /item/deployment/{id} response builds in
        # `get_deployment` so a single videowall fetch is enough.
        users = CommonDeploymentUsers.get_users_info(deployment_id)
        deployment["total_users"] = len(users)
        deployment["desktops_each_user"] = (
            len(deployment.get("desktops", []))
            and (
                # On a deployment with desktops, divide actual desktops by users
                # to derive the per-user multiplier; falls back to 1 when there
                # are no desktops yet so the recreate count is `total_users`.
                max(1, len(deployment["desktops"]) // max(1, len(users)))
            )
            or 1
        )
        deployment["total_desktops"] = (
            deployment["total_users"] * deployment["desktops_each_user"]
        )
        return deployment

    @staticmethod
    def check_quota(user_id: str, users: list[dict] | None = None) -> None:
        from isardvdi_common.helpers.quotas import Quotas

        Quotas.deployment_create(user_id, 1, None, users or None)

    @staticmethod
    def get_selected_users(payload: dict, allowed: dict) -> list[dict]:
        return CommonDeploymentUsers.get_selected_users(payload, allowed)

    @staticmethod
    def bulk_delete_deployments(
        deployment_ids: list[str], user_id: str, permanent: bool = False
    ) -> None:
        for d_id in deployment_ids:
            DesktopEvents.deployment_delete(
                deployment_id=d_id, agent_id=user_id, permanent=permanent
            )

    @staticmethod
    def start_all_desktops(deployment_id: str, user_id=None) -> None:
        desktops = CommonDeploymentDesktops.get_desktop_ids(deployment_id)
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found in deployment {deployment_id}.",
                traceback.format_exc(),
            )
        DesktopEvents.desktops_start(desktops)
        # Best-effort: reconcile each desktop's bastion target to the deployment
        # config and inject the deployment owner + co-owners (+ acting user)
        # profile keys, owner-first and de-duped. ensure_keys_on_start resolves
        # the deployment from the desktop, so this runs even without user_id.
        for d_id in desktops:
            try:
                BastionService.ensure_keys_on_start(d_id, user_id)
            except Exception:
                logging.warning(
                    "Failed to inject bastion SSH key on deployment start "
                    "of desktop %s",
                    d_id,
                    exc_info=True,
                )

    @staticmethod
    def toggle_domain_visibility(domain_id: str) -> None:
        if not RethinkDomain.exists(domain_id):
            raise Error(
                "not_found",
                f"Domain with ID {domain_id} does not exist.",
            )
        domain = RethinkDomain(domain_id)
        # ``RethinkDomain.toggle_user_visible`` raises a plain
        # ``ValueError`` when the desktop has no tag; the route's
        # ``except Exception`` then surfaces it as a generic 500.
        # Pre-check at the service layer so a wrong-button click goes
        # to a typed 400 instead.
        if not domain.tag:
            raise Error(
                "bad_request",
                "Desktop is not part of a deployment; visibility toggle does not apply.",
                description_code="not_in_deployment",
            )
        domain.toggle_user_visible()

    @staticmethod
    def get_deployment_hardware(deployment_id: str) -> dict:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_deployment_details_hardware()

    @staticmethod
    def get_deployment_info(deployment_id: str, payload: dict) -> dict:
        from isardvdi_common.helpers.quotas import Quotas

        deployment = CommonDeployments.get_deployment_info(
            deployment_id=deployment_id,
        )
        deployment = Quotas.limit_user_hardware_allowed(payload, deployment)
        return deployment

    @staticmethod
    def get_co_owners(deployment_id: str) -> dict:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_co_owners()

    @staticmethod
    def update_co_owners(deployment_id: str, co_owners: list[str]) -> None:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        RethinkDeployment(deployment_id).update_co_owners(co_owners)

    @staticmethod
    def change_owner(payload: dict, deployment_id: str, user_id: str) -> None:
        CommonDeployments.change_owner_deployment(payload, deployment_id, user_id)

    @staticmethod
    def get_permissions(deployment_id: str) -> list[str]:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return RethinkDeployment(deployment_id).get_deployment_permissions()

    @staticmethod
    def edit_deployment_users(payload: dict, deployment_id: str, allowed: dict) -> None:
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
    def check_desktops_started(deployment_id: str) -> None:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        RethinkDeployment(deployment_id).check_desktops_started()

    @staticmethod
    def delete_desktops(
        user_id: str, deployment_id: str, request: Request
    ) -> list[str]:
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
    def direct_viewer_csv(deployment_id: str, regenerate: bool = False) -> str:
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        return CommonDeploymentDirectViewer.direct_viewer_csv(
            deployment_id, regenerate=regenerate
        )

    # ── Deployment bastion ───────────────────────────────────────────────

    @staticmethod
    def _default_bastion_config() -> dict:
        return {
            "ssh": {"enabled": False, "port": 22},
            "http": {"enabled": False, "http_port": 80, "https_port": 443},
        }

    @staticmethod
    def get_deployment_bastion(deployment_id: str) -> dict:
        """Return the deployment-level bastion config (or defaults)."""
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        deployment = Caches.get_document("deployments", deployment_id)
        return (deployment or {}).get(
            "bastion"
        ) or DeploymentService._default_bastion_config()

    @staticmethod
    def set_deployment_bastion(deployment_id: str, config: dict) -> dict:
        """Persist the bastion config on the deployment and apply it (ssh/http
        enable + ports) to every current desktop's bastion target, preserving
        each target's authorized_keys / domains. New/recreated desktops inherit
        it at their next start via BastionService.ensure_keys_on_start.
        """
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        normalized = {
            "ssh": {
                "enabled": bool(config.get("ssh", {}).get("enabled")),
                "port": int(config.get("ssh", {}).get("port", 22)),
            },
            "http": {
                "enabled": bool(config.get("http", {}).get("enabled")),
                "http_port": int(config.get("http", {}).get("http_port", 80)),
                "https_port": int(config.get("http", {}).get("https_port", 443)),
            },
        }
        RethinkDeployment.update_document(deployment_id, {"bastion": normalized})
        Caches.invalidate_cache("deployments", deployment_id)
        for desktop_id in CommonDeploymentDesktops.get_desktop_ids(deployment_id):
            try:
                BastionService.apply_bastion_config(desktop_id, normalized)
            except Exception:
                logging.warning(
                    "Failed to apply deployment bastion config to desktop %s",
                    desktop_id,
                    exc_info=True,
                )
        return normalized

    @staticmethod
    def get_deployment_desktop_bastion(deployment_id: str, desktop_id: str) -> dict:
        """Read-only bastion status of a single deployment desktop, for the
        owner/co-owner per-row view. Verifies the desktop belongs to the
        deployment (``domains.tag == deployment_id``) before returning data, so
        a co-owner (who is not the desktop owner) cannot read arbitrary targets.
        """
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        try:
            tag = Caches.get_document("domains", desktop_id, ["tag"])
        except ValueError:
            tag = None
        if tag != deployment_id:
            raise Error(
                "forbidden",
                "Desktop does not belong to this deployment",
                description_code="forbidden",
            )
        return BastionService.get_desktop_bastion_active(desktop_id)

    @staticmethod
    def bastion_csv(deployment_id: str) -> str:
        """Build a CSV of every deployment desktop's bastion connection info
        (no key material). One row per desktop.
        """
        if not RethinkDeployment.exists(deployment_id):
            raise Error(
                "not_found",
                f"Deployment with ID {deployment_id} does not exist.",
            )
        cfg = BastionService.get_admin_bastion_config()
        bastion_domain = cfg.get("bastion_domain")
        ssh_port = cfg.get("bastion_ssh_port")

        fieldnames = [
            "username",
            "email",
            "desktop_name",
            "status",
            "target_id",
            "ssh_enabled",
            "ssh_command",
            "http_enabled",
            "http_url",
            "https_url",
            "custom_domain",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()

        for desktop_id in CommonDeploymentDesktops.get_desktop_ids(deployment_id):
            try:
                domain = Caches.get_document("domains", desktop_id) or {}
            except ValueError:
                domain = {}
            try:
                user = Caches.get_document("users", domain.get("user")) or {}
            except ValueError:
                user = {}
            try:
                target = Targets.get_domain_target(desktop_id)
            except Error:
                target = None
            ssh = (target or {}).get("ssh") or {}
            http = (target or {}).get("http") or {}
            target_id = (target or {}).get("id", "")
            custom_domain = (target or {}).get("domain") or ""
            host = custom_domain or bastion_domain or ""
            # Without a custom domain, HTTP(S) is served on a per-target
            # subdomain of the bastion domain (target id with its last "-"
            # turned into "."), reachable on the platform's public web ports.
            target_host = (
                f"{'.'.join(target_id.rsplit('-', 1))}.{bastion_domain}"
                if target_id and not custom_domain
                else host
            )
            ssh_command = ""
            if ssh.get("enabled") and target_id:
                port = "" if str(ssh_port) == "22" else f" -p {ssh_port}"
                ssh_command = f"ssh {target_id}@{host}{port}"
            http_url = https_url = ""
            if http.get("enabled"):
                http_p = os.environ.get("HTTP_PORT", "80")
                https_p = os.environ.get("HTTPS_PORT", "443")
                http_url = f"http://{target_host}" + (
                    "" if str(http_p) == "80" else f":{http_p}"
                )
                https_url = f"https://{target_host}" + (
                    "" if str(https_p) == "443" else f":{https_p}"
                )
            writer.writerow(
                {
                    "username": user.get("username", ""),
                    "email": user.get("email", ""),
                    "desktop_name": domain.get("name", ""),
                    "status": domain.get("status", ""),
                    "target_id": target_id,
                    "ssh_enabled": bool(ssh.get("enabled")),
                    "ssh_command": ssh_command,
                    "http_enabled": bool(http.get("enabled")),
                    "http_url": http_url,
                    "https_url": https_url,
                    "custom_domain": custom_domain,
                }
            )
        return buffer.getvalue()
