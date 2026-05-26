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


from api.services.error import Error
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.domains.domains import DomainsProcessed as CommonDomains
from isardvdi_common.lib.users.users.user import UsersProcessed
from isardvdi_common.models.interfaces import Interface


class DomainService:

    @staticmethod
    def get_domain_info(domain_id: str, payload: dict) -> dict:
        """Get domain definition + runtime state used by the admin info modal."""
        domain_def = Caches.get_document(
            "domains",
            domain_id,
            [
                "id",
                "kind",
                "name",
                "description",
                "image",
                "guest_properties",
                "status",
                "hyp_started",
                "viewer",
                "tag",
                "user",
            ],
            invalidate=True,
        )

        if not domain_def:
            raise Error("not_found", f"Domain with ID {domain_id} not found")

        hardware = CommonDomains.get_domain_hardware(domain_id)

        # hyp_started persists as False (not None) when never scheduled.
        hyp_started = domain_def.get("hyp_started")
        if not hyp_started:
            hyp_started = None

        viewer = domain_def.get("viewer") or {}
        guest_ip = viewer.get("guest_ip") or None

        # ``tag`` holds the deployment id when the domain belongs to one.
        deployment_name = None
        deployment_id = domain_def.get("tag")
        if deployment_id and isinstance(deployment_id, str):
            deployment = Caches.get_document(
                "deployments", deployment_id, ["id", "name"]
            )
            if deployment:
                deployment_name = deployment.get("name")

        storage_id = None
        disks = (hardware.get("hardware") or {}).get("disks") or []
        if disks:
            storage_id = (
                disks[0].get("storage_id") if isinstance(disks[0], dict) else None
            )

        owner = None
        user_id = domain_def.get("user")
        if user_id:
            try:
                user = UsersProcessed.get_user_full_data(user_id)
            except Exception:
                user = None
            if user:
                owner = {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "name": user.get("name"),
                    "email": user.get("email"),
                    "role": user.get("role"),
                    "category": user.get("category"),
                    "category_name": user.get("category_name"),
                    "group": user.get("group"),
                    "group_name": user.get("group_name"),
                }

        # hardware.interfaces is list[{id, mac}] (desktops) or list[str] (templates).
        interfaces_list = None
        raw_interfaces = (hardware.get("hardware") or {}).get("interfaces")
        if raw_interfaces:
            names_by_id = Interface.get_interfaces_names()
            interfaces_list = []
            for iface in raw_interfaces:
                if isinstance(iface, str):
                    interfaces_list.append(
                        {"id": iface, "name": names_by_id.get(iface), "mac": None}
                    )
                else:
                    iface_id = iface.get("id")
                    interfaces_list.append(
                        {
                            "id": iface_id,
                            "name": names_by_id.get(iface_id) if iface_id else None,
                            "mac": iface.get("mac"),
                        }
                    )

        domain = {
            **domain_def,
            **hardware,
            "status": domain_def.get("status"),
            "hyp_started": hyp_started,
            "guest_ip": guest_ip,
            "deployment_name": deployment_name,
            "storage_id": storage_id,
            "owner": owner,
            "interfaces": interfaces_list,
        }
        domain.pop("viewer", None)
        domain.pop("tag", None)
        domain.pop("user", None)
        return Quotas.limit_user_hardware_allowed(payload, domain)
