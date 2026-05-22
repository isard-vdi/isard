#
#   Copyright © 2025 Naomi Hidalgo Piñar, Miriam Melina Gamboa Valdez
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
import time
from typing import Any, Optional
from uuid import uuid4

from api.schemas.domains.desktops import (
    BastionAuthorizedKeysUpdateRequest,
    CreateDesktopFromMedia,
    CreateDesktopRequest,
)
from api.services.cards import CardService
from api.services.error import Error
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from fastapi import Request
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.desktop_nonpersistent_events import (
    DesktopNonpersistentEvents,
)
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.logging import Logging
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.scheduler import Scheduler as SchedulerHelper
from isardvdi_common.lib.deployments.deployment_desktops import (
    DeploymentDesktopsProcessed as CommonDeploymentDesktops,
)
from isardvdi_common.lib.domains.desktops.desktop_direct_viewer import (
    DesktopDirectViewer,
)
from isardvdi_common.lib.domains.desktops.desktop_viewers import DesktopViewers
from isardvdi_common.lib.domains.desktops.desktops import (
    DesktopsProcessed as CommonDesktops,
)
from isardvdi_common.lib.domains.desktops.desktops_nonpersistent import (
    DesktopsNonpersistentProcessed as CommonDesktopsNonpersistent,
)
from isardvdi_common.lib.domains.domains import DomainsProcessed
from isardvdi_common.lib.domains.templates.templates import (
    TemplatesProcessed as CommonTemplates,
)
from isardvdi_common.lib.media.media import MediaProcessed as CommonMedia
from isardvdi_common.lib.storage.storage import StorageProcessed as CommonStorage
from isardvdi_common.models.boots import Boot as RethinkBoot
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.media import Media as RethinkMedia
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.targets import Targets
from isardvdi_common.models.targets import Targets as RethinkTargets
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.models.videos import Video as RethinkVideos
from isardvdi_common.schemas.domains import DesktopStatusEnum

# Short TTL coalesces accidental double-clicks on the desktop card "View"
# button. Each .vv download spawns a virt-viewer that opens a fresh SPICE
# session, kicking the previous session — so a fast-fingered click would
# previously leave the user with a frozen screen. 2 seconds is long enough
# to swallow a double-click but far shorter than the time it takes the
# engine to actually restart a domain (which is when the SPICE password
# would legitimately rotate), so cache hits cannot serve stale credentials.
_GET_DESKTOP_VIEWER_CACHE: TTLCache = TTLCache(maxsize=64, ttl=2)


def _get_desktop_viewer_cache_key(
    user_id: str,
    desktop_id: str,
    viewer_type: str,
    is_admin: bool = False,
    request: Optional[Request] = None,
) -> tuple:
    # user_id is in the key so different users never share a cached viewer credential (e.g. SPICE password); `request` is unhashable.
    return hashkey(user_id, desktop_id, viewer_type, is_admin)


class DesktopService:
    @staticmethod
    def get_user_allowed_reservables(payload: dict) -> list[dict]:
        """Return reservable vGPUs visible to the calling user.

        Calls ``allowed.get_items_allowed(payload, "reservables_vgpus",
        ...)``. Filtering is performed against
        ``categories``/``groups``/``roles``/``users`` allowlists in the
        ``reservables_vgpus`` table.
        """
        return Alloweds.get_items_allowed(
            payload,
            "reservables_vgpus",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )

    @staticmethod
    def create_desktop(user_id: str, data: CreateDesktopRequest) -> str:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )

        # TODO: These checks must be reviewed
        Quotas.desktop_create(user_id)
        template = CommonTemplates.get_template(data.template_id)
        CommonTemplates.check_template_status(None, template)
        payload = Helpers.gen_payload_from_user(user_id=user_id)
        if not Alloweds.is_allowed(payload, template, "domains"):
            raise Error(
                "forbidden",
                "User not allowed to use this template",
                description_code="template_not_allowed",
            )
        if data.guest_properties and data.guest_properties.viewers:
            DesktopViewers.check_new_desktop_viewers(
                new_data=data.model_dump(exclude_unset=True), template=template
            )

        # Check if the desktop name is already in use
        Helpers.check_user_duplicated_domain_name(data.name, user_id, "desktop")

        new_data = {
            "hardware": (
                data.hardware.model_dump(exclude_unset=True) if data.hardware else {}
            ),
            "guest_properties": (
                data.guest_properties.model_dump(exclude_unset=True)
                if data.guest_properties
                else {}
            ),
            "reservables": (
                data.reservables.model_dump(exclude_unset=True)
                if data.reservables
                else {}
            ),
        }

        if data.persistent is True:
            desktop = CommonDesktops.new_from_template(
                user_id=user_id,
                desktop_name=data.name,
                desktop_description=data.description,
                template_id=data.template_id,
                new_data=new_data,
                image=data.image.model_dump(exclude_unset=True) if data.image else None,
            )
        else:
            desktop = CommonDesktopsNonpersistent.new_desktop(
                user_id=user_id,
                template_id=data.template_id,
                name=data.name,
                description=data.description,
            )

        if data.bastion_target:
            RethinkTargets.update_domain_target(
                desktop["id"], data.bastion_target.model_dump(exclude_unset=True)
            )

        return desktop["id"]

    @staticmethod
    def create_nonpersistent_desktop(payload: dict, template_id: str) -> str:
        """Create (or reuse + start) a non-persistent desktop from a
        template. ``@has_token`` — takes only ``template_id`` and
        delegates quota + allowlist checks to the common helper.
        """
        user_id = payload["user_id"]
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )
        Quotas.volatile_create(user_id)
        Quotas.desktop_start(user_id, template_id)

        template = CommonTemplates.get_template(template_id)
        if not Alloweds.is_allowed(payload, template, "domains"):
            raise Error(
                "forbidden",
                "User not allowed to use this template",
                description_code="template_not_allowed",
            )

        desktop = CommonDesktopsNonpersistent.new_desktop(
            user_id=user_id,
            template_id=template_id,
        )
        if isinstance(desktop, dict):
            return desktop.get("id")
        return desktop

    @staticmethod
    def create_from_media(user_id: str, data: CreateDesktopFromMedia) -> str:
        """Create a desktop from media"""

        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )
        if not RethinkMedia.exists(data.media_id):
            raise Error(
                "not_found",
                f"Media with ID {data.media_id} not found",
                description_code="not_found",
            )
        # Match v3 ApiDesktopsPersistent.NewFromMedia: enforce per-user
        # desktop_create quota and require at least one viewer.
        Quotas.desktop_create(user_id)
        Helpers.check_user_duplicated_domain_name(data.name, user_id, "desktop")
        guest_viewers = data.guest_properties.viewers if data.guest_properties else None
        if not guest_viewers or not any(
            getattr(guest_viewers, viewer) is not None
            for viewer in (
                "browser_rdp",
                "browser_vnc",
                "file_rdpgw",
                "file_rdpvpn",
                "file_spice",
            )
        ):
            raise Error(
                "bad_request",
                "At least one viewer must be selected.",
                description_code="one_viewer_minimum",
            )

        hardware = data.hardware.model_dump(exclude_unset=True) if data.hardware else {}
        # Engine stores/consumes create_dict.hardware.memory in KiB (see
        # resolve_hardware_from_create_dict in engine/models/domain_xml.py);
        # the apiv4 MediaHardware schema receives memory in GB.
        if "memory" in hardware:
            hardware["memory"] = int(hardware["memory"] * 1048576)
        reservables = (
            data.reservables.model_dump(exclude_unset=True)
            if hasattr(data, "reservables") and data.reservables
            else {}
        )
        # Vue 3 ships ``vgpus: ["None"]`` (the literal string list)
        # to clear the GPU reservable. Coerce here so the booking
        # layer doesn't treat ``["None"]`` as a real reservable
        # later (would block start with "booking required").
        if reservables.get("vgpus") == ["None"]:
            reservables["vgpus"] = None

        user = RethinkUser(user_id)
        media = RethinkMedia(data.media_id)

        if data.kind == "iso":
            if "isos" not in hardware:
                hardware["isos"] = []
            hardware["isos"].append(
                {
                    "id": data.media_id,
                    "name": media.name,
                }
            )
        elif data.kind == "floppy":
            if "floppies" not in hardware:
                hardware["floppies"] = []
            hardware["floppies"].append(
                {
                    "id": data.media_id,
                    "name": media.name,
                }
            )

        # Normalize interfaces: convert ['default'] -> [{'id': 'default', 'mac': 'generated'}]
        if "interfaces" in hardware and hardware.get("interfaces"):
            normalized_ifaces = []
            for iface in hardware.get("interfaces", []):
                if isinstance(iface, str):
                    # create a dict with id and generated MAC
                    normalized_ifaces.append({"id": iface, "mac": gen_random_mac()})
                elif isinstance(iface, dict):
                    if "mac" not in iface:
                        iface["mac"] = gen_random_mac()
                    normalized_ifaces.append(iface)
            hardware["interfaces"] = normalized_ifaces

        if "graphics" not in hardware:
            hardware["graphics"] = ["default"]

        desktop_id = str(uuid4())

        if "disks" not in hardware or not hardware.get("disks"):
            disk_size = hardware.get("disk_size", 1)
            disk_bus = hardware.get("disk_bus", "default")
            hardware["disks"] = [
                {
                    "bus": disk_bus,
                    "extension": "qcow2",
                    "size": str(disk_size) + "G",
                    "parent": None,
                }
            ]

        # Pre-allocate the storage row up-front. The branch's task
        # chain (``Storage.enqueue_disk_creation_chain_for_domain``)
        # requires the domain's ``create_dict.hardware.disks[0]`` to
        # carry both ``storage_id`` and ``file`` *before* the domain
        # row is inserted, so engine restart cleanup can trace the
        # in-flight task via the ``storage_ids`` multi-index.
        # ISO-only desktops (no disks at all) skip this — they have
        # no qcow2 to create.
        pending_storage = None
        pending_size = None
        if hardware.get("disks"):
            pending_size = hardware["disks"][0].get("size")
            pending_storage = Storage.new_dict(
                user_id=user_id,
                pool_usage="desktop",
                parent_id=None,
            )
            pending_storage.status_logs = [
                {"time": int(time.time()), "status": "created"}
            ]
            hardware["disks"][0].update(
                {
                    "storage_id": pending_storage.id,
                    "file": pending_storage.path,
                }
            )
        image_data = None
        if hasattr(data, "image") and data.image:
            if isinstance(data.image, str):
                image_data = data.image
            else:
                image_data = data.image.model_dump(exclude_unset=True)
        else:
            image_data = CardService.get_domain_stock_card(desktop_id)

        desktop = {
            "id": desktop_id,
            "name": data.name,
            "description": data.description,
            "kind": "desktop",
            "user": user.id,
            "username": user.username,
            "status": DesktopStatusEnum.creating_disk_from_scratch.value,
            "detail": "",
            "category": user.category,
            "group": user.group,
            "icon": "",
            "image": image_data,
            "guest_properties": data.guest_properties.model_dump(exclude_unset=True),
            "create_dict": {
                "create_from_virt_install_xml": data.os_template,
                "hardware": hardware,
                "reservables": reservables,
            },
            "hypervisors_pools": ["default"],
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "accessed": int(time.time()),
            "persistent": True,
            "forced_hyp": False,
            "favourite_hyp": False,
            "from_media": data.media_id,
            "tag": False,
            "tag_visible": True,
            "booking_id": False,
        }
        RethinkDomain.init_document(**desktop)

        # Spin up the task chain that builds the qcow2 file and links
        # it back into the domain row. ``creating_disk_from_scratch``
        # is the wait-state the engine sees while the chain runs.
        if pending_storage is not None:
            pending_storage.enqueue_disk_creation_chain_for_domain(
                domain_id=desktop_id,
                size=pending_size,
            )

        return desktop_id

    @staticmethod
    def get_desktop(desktop_id: str) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        desktop = CommonDesktops.get_desktop(desktop_id)
        if not desktop or desktop.get("kind") != "desktop":
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        return desktop

    @staticmethod
    def get_desktop_networks(desktop_id: str) -> list[dict]:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        networks = CommonDesktops.get_desktop_networks(desktop_id)
        return networks

    @staticmethod
    def get_desktop_details(desktop_id: str) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        details = CommonDesktops.get_desktop_details(desktop_id)
        desktop_status = CommonDesktops.parse_frontend_desktop_status(details)["status"]
        boots_names = RethinkBoot.get_boots_names()
        videos_names = RethinkVideos.get_videos_names()
        parsed_details = {
            "id": desktop_id,
            "name": details["name"],
            "description": details["description"],
            "ip": details.get("viewer", {}).get("guest_ip"),
            "vcpu": details["create_dict"]["hardware"].get("vcpus", 0),
            "memory": details["create_dict"]["hardware"].get("memory", 0) / 1048576,
            "disk_bus": details["create_dict"]["hardware"].get("disk_bus", "default"),
            "boot_order": [
                {"id": b, "name": boots_names[b]}
                for b in details["create_dict"]["hardware"].get("boot_order", [])
            ],
            "disks": [
                {
                    "id": d["storage_id"],
                    "size": round(
                        CommonStorage.get_storage_actual_size(d["storage_id"])
                        / 1073741824,
                        2,
                    ),
                }
                for d in details["create_dict"]["hardware"].get("disks", [])
            ],
            "videos": [
                {"id": v, "name": videos_names[v]}
                for v in details["create_dict"]["hardware"].get("videos", [])
            ],
            "viewers": list(
                details.get("guest_properties", {}).get("viewers", {}).keys()
            ),
            "fullscreen": details.get("guest_properties", {}).get("fullscreen", False),
            "reservables": details["create_dict"].get("reservables", {"vgpus": None}),
            "status": desktop_status,
            "interfaces": CommonDesktops.get_desktop_networks(desktop_id),
            "credentials": details.get("guest_properties", {}).get("credentials", None),
            "template": details.get("template", None),
        }

        for media_kind in ["isos", "floppies"]:
            if details["create_dict"]["hardware"].get(media_kind):
                media_ids = [
                    media["id"]
                    for media in details["create_dict"]["hardware"].get(media_kind, [])
                ]
                parsed_details[media_kind] = CommonMedia.get_medias_names(
                    media_ids=media_ids
                )
            else:
                parsed_details[media_kind] = None

        return parsed_details

    @staticmethod
    def get_desktop_bastion(desktop_id: str) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        try:
            bastion = Targets.get_domain_target(desktop_id)
        except Exception:
            bastion = None
        if not bastion:
            bastion = Targets.update_domain_target(desktop_id, {})
        return bastion

    @staticmethod
    def update_desktop_bastion_authorized_keys(
        desktop_id: str, data: BastionAuthorizedKeysUpdateRequest
    ) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        target = Targets.get_domain_target(desktop_id)
        target["ssh"]["authorized_keys"] = data.authorized_keys
        return Targets.update_domain_target(
            domain_id=desktop_id,
            data=target,
        )

    @staticmethod
    def update_desktop_bastion_domain(desktop_id: str, domain_name: str | None) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )

        return Targets.update_domain_target(
            domain_id=desktop_id,
            data={"domain": domain_name},
        )

    @staticmethod
    def update_desktop_bastion_domains(
        payload: dict, desktop_id: str, domains: list[str]
    ) -> None:
        """Update the list of individual bastion domains for a desktop.

        Mirrors v3 ``api_v3_update_bastion_target_domains``
        (``BastionView.py:125``): filters empty entries, limits to 10
        domains, checks uniqueness, DNS-verifies any newly added domain
        against the category CNAME, and writes the updated list back to
        the ``targets`` row.
        """
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )

        from isardvdi_common.helpers.bastion import Bastion

        cleaned = [d.strip() for d in (domains or []) if d and d.strip()]
        if len(cleaned) > 10:
            raise Error(
                "bad_request",
                "Maximum 10 domains allowed",
                description_code="bastion_domains_too_many",
            )

        target = Targets.get_domain_target(desktop_id)
        old_domains = set(target.get("domains", []) or [])

        Bastion.check_duplicate_bastion_domains(cleaned, target_id=target["id"])

        if Bastion.bastion_domain_verification_required():
            category_cname = (
                f"{target['id']}.{Bastion.get_bastion_domain(payload['category_id'])}"
            )
            for domain in cleaned:
                if domain not in old_domains:
                    Bastion.check_bastion_domain_dns(
                        domain,
                        category_cname,
                        kind="cname",
                    )

        Targets.update_domain_target(desktop_id, {"domains": cleaned})

    @staticmethod
    def verify_bastion_domain(payload: dict, desktop_id: str, domain: str) -> dict:
        """Verify a single bastion domain's DNS without saving.

        Mirrors v3 ``api_v3_verify_bastion_domain``
        (``BastionView.py:198``). Returns ``{"verified": True}`` on
        success, or raises ``precondition_required`` on DNS mismatch.
        """
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )

        from isardvdi_common.helpers.bastion import Bastion

        domain = (domain or "").strip()
        if not domain:
            raise Error(
                "bad_request",
                "Domain is required",
                description_code="bastion_domain_required",
            )

        target = Targets.get_domain_target(desktop_id)
        Bastion.check_duplicate_bastion_domains([domain], target_id=target["id"])

        if Bastion.bastion_domain_verification_required():
            Bastion.check_bastion_domain_dns(
                domain,
                f"{target['id']}.{Bastion.get_bastion_domain(payload['category_id'])}",
                kind="cname",
            )

        return {"verified": True}

    @staticmethod
    def get_desktop_share_link(desktop_id: str) -> str:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        link = DesktopDirectViewer.get_desktop_jumper_url(desktop_id=desktop_id)
        return link

    @staticmethod
    def update_desktop_share_link(desktop_id: str, enabled: bool = True) -> str:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        link = DesktopDirectViewer.reset_desktop_jumper_url(
            desktop_id=desktop_id, enabled=enabled
        )
        return link

    @staticmethod
    def get_desktop_direct_viewer_from_token(token: str, request: Request) -> dict:
        direct_viewer = DesktopDirectViewer.desktop_viewer_from_token(
            token, request=request
        )
        return direct_viewer

    @staticmethod
    def get_desktop_viewer_data_from_token(token, viewer_type, request):
        Logging.logs_domain_event_directviewer(
            DesktopDirectViewer.desktop_from_token(token)["id"],
            action_user=None,
            viewer_type=viewer_type,
            user_request=request,
        )
        return DesktopDirectViewer.desktop_viewer_data_from_token(token, viewer_type)

    @staticmethod
    def get_direct_viewer_docs():
        docs_link = DesktopDirectViewer.desktop_viewer_docs()
        return docs_link

    @staticmethod
    def reset_desktop_from_token(token: str, request: Request) -> str:
        desktop_id = DesktopDirectViewer.reset_desktop(token, request)
        return desktop_id

    @staticmethod
    def get_desktop_networks_from_token(token):
        desktop_id = DesktopDirectViewer.get_desktop_from_token(token)["id"]
        return DesktopService.get_desktop_networks(desktop_id)

    @staticmethod
    def get_desktop_details_from_token(token: str) -> dict:
        desktop_id = DesktopDirectViewer.get_desktop_from_token(token)["id"]
        return DesktopService.get_desktop_details(desktop_id)

    @staticmethod
    def start_desktop_from_token(token, request):
        return DesktopDirectViewer.start_desktop(token, request)

    @staticmethod
    def owns_desktop_viewer_by_desktop_id(
        desktop_id: str,
        user_id: str,
        category_id: str,
        role_id: str,
        connection_ip: str = None,
    ) -> None:
        """Delegate to the common helper. Raises on failure."""
        DesktopDirectViewer.owns_desktop_viewer_by_desktop_id(
            desktop_id=desktop_id,
            user_id=user_id,
            category_id=category_id,
            role_id=role_id,
            connection_ip=connection_ip,
        )

    @staticmethod
    def owns_desktop_viewer_by_ip(
        user_id: str, category_id: str, role_id: str, guess_ip: str
    ) -> None:
        """Delegate to the common helper. Raises on failure."""
        DesktopDirectViewer.owns_desktop_viewer_by_ip(
            user_id=user_id,
            category_id=category_id,
            role_id=role_id,
            guess_ip=guess_ip,
        )

    @staticmethod
    def owns_desktop_viewer_by_proxies(
        user_id: str,
        category_id: str,
        role_id: str,
        proxy_video: str,
        proxy_hyper_host: str,
        port: int,
    ) -> None:
        """Delegate to the common helper. Raises on failure."""
        DesktopDirectViewer.owns_desktop_viewer_by_proxies(
            user_id=user_id,
            category_id=category_id,
            role_id=role_id,
            proxy_video=proxy_video,
            proxy_hyper_host=proxy_hyper_host,
            port=port,
        )

    @staticmethod
    def stop_desktop(
        desktop_id: str,
        user_id: str,
        force: Optional[bool] = None,
        request: Optional[Request] = None,
    ) -> str:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        # Status flip BEFORE the audit-log write — same reasoning as in
        # `start_desktop`. Otherwise the audit-log update emits a changefeed
        # event with the unchanged status and the frontend's optimistic
        # `Stopping` reverts visibly before settling.
        DesktopEvents.desktop_stop(desktop_id=desktop_id, force=force)
        Logging.logs_domain_stop_api(desktop_id, user_id, user_request=request)
        SchedulerHelper.remove_desktop_timeouts(desktop_id)
        return desktop_id

    @staticmethod
    def change_owner(payload: dict, desktop_id: str, new_user_id: str) -> None:
        """Reassign a desktop to a different user.

        Mirrors v3 ``api_v3_desktop_change_owner``
        (``api/views/CommonView.py:186``). Both ``ownsUserId`` and
        ``ownsDomainId`` are enforced before the DB flip.
        """
        Helpers.owns_user_id(payload=payload, user_id=new_user_id)
        Helpers.owns_domain_id(payload=payload, domain_id=desktop_id)
        Helpers.change_owner_desktop(user_id=new_user_id, desktop_id=desktop_id)

    @staticmethod
    def retry_failed_desktop(desktop_id: str, user_id: str) -> dict:
        """Transition a Failed desktop back to StartingPaused.

        Ports the v3 ``GET /desktop/updating/{desktop_id}`` behaviour
        the webapp admin exposes through the "retry" row action. The
        atomic ``r.branch`` flip lives in
        ``DesktopEvents.desktop_retry_failed`` (common package) so the
        service stays a thin orchestration layer.
        """
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        payload = Helpers.gen_payload_from_user(user_id=user_id)
        Helpers.owns_domain_id(payload=payload, domain_id=desktop_id)
        new_status = DesktopEvents.desktop_retry_failed(desktop_id)
        return {"id": desktop_id, "status": new_status}

    @staticmethod
    def bulk_edit_desktops(ids: list[str], data: dict, payload: dict) -> dict:
        """Bulk-edit a list of desktops.

        Ports the v3 ``PUT /domain/bulk`` handler that called
        ``Desktops.update_desktop`` in bulk mode. Ownership is enforced
        per-id via ``Helpers.owns_domain_id`` before the update.
        """
        if not ids or not isinstance(ids, list):
            raise Error(
                "bad_request",
                "bulk edit requires a non-empty 'ids' list",
            )
        for desktop_id in ids:
            Helpers.owns_domain_id(payload=payload, domain_id=desktop_id)
        admin_or_manager = payload.get("role_id") in ("manager", "admin")
        CommonDesktops.update_desktop(
            ids, data, admin_or_manager=admin_or_manager, bulk=True
        )
        return {"ids": ids}

    @staticmethod
    def bulk_create_persistent_desktops(payload: dict, data: dict) -> dict:
        """Create multiple persistent desktops from a template.

        Ports the v3 ``POST /persistent_desktop/bulk`` handler that called
        ``Desktops.bulk_create_desktops``. The common lib method handles
        both allowed-entity fan-out and quota checks.
        """
        return CommonDesktops.bulk_create_desktops(payload, data)

    @staticmethod
    def stop_user_desktops(
        user_id: str,
        force: Optional[bool] = None,
        request: Optional[Request] = None,
    ) -> None:
        stopped_desktops_ids = CommonDesktops.stop_user_desktops(user_id, force)
        for desktop_id in stopped_desktops_ids:
            SchedulerHelper.remove_desktop_timeouts(desktop_id)
            Logging.logs_domain_stop_api(desktop_id, user_id, user_request=request)

    @staticmethod
    def start_desktop(
        desktop_id: str, user_id: str, request: Optional[Request] = None
    ) -> str:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        payload = Helpers.gen_payload_from_user(user_id=user_id)
        if Helpers.owns_deployment_desktop_id(payload=payload, desktop_id=desktop_id):
            desktop = Quotas.deployment_desktop_start(user_id, desktop_id)
        else:
            desktop = Quotas.desktop_start(user_id, desktop_id)
        desktop = CommonDesktops._parse_desktop_booking(desktop)
        if desktop["needs_booking"]:
            # If the user is neither admin or manager check that we are in a booking
            if (
                not payload["role_id"] in ["admin", "manager"]
                and not desktop["booking_id"]
            ):
                raise Error(
                    "precondition_required",
                    "Desktop needs a booking to be started",
                    description_code="desktop_not_booked",
                )
            # Check that the current plan is the one that allows to start the desktop
            try:
                CommonDesktops.check_current_plan(
                    payload=payload, desktop_id=desktop_id
                )
            except Error as e:
                if payload["role_id"] not in ["admin", "manager"]:
                    raise e
        # Flip status to Starting BEFORE writing the audit-log id. Both
        # writes hit the `domains` row, but only the status flip carries the
        # new status — if the audit-log update lands first, its changefeed
        # event emits status=Stopped (unchanged), which races the optimistic
        # frontend flip and makes the desktop card visibly flicker
        # Stopped → Starting → Stopped → Starting before settling.
        DesktopEvents.desktop_start(desktop_id=desktop_id)
        Logging.logs_domain_start_api(desktop_id, user_id, user_request=request)
        SchedulerHelper.add_desktop_timeouts(payload, desktop_id)

        return desktop_id

    @staticmethod
    def extend_desktop_timeout(payload: dict, desktop_id: str) -> None:
        """Extend the remaining time before automatic desktop shutdown."""
        desktop = DomainsProcessed.get_status_and_scheduled(desktop_id)
        if not desktop or desktop.get("status") != "Started":
            raise Error(
                "precondition_required",
                "Desktop is not running",
                description_code="desktop_not_started",
            )
        current_shutdown = desktop.get("scheduled", {}).get("shutdown")
        if not current_shutdown:
            raise Error(
                "precondition_required",
                "Desktop has no scheduled shutdown",
                description_code="desktop_no_scheduled_shutdown",
            )
        # Re-add timeouts from current time
        SchedulerHelper.add_desktop_timeouts(payload, desktop_id, reset_existing=True)

    @staticmethod
    def desktop_update_status(desktop_id: str) -> str:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        DesktopEvents.desktop_updating(desktop_id=desktop_id)
        return desktop_id

    @staticmethod
    def delete_desktop(
        desktop_id: str, user_id: Optional[str] = None, permanent: bool = False
    ) -> bool | list | None:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        persistent = RethinkDomain(desktop_id).persistent
        if persistent:
            # `DesktopEvents.desktop_delete` returns the storage-delete
            # tasks whenever the recycle bin is skipped (permanent=True,
            # tagged desktop, or a 0s cutoff). Otherwise the desktop is
            # moved to the recycle bin and the call returns None.
            return DesktopEvents.desktop_delete(
                desktop_id=desktop_id, agent_id=user_id, permanent=permanent
            )
        else:
            DesktopNonpersistentEvents.desktop_non_persistent_delete(
                desktop_id=desktop_id
            )
            return True

    @staticmethod
    def create_desktops(
        create_dict_list: list[dict], users: list[str], tag: str | bool
    ) -> None:
        """Create desktops from a list of create_dicts and a list of users. Engine will create the XMLs after being added in the database"""
        for create_dict in create_dict_list:
            hardware = create_dict["hardware"]
            template = RethinkDomain(create_dict["template"])
            # Path-shaped ``parent`` lineage marker not written: see
            # PR3. ``storage.parent`` UUID + qcow2 header are the
            # chain representations consumed downstream.
            hardware["disks"] = [{"extension": "qcow2"}]
            interfaces = []
            hardware["graphics"] = ["default"]
            for interface in hardware.get("interfaces"):
                interfaces.append(
                    {
                        "id": interface,
                        "mac": gen_random_mac(),
                    }
                )
            hardware["interfaces"] = interfaces
            for user_id in users:
                if not RethinkUser.exists(user_id):
                    raise Error(
                        "not_found",
                        f"User with ID {user_id} not found",
                        description_code="not_found",
                    )
                user = RethinkUser(user_id)
                desktop = {
                    "id": str(uuid4()),
                    "name": create_dict["name"],
                    "description": "",
                    "kind": "desktop",
                    "user": user.id,
                    "username": user.username,
                    "status": DesktopStatusEnum.creating.value,
                    "category": user.category,
                    "group": user.group,
                    "icon": "",
                    "image": create_dict["image"],
                    "os": create_dict.get("os", None),
                    "guest_properties": create_dict["guest_properties"],
                    "create_dict": {
                        "hardware": hardware,
                        "origin": create_dict["template"],
                        "reservables": create_dict["reservables"],
                    },
                    "hypervisors_pools": ["default"],
                    "allowed": {
                        "roles": False,
                        "categories": False,
                        "groups": False,
                        "users": False,
                    },
                    "accessed": int(time.time()),
                    "persistent": True,
                    "forced_hyp": False,
                    "favourite_hyp": False,
                    "from_template": create_dict["template"],
                    "tag": tag,
                    "tag_visible": True,
                    "booking_id": False,
                }

                if "hardware" in create_dict and "memory" in hardware:
                    desktop["create_dict"]["hardware"]["memory"] = int(
                        hardware["memory"] * 1048576
                    )

                RethinkDomain(**desktop)

    @staticmethod
    def toggle_user_deployment_desktops_visibility(
        user_id: str, deployment_id: str
    ) -> list[dict]:
        """
        Toggle visibility (tag_visible) of all desktops belonging to a user in a deployment.
        Returns the list of updated desktops.
        """
        desktops = list(
            CommonDeploymentDesktops.get_deployment_user_desktops(
                deployment_id, user_id
            )
        )
        if not desktops:
            raise Error(
                "not_found",
                f"No desktops found for user {user_id} in deployment {deployment_id}",
                description_code="not_found",
            )
        visible = all(d.get("tag_visible", True) for d in desktops)
        desktop_ids = [d["id"] for d in desktops]
        CommonDeploymentDesktops.update_desktops_visibility(desktop_ids, not visible)
        return desktops

    @staticmethod
    def get_user_desktops(user_id: str) -> list[dict]:
        return CommonDesktops.get_user_desktops(user_id)

    # TODO: For now pagination won't be used since the user load is not as high. Although this works, it is not needed yet.

    @classmethod
    def get_user_desktops_paginated(
        cls,
        user_id: str,
        start_after: Optional[int] = None,
        page_size: int = 10,
        sort_field: str = "accessed",
        sort_order: str = "desc",
        search: Optional[str] = None,
        search_field: Optional[str] = "name",
        filters: Optional[dict] = None,
    ) -> dict:
        """
        Get all desktops for a specific user.
        Returns a list of desktops.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )

        # The only supported sort_field is "accessed" — the route layer
        # enforces it via ``Literal["accessed"]``. Map it explicitly so
        # an unmapped value never reaches the rdb query and crashes
        # downstream with ``UnboundLocalError: local variable 'index'``.
        sort_index = {"accessed": "kind_user_accessed"}
        if sort_field not in sort_index:
            raise Error(
                "bad_request",
                f"Unsupported sort_field: {sort_field!r}",
                description_code="bad_sort_field",
            )
        index = sort_index[sort_field]
        index_value = ["desktop", user_id]

        desktops = RethinkDomain.get_desktops(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
        )

        parsed_desktops = [
            CommonDesktops._parse_desktop(desktop)
            for desktop in desktops
            if not desktop.get("tag")
            or desktop.get("tag")
            and desktop.get("tag_visible")
        ]

        total = RethinkDomain.query_count_raw(
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
        )

        return {
            "rows": parsed_desktops,
            "total": total,
        }

    @classmethod
    def get_all_desktops(
        cls,
        start_after: Optional[int] = None,
        page_size: int = 10,
        sort_field: str = "accessed",
        sort_order: str = "desc",
        search: Optional[str] = None,
        search_field: Optional[str] = "name",
        # filters=None,
    ) -> dict:
        """
        Get all desktops with pagination and optional filters.
        """

        # Determine the index based on the sort field
        # Rethinkdb only supports get_all and order_by on a single field
        # so we need to choose the index based on the sort field

        if sort_field == "accessed":
            index = "kind_accessed"
        else:
            index = "kind"

        index_value = ["desktop"]

        # TODO: Enable filters when needed. This might require a more complex index setup, considering the accessed field.
        # Apply filters using the most specific index available
        # If so, we can use the index to optimize the query and remove the filtering
        # if filters:
        #     if "status" in filters and "category" in filters:
        #         index = "kind_status_category"
        #         index_value = ["desktop", filters["status"], filters["category"]]
        #         filters.pop("status", None)
        #         filters.pop("category", None)
        #     elif "status" in filters and "group" in filters:
        #         index = "kind_status_group"
        #         index_value = ["desktop", filters["status"], filters["group"]]
        #         filters.pop("status", None)
        #         filters.pop("group", None)
        #     elif "status" in filters and "user" in filters:
        #         index = "kind_status_user"
        #         index_value = ["desktop", filters["status"], filters["user"]]
        #         filters.pop("status", None)
        #         filters.pop("user", None)
        #     elif "category" in filters:
        #         index = "kind_category"
        #         index_value = ["desktop", filters["category"]]
        #         filters.pop("category", None)
        #     elif "group" in filters:
        #         index = "kind_group"
        #         index_value = ["desktop", filters["group"]]
        #         filters.pop("group", None)
        #     elif "user" in filters:
        #         index = "kind_user"
        #         index_value = ["desktop", filters["user"]]
        #         filters.pop("user", None)
        #     elif "status" in filters:
        #         index = "kind_status"
        #         index_value = ["desktop", filters["status"]]
        #         filters.pop("status", None)

        desktops = RethinkDomain.get_desktops(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            # filters=filters,
        )

        parsed_desktops = [
            CommonDesktops._parse_desktop(desktop)
            for desktop in desktops
            if not desktop.get("tag")
            or desktop.get("tag")
            and desktop.get("tag_visible")
        ]

        total = RethinkDomain.query_count_raw(
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            # filters=filters,
        )

        return {
            "rows": parsed_desktops,
            "total": total,
        }

    def edit_desktop(desktop_id: str, data: dict, payload: dict) -> None:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )

        bastion_data = data.pop("bastion_target", None)

        CommonDesktops.validate_desktop_update(data, desktop_id)

        CommonDesktops.update_desktop(
            desktop_id=desktop_id,
            desktop_data=data,
            admin_or_manager=payload["role_id"] in ["admin", "manager"],
            bulk=False,
        )

        if bastion_data is not None:
            RethinkTargets.update_domain_target(desktop_id, bastion_data)

    @staticmethod
    @cached(_GET_DESKTOP_VIEWER_CACHE, key=_get_desktop_viewer_cache_key)
    def get_desktop_viewer(
        user_id: str,
        desktop_id: str,
        viewer_type: str,
        is_admin: bool = False,
        request: Optional[Request] = None,
    ) -> dict:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        viewer = DesktopDirectViewer.desktop_viewer(
            desktop_id, protocol=viewer_type, get_cookie=True, admin_role=is_admin
        )
        return viewer

    @staticmethod
    def recreate_desktop(
        payload: dict,
        desktop_id: str,
    ) -> Any:
        if not RethinkDomain.exists(desktop_id):
            raise Error(
                "not_found",
                f"Desktop with ID {desktop_id} not found",
                description_code="not_found",
            )
        Helpers.check_task_priority(payload, "default")
        Helpers.check_task_retry(payload, 0)
        desktop_storages = RethinkDomain(desktop_id).storages
        # Iterate over all storages (for now only one storage per desktop is supported)
        for storage in desktop_storages:
            storage = CommonStorage.check_storage(payload, storage.id)
            try:
                return storage.recreate(
                    payload.get("user_id"),
                    desktop_id,
                    priority="default",
                    retry=0,
                )
            except Exception as e:
                raise Error(*e.args)


def gen_random_mac() -> str:
    mac = [
        0x52,
        0x54,
        0x00,
        random.randint(0x00, 0x7F),
        random.randint(0x00, 0xFF),
        random.randint(0x00, 0xFF),
    ]
    return ":".join(map(lambda x: "%02x" % x, mac))
