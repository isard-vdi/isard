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

import asyncio
import copy
import json
import logging as log
import time
import traceback
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from typing import Literal

import gevent
from cachetools import TTLCache, cached
from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.api_notify import notify_admins, send_socket_user
from isardvdi_common.helpers.bookings import Bookings
from isardvdi_common.helpers.bookings import Bookings as BookingsHelpers
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.cards import Cards
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_viewer import default_guest_properties
from isardvdi_common.helpers.logging import Logging
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.rules import get_unused_item_timeout
from isardvdi_common.lib.bookings.bookings import BookingsProcessed
from isardvdi_common.lib.bookings.reservables_planner_compute import (
    ReservablesPlannerCompute,
)
from isardvdi_common.lib.domains.disk_resolver import resolve_parent_disk
from isardvdi_common.lib.domains.templates.templates import TemplatesProcessed
from isardvdi_common.lib.storage.storage import StorageProcessed
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.user import User
from isardvdi_common.schemas.domains import (
    DesktopFromTemplate,
    DomainStatus,
    TemplateToDesktop,
)
from rethinkdb import r
from socketio import RedisManager

from ....schemas.domains import DesktopFromTemplate, DesktopStatusEnum, DomainStatus

socketio = RedisManager(socketio_url(), write_only=True)


class DesktopsProcessed(RethinkSharedConnection):
    _rdb_table = "domains"

    # TODO(move-domains-to-common): centralize this constants
    MIN_AUTOBOOKING_TIME = 30
    MAX_BOOKING_TIME = 12 * 60  # 12h

    @staticmethod
    def parse_frontend_desktop_status(desktop):
        # TODO(separate-common-classes): move this to a desktop helpers class
        if (
            desktop["status"].startswith("Creating")
            and desktop["status"] != DesktopStatusEnum.creating_and_starting.value
        ):
            desktop["status"] = DesktopStatusEnum.creating.value
        if desktop["status"] == DesktopStatusEnum.started.value and not desktop.get(
            "viewer", {}
        ).get("passwd"):
            desktop["status"] = DesktopStatusEnum.starting.value

        if (
            desktop["status"] == DesktopStatusEnum.started.value
            and "wireguard"
            in [i["id"] for i in desktop["create_dict"]["hardware"]["interfaces"]]
            and not desktop.get("viewer", {}).get("guest_ip")
        ):
            desktop["status"] = DesktopStatusEnum.waiting_ip.value

        return desktop

    @classmethod
    def _parse_desktop(cls, desktop):
        # TODO(separate-common-classes): move this to a desktop helpers class
        desktop = cls.parse_frontend_desktop_status(desktop)
        desktop["image"] = desktop.get("image", None)
        parents = desktop.get("parents")
        desktop["from_template"] = (
            parents[-1] if isinstance(parents, (list, tuple)) and parents else None
        )

        if desktop.get("persistent", True):
            desktop["type"] = "persistent"
        else:
            desktop["type"] = "nonpersistent"

        gp = desktop.get("guest_properties") or default_guest_properties()
        desktop["viewers"] = [
            v.replace("_", "-") for v in list(gp.get("viewers", {}).keys())
        ]

        if desktop["status"] == DesktopStatusEnum.started.value:
            if "wireguard" in [
                i["id"] for i in desktop["create_dict"]["hardware"]["interfaces"]
            ]:
                desktop["ip"] = desktop.get("viewer", {}).get("guest_ip")
            else:
                desktop["viewers"] = [
                    v
                    for v in desktop["viewers"]
                    if v not in ["file-rdpgw", "file-rdpvpn", "browser-rdp"]
                ]

        if desktop["status"] == DesktopStatusEnum.downloading.value:
            progress = {
                "percentage": desktop.get("progress", {}).get("received_percent"),
                "throughput_average": desktop.get("progress", {}).get(
                    "speed_download_average"
                ),
                "time_left": desktop.get("progress", {}).get("time_left"),
                "size": desktop.get("progress", {}).get("total"),
            }
        else:
            progress = None
        editable = True
        if desktop.get("tag"):
            deployment_user = Caches.get_document(
                "deployments", desktop.get("tag"), ["user"]
            )
            try:
                editable = True if deployment_user == desktop["user"] else False
            except Exception as e:
                print(e)
                # log.debug(traceback.format_exc())
                editable = False
            permissions = Caches.get_document(
                "deployments", desktop.get("tag"), ["user_permissions"]
            )
            if permissions is None:
                desktop["permissions"] = []
            else:
                desktop["permissions"] = permissions
                desktop["permissions"].sort()

        bastion_targets = desktop.pop("bastion_targets", None)
        if (
            bastion_targets
            and isinstance(bastion_targets, list)
            and len(bastion_targets) > 0
        ):
            desktop["bastion_target"] = bastion_targets[0]

        parsed_desktop = {
            "id": desktop["id"],
            "name": desktop["name"],
            "status": desktop["status"],
            # `state` is the apiv3 alias the old-frontend (Vue 2) reads; same
            # value as `status`. Vue 3 reads `status` directly. Keeping both
            # in the response makes a single endpoint serve both frontends.
            "state": desktop["status"],
            "type": desktop["type"],
            "template": desktop["from_template"],
            "viewers": desktop["viewers"],
            "icon": desktop["icon"],
            "image": desktop["image"],
            "description": desktop["description"],
            "ip": desktop.get("ip"),
            "progress": progress,
            "editable": editable,
            "scheduled": desktop.get("scheduled", {"shutdown": False}),
            "server": desktop.get("server"),
            "accessed": desktop.get("accessed"),
            "tag": desktop.get("tag"),
            "visible": desktop.get("tag_visible"),
            "user": desktop.get("user"),
            "user_name": desktop.get("user_name"),
            "group": desktop.get("group"),
            "category": desktop.get("category"),
            "reservables": desktop["create_dict"].get("reservables", {"vgpus": None}),
            "interfaces": desktop["create_dict"]["hardware"]["interfaces"],
            "current_action": desktop.get("current_action"),
            "storage": [
                disk.get("storage_id")
                for disk in desktop["create_dict"]["hardware"].get("disks", [{}])
            ],
            "permissions": desktop.get("permissions", []),
            "bastion_target": desktop.get("bastion_target"),
        }

        # The group and category name are only available if defined
        if desktop.get("group_name"):
            parsed_desktop["group_name"] = desktop["group_name"]
        if desktop.get("category_name"):
            parsed_desktop["category_name"] = desktop["category_name"]
        if desktop.get("user_name"):
            parsed_desktop["user_name"] = desktop["user_name"]

        return {
            **parsed_desktop,
            **cls._parse_desktop_booking(desktop),
        }

    @classmethod
    def _parse_desktop_booking(cls, desktop):
        if not desktop.get("create_dict", {}).get("reservables") or not any(
            list(desktop["create_dict"]["reservables"].values())
        ):
            return {
                "needs_booking": False,
                "next_booking_start": None,
                "next_booking_end": None,
                "booking_id": False,
            }
        item_id = desktop["id"]
        booking = BookingsProcessed.get_cached_desktop_bookings(item_id)
        if not booking and desktop.get("tag"):
            booking = BookingsProcessed.get_cached_deployment_bookings(
                desktop.get("tag")
            )

        if booking:
            return {
                "needs_booking": True,
                "next_booking_start": booking[0]["start"].strftime("%Y-%m-%dT%H:%M%z"),
                "next_booking_end": booking[0]["end"].strftime("%Y-%m-%dT%H:%M%z"),
                "booking_id": desktop.get("booking_id", False),
            }
        else:
            return {
                "needs_booking": True,
                "next_booking_start": None,
                "next_booking_end": None,
                "booking_id": False,
            }

    @classmethod
    def new_from_templateTh(cls, desktops, deployment):
        # Bulk-spawn progress events are emitted directly via SocketIO here
        # (bypassing RethinkDB -> changefeed -> change-handler) because they
        # describe a transient, in-flight operation that is not persisted to
        # the DB: we need a "started bulk creation" signal BEFORE the first
        # row is inserted, and an "ended" signal AFTER the loop, neither of
        # which corresponds to a DB change on any single row.
        #
        # Documented as a known bypass path in
        # migration/ENGINE_CHANGE_HANDLING.md. If these events ever need to
        # be sourced from DB rows instead, the deployment row would need a
        # `bulk_create_status` field and the DeploymentsHandler in
        # change-handler would map that field's transitions to these events.
        async def process_desktops():
            send_socket_user(
                "creating_desktops",
                {"deployment_id": deployment["id"]},
                [deployment["user"]] + deployment["co_owners"],
            )
            for desktop in desktops:
                result = cls.new_from_template(
                    desktop["name"],
                    desktop["description"],
                    desktop["template_id"],
                    desktop["user_id"],
                    desktop["domain_id"],
                    desktop["deployment_tag_dict"],
                    desktop["new_data"],
                    desktop["image"],
                    soft=True,
                )
                if result is not None:
                    Helpers.set_current_booking(
                        {
                            "id": result["id"],
                            "tag": result["tag"],
                            "create_dict": result["create_dict"],
                        }
                    )
                time.sleep(0.25)
            send_socket_user(
                "end_creating_desktops",
                {"deployment_id": deployment["id"]},
                [deployment["user"]] + deployment["co_owners"],
            )

        # Spawn the process_desktops greenlet and return immediately
        asyncio.create_task(process_desktops())

    @classmethod
    def merge_new_data_with_template(cls, template_id, new_data):
        """

        Parse and merge template defaults with new data for desktop creation.
        This method retrieves a template and merges it with optional new data
        to create the final configuration for desktop creation.
        Args:
            template_id (str): The ID of the template to retrieve
            new_data (dict, optional): Dictionary containing new data to merge with template.
                Can contain 'hardware', 'reservables', and/or 'guest_properties' keys.
                - hardware: Updates existing hardware configuration
                - reservables: Replaces reservables configuration entirely
                - guest_properties: Merges with existing guest properties, with viewers being overridden
        Returns:
            tuple: A tuple containing:
                - create_dict (dict): Deep copy of template's create_dict merged with new hardware/reservables
                - guest_properties (dict): Deep copy of template's guest_properties merged with new guest_properties
        Raises:
            Error: If template_id is not found in cache, raises "not_found" error with description

        """
        template = Caches.get_document("domains", template_id)
        if not template:
            raise Error(
                "not_found",
                "Template not found",
                traceback.format_exc(),
                description_code="not_found",
            )

        new_data = new_data or {}
        new_hardware = new_data.get("hardware") or {}

        create_dict = copy.deepcopy(template["create_dict"])
        guest_properties = copy.deepcopy(template["guest_properties"])

        # Hardware interfaces must be an array of ids. Hence when inheriting from the template it must be transformed
        if not new_hardware.get("interfaces"):
            create_dict["hardware"]["interfaces"] = [
                i["id"] if isinstance(i, dict) and i.get("id") else i
                for i in create_dict["hardware"]["interfaces"]
            ]

        # Hardware isos must be an array of ids. Hence when inheriting from the template it must be transformed
        if not new_hardware.get("isos"):
            create_dict["hardware"]["isos"] = [
                i["id"] if isinstance(i, dict) and i.get("id") else i
                for i in create_dict["hardware"].get("isos", [])
            ]

        # Memory must be in MB, transform it from bytes to MB when inheriting from template
        if create_dict["hardware"].get("memory"):
            create_dict["hardware"]["memory"] = float(
                create_dict["hardware"]["memory"] / 1048576
            )

        # If new_data is provided, we need to update the template with the new data
        if new_data and (
            new_data.get("hardware")
            or new_data.get("reservables")
            or new_data.get("guest_properties")
        ):
            if new_data.get("hardware"):
                # If hardware is provided, we need to update the template with the new data
                create_dict["hardware"].update(new_data["hardware"])

            if new_data.get("reservables"):
                # The Vue 3 client ships ``vgpus: ["None"]`` (the
                # literal string list) when the user clears the
                # reservable. Coerce to ``None`` here, same as the
                # from-media + edit paths already do — without this
                # the desktop persists ``["None"]``, which the booking
                # layer treats as a real reservable and demands a
                # booking on every start, even for non-GPU desktops.
                if new_data["reservables"].get("vgpus") == ["None"]:
                    new_data["reservables"]["vgpus"] = None
                create_dict["reservables"] = new_data["reservables"]

            # If new_data contains guest_properties, merge only the provided keys
            if new_data.get("guest_properties"):
                guest_properties.update(new_data["guest_properties"])
                guest_properties["viewers"] = new_data["guest_properties"]["viewers"]

        return create_dict, guest_properties

    @classmethod
    def new_from_template(
        cls,
        desktop_name,
        desktop_description,
        template_id,
        user_id,
        domain_id=None,
        deployment_tag_dict=False,
        new_data=None,
        image=None,
        insert=True,
        soft=False,
    ):
        template = Caches.get_document("domains", template_id)
        if not template:
            raise Error(
                "not_found",
                "Template not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        user = Caches.get_document(
            "users", user_id, ["id", "username", "category", "group"]
        )
        if user is None:
            raise Error(
                "not_found",
                f"new_from_template: user id {user_id} not found.",
                description_code="not_found",
            )

        # Inherit the template data and override with the given new_data
        create_dict, guest_properties = cls.merge_new_data_with_template(
            template_id, new_data
        )

        # Generate new MACs for the interfaces
        create_dict["hardware"]["interfaces"] = Helpers.gen_interfaces_macs(
            create_dict["hardware"]["interfaces"]
        )

        # Add the disks to the create_dict so the new qcow2 disk are created
        parent_disk = resolve_parent_disk(template)
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]

        # Allocate the storage row before inserting the domain so
        # ``disks[0].storage_id`` is populated at insert time. That lets
        # engine restart cleanup trace the in-flight task via the
        # ``storage_ids`` index and avoid deleting a legitimately-in-progress
        # Creating domain.
        parent_storage_id = (
            template.get("create_dict", {})
            .get("hardware", {})
            .get("disks", [{}])[0]
            .get("storage_id")
        )
        if not parent_storage_id:
            raise Error(
                "precondition_required",
                f"Template {template['id']} has no storage_id on disk 0; "
                "cannot create via storage task.",
                description_code="template_no_storage_id",
            )
        pending_storage = Storage.new_dict(
            user_id=user_id,
            pool_usage="desktop",
            parent_id=parent_storage_id,
        )
        pending_storage.status_logs = [{"time": int(time.time()), "status": "created"}]
        create_dict["hardware"]["disks"][0].update(
            {
                "storage_id": pending_storage.id,
                "file": pending_storage.path,
            }
        )

        # Parse media info to have full media info (name and description) in create_dict
        try:
            create_dict = Helpers._parse_media_info(create_dict)
        except Exception:
            raise Error(
                "internal_server",
                "new_from_template: unable to parse media info.",
                description_code="unable_to_parse_media",
            )

        # If no deployment tag is provided, limit the hardware according to user hardware permissions
        if not deployment_tag_dict:
            payload = Helpers.gen_payload_from_user(user_id)
            create_dict = Quotas.limit_user_hardware_allowed(payload, create_dict)

        new_desktop = {
            "id": domain_id or str(uuid.uuid4()),
            "name": desktop_name,
            "description": desktop_description or template["description"],
            "kind": "desktop",
            "user": user_id,
            "username": user["username"],
            "status": DesktopStatusEnum.creating.value,
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "icon": template.get("icon", ""),
            "image": image or template.get("image"),
            "server": False,
            # A template derived from a from-media desktop may have
            # no ``os`` yet (engine writes it on first start) — don't
            # crash here; the engine will backfill.
            "os": template.get("os", ""),
            "guest_properties": guest_properties,
            "create_dict": {**create_dict, **{"origin": template["id"]}},
            "hypervisors_pools": template["hypervisors_pools"],
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "accessed": int(time.time()),
            "persistent": True,
            "forced_hyp": template.get("forced_hyp", False),
            "favourite_hyp": template.get("favourite_hyp", False),
            "from_template": template["id"],
            # Ancestor chain: template's own chain plus the template itself
            # as the immediate parent. Required for the
            # ``get_all(template_id, index="parents")`` lookups used by
            # template-disable cascade, deployment stats and recycle-bin
            # dependant purges.
            "parents": (template.get("parents") or []) + [template["id"]],
            "tag": False,
            "tag_visible": False,
            "booking_id": False,
        }
        if deployment_tag_dict:
            new_desktop = {**new_desktop, **deployment_tag_dict}

        # Convert the memory to bytes. Must be after the limit hardware since the quota is checked in GB
        create_dict["hardware"]["memory"] = int(
            create_dict["hardware"]["memory"] * 1048576
        )

        # Validate new_desktop using Pydantic
        try:
            valid_desktop = DesktopFromTemplate(**new_desktop).model_dump(
                mode="json", exclude_unset=True
            )
        except Exception as e:
            raise Error(
                "bad_request",
                "new_from_template: Invalid desktop data",
                traceback.format_exc(),
                description_code="invalid_desktop_data",
            )
        if insert:
            if soft:
                with cls._rdb_context():
                    r.table("domains").insert(valid_desktop, durability="soft").run(
                        cls._rdb_connection
                    )
            else:
                with cls._rdb_context():
                    r.table("domains").insert(valid_desktop).run(cls._rdb_connection)

            pending_storage.enqueue_disk_creation_chain_for_domain(
                domain_id=valid_desktop["id"],
            )
        if image:
            image_data = image
            # ``domain_id`` is the optional pre-allocated id passed by
            # callers that insert themselves (``insert=False``); for the
            # default ``insert=True`` path the row id we just wrote is
            # ``valid_desktop["id"]``. Picking it up here avoids the
            # ``r.table('domains').get(None)`` ReqlNonExistenceError that
            # turned every persistent-from-template create with an
            # ``image`` payload into a 500 (the Vue 3 client always
            # ships ``image`` in its create body).
            target_id = domain_id or valid_desktop["id"]
            if not image_data.get("file"):
                Cards.update(target_id, image_data["id"], image_data["type"])
            else:
                Cards.upload(target_id, image_data)
        return new_desktop

    @classmethod
    def desktops_stop(
        cls,
        desktops_ids,
        force=False,
        include_shutting_down=True,
        batch_size=20,
        wait_seconds=1,
        update_accessed=True,
    ):
        warnings.warn(
            "duplicate of isardvdi_common.helpers.desktop_events.DesktopEvents.desktops_stop"
        )
        # TODO(separate-common-classes): duplicate of isardvdi_common.helpers.desktop_events DesktopEvents.desktops_stop
        action = "stop"
        try:
            status_updates = []

            if include_shutting_down:
                status_updates.append(
                    (
                        DesktopStatusEnum.shutting_down.value,
                        DesktopStatusEnum.stopping.value,
                    )
                )
            if force:
                status_updates.append(
                    (DesktopStatusEnum.started.value, DesktopStatusEnum.stopping.value)
                )
            else:
                status_updates.append(
                    (
                        DesktopStatusEnum.started.value,
                        DesktopStatusEnum.shutting_down.value,
                    )
                )

            update_data = {}
            if update_accessed:
                update_data["accessed"] = int(time.time())

            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                keys = [["desktop", d_id] for d_id in batch_ids]
                for current_status, new_status in status_updates:
                    update_data["status"] = new_status
                    # Use Pydantic validation for updates
                    update_data = {
                        k: v for k, v in update_data.items() if v is not None
                    }
                    valid_domain = DomainStatus(**update_data).model_dump(
                        exclude_unset=True
                    )

                    with cls._rdb_context():
                        r.table("domains").get_all(*keys, index="kind_ids").filter(
                            {"status": current_status}
                        ).update(valid_domain).run(cls._rdb_connection)
                time.sleep(wait_seconds)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def parse_domain_update(cls, domain_id, new_data, admin_or_manager=False):
        domain = Caches.get_document("domains", domain_id)
        if not domain:
            raise Error(
                "not_found",
                "Not found domain to be updated",
                traceback.format_exc(),
                description="not_found",
            )
        new_domain = {}

        if admin_or_manager:
            if "forced_hyp" in new_data and new_data.get("forced_hyp") != domain.get(
                "forced_hyp"
            ):
                new_domain["forced_hyp"] = new_data.get("forced_hyp")
            if "favourite_hyp" in new_data and new_data.get(
                "favourite_hyp"
            ) != domain.get("favourite_hyp"):
                new_domain["favourite_hyp"] = new_data.get("favourite_hyp")
            if "server" in new_data and new_data.get("server") != domain.get("server"):
                new_domain = {
                    **new_domain,
                    **{
                        "server": new_data.get("server"),
                    },
                }
            if (
                (domain.get("server") or "server" in new_data)
                and "server_autostart" in new_data
                and new_data.get("server_autostart") != domain.get("server_autostart")
            ):
                new_domain = {
                    **new_domain,
                    **{
                        "server_autostart": new_data.get("server_autostart"),
                    },
                }
            if "xml" in new_data and new_data.get("xml") != domain.get("xml"):
                new_domain = {
                    **new_domain,
                    **{
                        "status": DesktopStatusEnum.updating.value,
                        "xml": new_data["xml"],
                    },
                }

        if "name" in new_data and new_data.get("name") != domain.get("name"):
            new_domain["name"] = new_data.get("name")
        if "description" in new_data and new_data.get("description") != domain.get(
            "description"
        ):
            new_domain["description"] = new_data.get("description")

        if new_data.get("guest_properties") and new_data.get(
            "guest_properties"
        ) != domain.get("guest_properties"):
            new_domain["guest_properties"] = {
                **new_data["guest_properties"],
                **{"viewers": r.literal(new_data["guest_properties"].pop("viewers"))},
            }

        if new_data.get("hardware") and new_data.get("hardware") != domain.get(
            "hardware"
        ):
            if new_data["hardware"].get("virtualization_nested"):
                new_data["hardware"]["virtualization_nested"] = new_data["hardware"][
                    "virtualization_nested"
                ]
            if new_data["hardware"].get("memory"):
                new_data["hardware"]["memory"] = int(
                    new_data["hardware"]["memory"] * 1048576
                )
            if new_data["hardware"].get("disk_bus"):
                disk_bus = (
                    new_data["hardware"]["disk_bus"]
                    if new_data["hardware"]["disk_bus"] != "default"
                    else "virtio"
                )
                new_data["hardware"] = {
                    **new_data["hardware"],
                    **{
                        "disks": [
                            {
                                **domain["create_dict"]["hardware"]["disks"][0],
                                **{"bus": disk_bus},
                            }
                        ]
                    },
                }

            if new_data["hardware"].get("interfaces"):
                old_interfaces = [
                    interface["id"]
                    for interface in domain["create_dict"]["hardware"]["interfaces"]
                ]
                new_interfaces = new_data["hardware"].get("interfaces")
                if old_interfaces != new_interfaces:
                    interfaces = []
                    for new_interface in new_interfaces:
                        interfaces.append(
                            {
                                "id": new_interface,
                                "mac": next(
                                    (
                                        item["mac"]
                                        for item in domain["create_dict"]["hardware"][
                                            "interfaces"
                                        ]
                                        if item["id"] == new_interface
                                    ),
                                    Helpers.gen_new_mac(),
                                ),
                            }
                        )
                    new_data["hardware"] = {
                        **new_data["hardware"],
                        **{"interfaces": r.literal(interfaces)},
                    }
                else:
                    new_data["hardware"].pop("interfaces", None)

            new_domain = {
                **new_domain,
                **{
                    "hardware": new_data["hardware"],
                },
            }

        if new_data.get("reservables"):
            if new_data["reservables"].get("vgpus") == ["None"]:
                new_data["reservables"]["vgpus"] = None
            new_domain = {
                **new_domain,
                **{
                    "create_dict": {
                        "reservables": new_data["reservables"],
                    },
                },
            }

        # Only flip to Updating for states that need the engine to
        # rebuild XML before next boot. For running-side states
        # (Started, Paused, Stopping, ...) the new create_dict is
        # persisted and will be picked up on next start; flipping
        # mid-run would leave the row stuck because
        # DomainsChangesThread.run only catches Stopped|Failed|
        # Downloaded → Updating.
        if domain.get("status") in ("Stopped", "Failed", "Downloaded"):
            new_domain = {
                **new_domain,
                **{
                    "status": DesktopStatusEnum.updating.value,
                },
            }

        return new_domain

    @classmethod
    @cached(cache=TTLCache(maxsize=50, ttl=30))
    def get_domain_group_and_category_name(cls, domain_id):
        with cls._rdb_context():
            group_and_category_names = (
                r.table(cls._rdb_table)
                .get(domain_id)
                .pluck("group", "category")
                .merge(
                    lambda domain: {
                        "group_name": r.table("groups").get(domain["group"])["name"],
                        "category_name": r.table("categories").get(domain["category"])[
                            "name"
                        ],
                    }
                )
                .run(cls._rdb_connection)
            )
        return group_and_category_names

    @classmethod
    def get_user_desktops(
        cls,
        user_id,
    ):
        with cls._rdb_context():
            desktops = (
                r.table(cls._rdb_table)
                .get_all(["desktop", user_id], index="kind_user")
                .order_by(r.desc("accessed"))
                .pluck(
                    [
                        "id",
                        "name",
                        "icon",
                        "image",
                        "user",
                        "group",
                        "category",
                        "status",
                        "description",
                        "parents",
                        "persistent",
                        "os",
                        "guest_properties",
                        "tag",
                        "tag_visible",
                        {"viewer": {"guest_ip", "passwd"}},
                        {
                            "create_dict": {
                                "hardware": ["interfaces", "videos", "disks"],
                                "reservables": True,
                            }
                        },
                        "server",
                        "progress",
                        "booking_id",
                        "scheduled",
                        "tag",
                        "current_action",
                    ]
                )
                .merge(
                    lambda domain: {
                        "bastion_targets": r.table("targets")
                        .get_all(domain["id"], index="desktop_id")
                        .pluck(
                            [
                                "id",
                                "http",
                                "ssh",
                                "domain",
                            ]
                        )
                        .coerce_to("array")
                    }
                )
                .run(cls._rdb_connection)
            )
            return [
                cls._parse_desktop(desktop)
                for desktop in desktops
                if not desktop.get("tag")
                or desktop.get("tag")
                and desktop.get("tag_visible")
            ]

    @classmethod
    def get_desktop(cls, desktop_id):
        with cls._rdb_context():
            desktop = (
                r.table(cls._rdb_table)
                .get(desktop_id)
                .pluck(
                    "image",
                    "name",
                    "id",
                    "status",
                    "kind",
                    "ip",
                    "description",
                    "tag_visible",
                    "accessed",
                    "user",
                )
                .run(cls._rdb_connection)
            )
        return desktop

    @classmethod
    def get_desktop_networks(cls, desktop_id):
        with cls._rdb_context():
            networks = (
                r.table("domains")
                .get(desktop_id)
                .pluck({"create_dict": {"hardware": {"interfaces": True}}})[
                    "create_dict"
                ]["hardware"]["interfaces"]
                .default([])
                .map(
                    lambda interface: interface.merge(
                        {
                            "name": r.table("interfaces")
                            .get(interface["id"])
                            .pluck("name")["name"]
                            .default("Unknown")
                        }
                    )
                )
                .run(cls._rdb_connection)
            )

        return networks

    @classmethod
    def get_desktop_details(cls, desktop_id):
        with cls._rdb_context():
            details = (
                r.table("domains")
                .get(desktop_id)
                .pluck(
                    "name",
                    "description",
                    "status",
                    "from_template",
                    {
                        "create_dict": {
                            "hardware": {
                                "interfaces": True,
                                "disks": True,
                                "boot_order": True,
                                "graphics": True,
                                "isos": True,
                                "floppies": True,
                                "memory": True,
                                "vcpus": True,
                                "videos": True,
                            },
                            "reservables": True,
                        },
                        "viewer": {"guest_ip": True, "passwd": True},
                        "guest_properties": {
                            "fullscreen": True,
                            "viewers": True,
                            "credentials": True,
                        },
                    },
                )
                .merge(
                    lambda desktop: {
                        "template": r.branch(
                            desktop["from_template"].default(None).ne(None),
                            {
                                "id": desktop["from_template"],
                                "name": r.table("domains")
                                .get(desktop["from_template"])
                                .default({})
                                .pluck("name")["name"]
                                .default("Unknown"),
                            },
                            None,
                        )
                    }
                )
                .run(cls._rdb_connection)
            )

        return details

    @classmethod
    def convert_template_to_desktop(cls, data):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.convert_template_to_desktop()_"""
        data = TemplateToDesktop(**data).model_dump()
        if not Domain.exists(data["template_id"]):
            raise Error(
                error="not_found", description=f"Domain {data['template_id']} not found"
            )
        template = Domain(data["template_id"])

        Helpers.check_user_duplicated_domain_name(
            data["name"], template.user, "desktop"
        )

        # TODO: Stop derivated running desktops

        ## check if template is a duplicate from another
        if TemplatesProcessed.is_duplicate(data["template_id"]):
            raise Error(
                "bad_request",
                "Template to desktop is a duplicate from another template",
                traceback.format_exc(),
                description_code="duplicate",
            )

        ## TODO: Permanently delete children if any

        ## TODO: Delete deployments if any

        desktop_data = cls.new_from_template(
            data["name"],
            template.description,
            data["template_id"],
            template.user,
            data["template_id"],
            insert=False,
        )
        # We are updating the domain
        new_desktop_data = {
            "status": "Stopped",
            "create_dict": {
                "hardware": {"disks": template.create_dict["hardware"]["disks"]}
            },
            "xml": template.xml,
            "parents": template.parents if template.parents else [],
        }
        # Merge the new data with the existing desktop_data
        desktop_data = {**desktop_data, **new_desktop_data}

        # Permanently delete dependants in recycle bin
        RecycleBinHelpers.delete_dependants_recycle_bin_from_templates(
            [data["template_id"]]
        )

        with cls._rdb_context():
            r.table("domains").get(data["template_id"]).update(desktop_data).run(
                cls._rdb_connection
            )

        # move template disk to desktops path
        if len(template.storages) > 0:
            try:
                # TODO: change to mv once properly implemented
                template.storages[0].rsync(
                    template.user,
                    template.storages[0].directory_path_as_usage("desktop"),
                    priority="low",
                )
            except Exception:
                raise Error(
                    "internal_server",
                    "Unable to move template disk to desktops path",
                    traceback.format_exc(),
                    description_code="unable_to_move_template_disk",
                )

        return desktop_data

    @classmethod
    def bulk_create_desktops(cls, payload, data):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.BulkDesktops()_"""
        selected = data["allowed"]
        users = []
        desktops = []

        template = Caches.get_document("domains", data["template_id"])
        if template is None:
            raise Error("not_found", "Template to create desktops not found")

        # We limit the hardware according to the payload of the user who is creating the desktops
        template["create_dict"] = Quotas.limit_user_hardware_allowed(
            payload, template["create_dict"]
        )

        if all(value is False for value in selected.values()):
            raise Error(
                "precondition_required",
                "Target users must be selected in order to create desktops",
                traceback.format_exc(),
            )
        if payload["role_id"] == "admin":
            if selected["roles"] is not False:
                if not selected["roles"]:
                    with cls._rdb_context():
                        selected["roles"] = list(
                            r.table("roles").pluck("id")["id"].run(cls._rdb_connection)
                        )
                for role in selected["roles"]:
                    with cls._rdb_context():
                        users_in_roles = list(
                            r.table("users")
                            .get_all(role, index="role")
                            .filter(lambda user: user["active"].eq(True))["id"]
                            .run(cls._rdb_connection)
                        )
                    users = users + users_in_roles

            if selected["categories"] is not False:
                if not selected["categories"]:
                    with cls._rdb_context():
                        selected["categories"] = (
                            r.table("categories")
                            .pluck("id")["id"]
                            .run(cls._rdb_connection)
                        )
                with cls._rdb_context():
                    users_in_categories = list(
                        r.table("users")
                        .get_all(r.args(selected["categories"]), index="category")
                        .filter(lambda user: user["active"].eq(True))["id"]
                        .run(cls._rdb_connection)
                    )
                users = users + users_in_categories

        if selected["groups"] is not False:
            if not selected["groups"]:
                query = r.table("groups")
                if payload["role_id"] == "manager":
                    query = query.get_all(
                        payload["category_id"], index="parent_category"
                    )
                with cls._rdb_context():
                    selected["groups"] = query["id"].run(cls._rdb_connection)
            with cls._rdb_context():
                users_in_groups = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="group")
                    .filter(lambda user: user["active"].eq(True))["id"]
                    .run(cls._rdb_connection)
                )

            with cls._rdb_context():
                users_in_secondary_groups = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="secondary_groups")
                    .filter(lambda user: user["active"].eq(True))["id"]
                    .run(cls._rdb_connection)
                )
            users = users + users_in_groups + users_in_secondary_groups

        if selected["users"] is not False:
            if not selected["users"]:
                query = r.table("users")
                if payload["role_id"] == "manager":
                    query = query.get_all(payload["category_id"], index="category")
                with cls._rdb_context():
                    selected["users"] = list(
                        query.filter(lambda user: user["active"].eq(True))
                        .pluck("id")["id"]
                        .run(cls._rdb_connection)
                    )
            users = users + selected["users"]

        users = list(set(users))
        for user_id in users:
            Helpers.check_user_duplicated_domain_name(data["name"], user_id)
            Quotas.desktop_create(user_id)

        template["create_dict"]["hardware"]["interfaces"] = [
            i["id"] for i in template["create_dict"]["hardware"].get("interfaces", [])
        ]
        for user_id in users:
            desktop_data = {
                "name": data["name"],
                "description": data["description"],
                "template_id": data["template_id"],
                "hardware": template["create_dict"]["hardware"],
                "guest_properties": template["guest_properties"],
                "image": template["image"],
            }
            desktop_data = DesktopFromTemplate(**desktop_data).model_dump()

            cls.new_from_template(
                desktop_data["name"],
                desktop_data["description"],
                desktop_data["template_id"],
                user_id,
                desktop_data["id"],
                image=desktop_data["image"],
                soft=True,
                ignore_allowed_hardware=True,
            )

            desktops.append(
                {
                    "id": desktop_data["id"],
                    "name": desktop_data["name"],
                    "user": user_id,
                }
            )

        return desktops

    @classmethod
    def new_from_media(cls, payload, data):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.NewFromMedia()_"""
        with cls._rdb_context():
            username = (
                r.table("users")
                .get(payload["user_id"])
                .pluck("username")["username"]
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            xml = r.table("virt_install").get(data["xml_id"]).run(cls._rdb_connection)
        if not xml:
            raise Error(
                "not_found",
                "Not found virt install xml id",
                traceback.format_exc(),
                description_code="not_found",
            )
        with cls._rdb_context():
            media = r.table("media").get(data["media_id"]).run(cls._rdb_connection)
        if not media:
            raise Error(
                "not_found",
                "Not found media id",
                traceback.format_exc(),
                description_code="not_found",
            )

        with cls._rdb_context():
            graphics = [
                g["id"]
                for g in r.table("graphics")
                .get_all(r.args(data["hardware"]["graphics"]))
                .run(cls._rdb_connection)
            ]
        if not len(graphics):
            raise Error(
                "not_found",
                "Not found graphics ids",
                traceback.format_exc(),
                description_code="not_found",
            )

        with cls._rdb_context():
            videos = [
                v["id"]
                for v in r.table("videos")
                .get_all(r.args(data["hardware"]["videos"]))
                .run(cls._rdb_connection)
            ]
        if not len(videos):
            raise Error(
                "not_found",
                "Not found videos ids",
                traceback.format_exc(),
                description_code="not_found",
            )

        with cls._rdb_context():
            interfaces = [
                i["id"]
                for i in r.table("interfaces")
                .get_all(r.args(data["hardware"]["interfaces"]))
                .run(cls._rdb_connection)
            ]
        if len(data["hardware"]["interfaces"]) != len(interfaces):
            raise Error(
                "not_found",
                "Not found interface id",
                traceback.format_exc(),
                description_code="not_found",
            )
        data["hardware"]["interfaces"] = [
            {"id": interface, "mac": Helpers.gen_new_mac()}
            for interface in data["hardware"]["interfaces"]
        ]

        if data["hardware"].get("disk_size"):
            disks = [
                {
                    "bus": data["hardware"]["disk_bus"],
                    "extension": "qcow2",
                    "size": str(data["hardware"]["disk_size"]) + "G",
                }
            ]
        else:
            disks = []

        # Allocate the scratch storage up-front so engine restart cleanup
        # can trace the in-flight task via storage_ids. ISO-only desktops
        # (no disk_size, disks=[]) skip this — they have no qcow2 to
        # create.
        pending_storage = None
        pending_size = None
        if disks:
            pending_size = disks[0]["size"]
            pending_storage = Storage.new_dict(
                user_id=payload["user_id"],
                pool_usage="desktop",
                parent_id=None,
            )
            pending_storage.status_logs = [
                {"time": int(time.time()), "status": "created"}
            ]
            disks[0].update(
                {
                    "storage_id": pending_storage.id,
                    "file": pending_storage.path,
                }
            )

        if data["hardware"].get("reservables", {"vgpus": None}).get("vgpus") == [
            "None"
        ]:
            data["hardware"]["reservables"]["vgpus"] = None

        domain = {
            "id": data["id"],
            "name": data["name"],
            "description": data["description"],
            "kind": "desktop",
            "status": "CreatingDiskFromScratch",
            "detail": "Creating desktop from existing disk and checking if it is valid (can start)",
            "user": payload["user_id"],
            "username": username,
            "category": payload["category_id"],
            "group": payload["group_id"],
            "server": False,
            "xml": None,
            "icon": (
                "fa-circle-o"
                if data["kind"] == "iso"
                else "fa-disk-o" if data["kind"] == "file" else "fa-floppy-o"
            ),
            "image": Cards.get_domain_stock_card(data["id"]),
            "os": "win",
            "guest_properties": data.get(
                "guest_properties", default_guest_properties()
            ),
            "hypervisors_pools": ["default"],
            "accessed": int(time.time()),
            "persistent": True,
            "forced_hyp": data["forced_hyp"],
            "favourite_hyp": data["favourite_hyp"],
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
            "create_dict": {
                "create_from_virt_install_xml": xml["id"],
                "hardware": {
                    "virtualization_nested": False,
                    "disks": disks,
                    "disk_bus": data["hardware"]["disk_bus"],
                    "isos": [{"id": media["id"]}],
                    "floppies": [],
                    "boot_order": data["hardware"]["boot_order"],
                    "graphics": graphics,
                    "videos": videos,
                    "interfaces": data["hardware"]["interfaces"],
                    "memory": int(data["hardware"]["memory"]),
                    "vcpus": int(data["hardware"]["vcpus"]),
                    "qos_disk_id": False,
                },
                "reservables": data["hardware"]["reservables"],
            },
            "tag": False,
            "tag_visible": False,
            "tag_desktop_id": False,
            "booking_id": False,
        }

        res = Quotas.limit_user_hardware_allowed(payload, domain["create_dict"])
        if res["limited_hardware"]:
            raise Error(
                "bad_request",
                "Unauthorized hardware items: " + str(res["limited_hardware"]),
                traceback.format_exc(),
            )
        domain["create_dict"]["hardware"]["memory"] = int(
            data["hardware"]["memory"] * 1048576
        )
        with cls._rdb_context():
            r.table("domains").insert(domain).run(cls._rdb_connection)

        if pending_storage is not None:
            pending_storage.enqueue_disk_creation_chain_for_domain(
                domain_id=domain["id"],
                size=pending_size,
            )
        return domain["id"]

    @classmethod
    def update_desktop(
        cls, desktop_id, desktop_data, admin_or_manager=False, bulk=False
    ):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.Update()_"""
        desktops = desktop_id if bulk else [desktop_id]
        for d in desktops:
            if desktop_data.get("image"):
                image_data = desktop_data.pop("image")

                if not image_data.get("file"):
                    Cards.update(d, image_data["id"], image_data["type"])
                else:
                    Cards.upload(d, image_data)

            data = copy.deepcopy(desktop_data)
            desktop = cls.parse_domain_update(d, data, admin_or_manager)
            domain = Caches.get_document("domains", d)

            if desktop_data.get("reservables", {}).get("vgpus", []) != domain.get(
                "create_dict"
            ).get("reservables", {}).get("vgpus", []):
                # Delete booking when the vGPU profile is changed
                Bookings.delete_item_bookings("desktop", d)

            update_payload = {**desktop}
            # Only refresh ``create_dict.hardware`` when the edit
            # actually carried a hardware change. Always nesting
            # ``{"create_dict": {"hardware": desktop.get("hardware")}}``
            # wiped the live hardware to None on hardware-less edits
            # (forced_hyp/name/description/...), and the engine then
            # crashed in ``resolve_hardware_from_create_dict`` with
            # ``argument of type 'NoneType' is not iterable``.
            if "hardware" in desktop:
                update_payload["create_dict"] = {"hardware": desktop["hardware"]}

            with cls._rdb_context():
                r.table("domains").get(d).update(update_payload).run(
                    cls._rdb_connection
                )

    @classmethod
    def update_desktop_reservables(cls, desktop_id, reservables):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.UpdateReservables()_"""
        with cls._rdb_context():
            r.table("domains").get(desktop_id).update(
                {"create_dict": {"reservables": reservables}}
            ).run(cls._rdb_connection)

    @classmethod
    def check_viewers(cls, data, domain):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.check_viewers()_"""
        if data.get("hardware") is None:
            data["hardware"] = {}
        if data.get("guest_properties") is None:
            data["guest_properties"] = {}
        if data.get("guest_properties", {}).get("viewers") == None:
            data["guest_properties"] = domain["guest_properties"]
        elif not data.get("guest_properties", {}).get("viewers"):
            raise Error(
                "bad_request",
                "At least one viewer must be selected.",
                traceback.format_exc(),
                description_code="one_viewer_minimum",
            )
        hardware = {}
        if not data.get("hardware", {}).get("videos") or not data.get(
            "hardware", {}
        ).get("interfaces"):
            viewers_hardware = {}
            if not data.get("hardware", {}).get("videos"):
                viewers_hardware["videos"] = domain["create_dict"]["hardware"]["videos"]
            else:
                viewers_hardware["videos"] = data["hardware"]["videos"]

            if data.get("hardware", {}).get("interfaces") is None:
                data["hardware"] = {
                    "interfaces": [
                        interface["id"]
                        for interface in domain["create_dict"]["hardware"]["interfaces"]
                    ]
                }
                viewers_hardware["interfaces"] = [
                    interface["id"]
                    for interface in domain["create_dict"]["hardware"]["interfaces"]
                ]
            else:
                viewers_hardware["interfaces"] = data["hardware"]["interfaces"]

            hardware = viewers_hardware
        else:
            hardware = data["hardware"]

        viewers = data["guest_properties"]["viewers"]

        if (
            viewers.get("file_rdpgw")
            or viewers.get("browser_rdp")
            or viewers.get("file_rdpvpn")
        ) and (
            "wireguard" not in hardware["interfaces"]
            or hardware.get("interfaces") == []
        ):
            raise Error(
                "bad_request",
                "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                traceback.format_exc(),
            )

        if "none" in hardware["videos"] and (
            viewers.get("file_spice")
            or viewers.get("browser_vnc")
            or not (
                viewers.get("file_rdpgw")
                or viewers.get("browser_rdp")
                or viewers.get("file_rdpvpn")
            )
        ):
            raise Error(
                "bad_request",
                "'Only GPU' mode only works with RDP viewers. Please remove non-RDP viewers or choose another video option",
                traceback.format_exc(),
                description_code="only_works_rdp",
            )

        return data

    @classmethod
    def check_current_plan(cls, payload, desktop_id):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.check_current_plan()_"""
        fromDate = datetime.now(timezone.utc)
        toDate = fromDate + timedelta(minutes=cls.MAX_BOOKING_TIME)
        fromDate = fromDate.strftime("%Y-%m-%dT%H:%M%z")
        toDate = toDate.strftime("%Y-%m-%dT%H:%M%z")
        current_plan = BookingsProcessed.get_item_bookings(
            payload,
            fromDate,
            toDate,
            "desktop",
            desktop_id,
            "availability",
        )
        if not current_plan or current_plan[0]["start"] > fromDate:
            desktop = Caches.get_document("domains", desktop_id)
            if desktop.get("tag"):
                raise Error(
                    "precondition_required",
                    "The deployment desktop reservable does not match the current plan, its deployment must be booked in order to use it",
                    description_code="needs_deployment_booking",
                )
            else:
                raise Error(
                    "precondition_required",
                    "The desktop reservable does not match the current plan",
                    description_code="current_plan_doesnt_match",
                )

        return current_plan

    @classmethod
    def check_max_booking_date(cls, payload, desktop_id):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.check_max_booking_date()_"""
        current_plan = cls.check_current_plan(payload, desktop_id)
        # First check the users priority max time
        reservables, units, item_name = BookingsHelpers._get_reservables(
            "desktop", desktop_id
        )
        users_priority = ReservablesPlannerCompute.payload_priority(
            payload, reservables
        )
        if not users_priority["max_time"]:
            raise Error(
                "precondition_required",
                "Max time reached",
                description_code="bookings_max_time_reached",
            )
        priority = BookingsProcessed.get_min_profile_priority("desktop", desktop_id)

        forbid_time = priority["forbid_time"]
        if payload["role_id"] != "admin" and forbid_time < cls.MIN_AUTOBOOKING_TIME:
            raise Error(
                "precondition_required",
                "There's not enough advanced time to start the desktop",
                description_code="not_enough_advanced_time",
            )
        max_time = priority["max_time"]
        available_time = int(
            (
                datetime.strptime(
                    current_plan[0]["end"], "%Y-%m-%dT%H:%M%z"
                ).astimezone(timezone.utc)
                - datetime.now(timezone.utc)
            ).total_seconds()
            / 60
        )

        if payload["role_id"] == "admin":
            max_booking_time = min(max_time, available_time)
        else:
            max_booking_time = min(forbid_time, max_time, available_time)
        if max_booking_time >= cls.MIN_AUTOBOOKING_TIME:
            max_booking_time = min(max_booking_time, cls.MAX_BOOKING_TIME)

            max_booking_date = datetime.strftime(
                datetime.now(timezone.utc) + timedelta(minutes=max_booking_time),
                "%Y-%m-%dT%H:%M%z",
            )
            return max_booking_date
        else:
            desktop = Caches.get_document("domains", desktop_id)
            if desktop.get("tag"):
                raise Error(
                    "precondition_required",
                    "There's not enough advanced time to start the deployment desktop, its deployment must be booked in order to use it",
                    description_code="needs_deployment_booking",
                )
            raise Error(
                "precondition_required",
                "There's not enough time to start the desktop",
                description_code="not_enough_time_to_start",
            )

    @classmethod
    def validate_desktop_update(cls, data, domain_id):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.validate_desktop_update()_"""
        # Bypass the 10s TTL cache: status writers (engine state machine,
        # storage maintenance/ready cycle, core_worker promote-to-stopped) do
        # not invalidate this entry, so a stale "Started"/"Maintenance" read
        # spuriously fails the precondition right after a stop or a resize.
        desktop = Caches.get_document("domains", domain_id, invalidate=True)
        data["id"] = domain_id
        if data.get("name"):
            Helpers.check_user_duplicated_domain_name(
                data["name"], desktop["user"], desktop.get("kind"), data["id"]
            )
        if data.get("hardware") or data.get("guest_properties"):
            cls.check_viewers(data, desktop)
        if not "server" in data and desktop.get("status") not in ["Failed", "Stopped"]:
            raise Error(
                "precondition_required",
                "Desktops only can be edited when stopped or failed",
                traceback.format_exc(),
            )
        if (
            desktop.get("server_autostart")
            and ("server_autostart" not in data or "server" not in data)
            and desktop.get("status") != "Failed"
        ):
            raise Error(
                "precondition_required",
                "Autostart servers can't be edited",
                traceback.format_exc(),
            )

        if data.get("server_autostart") is True and (
            data.get("server") is False
            or (data.get("server") is None and not desktop.get("server"))
        ):
            raise Error(
                "precondition_required",
                "Non-server desktops can't be set to autostart",
                traceback.format_exc(),
            )

        if desktop.get("create_dict", {}).get("reservables", {}).get("vgpus") and (
            data.get("server")
        ):
            raise Error(
                "precondition_required",
                "Servers can not have a bookable item",
                traceback.format_exc(),
            )
        if data.get("reservables", {}).get("vgpus") and data[
            "reservables"
        ] != desktop.get("create_dict", {}).get("reservables"):
            with cls._rdb_context():
                vgpu_profiles = list(
                    r.table("reservables_vgpus")["id"].run(cls._rdb_connection)
                )
            for desktop_profile in data["reservables"].get("vgpus"):
                if desktop_profile not in vgpu_profiles:
                    raise Error("not_found", "vGPU not found: " + desktop_profile)

    @classmethod
    def admin_change_status(cls, current_status, target_status):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.change_status()_"""
        with cls._rdb_context():
            r.table("domains").get_all(
                ["desktop", current_status], index="kind_status"
            ).update({"status": target_status}).run(cls._rdb_connection)

    @classmethod
    def admin_change_status_category(cls, category, current_status, target_status):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.change_status_category()_"""
        with cls._rdb_context():
            r.table("domains").get_all(
                ["desktop", current_status, category], index="kind_status_category"
            ).update({"status": target_status}).run(cls._rdb_connection)

    @classmethod
    def update_storage(cls, domain_id, new_storage_id):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.update_storage()_"""
        with cls._rdb_context():
            domain = r.table("domains").get(domain_id).run(cls._rdb_connection)
        if not domain:
            raise Error(
                "not_found",
                "Domain not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        if domain["status"] not in ["Stopped", "Maintenance"]:
            raise Error(
                "precondition_required",
                "Desktop must be stopped to change storage",
                traceback.format_exc(),
            )
        if domain["kind"] == "desktop":
            with cls._rdb_context():
                r.table("domains").get(domain_id).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "disks": [
                                    {
                                        "storage_id": new_storage_id,
                                    }
                                ]
                            }
                        }
                    }
                ).run(cls._rdb_connection)

        return domain_id

    @classmethod
    def set_desktops_maintenance(
        cls, payload, storage_id, action, domains=None, batch_size=250
    ):
        """_From api/libv2/api_desktops_persistent.py ApiDesktopsPersistent.set_desktops_maintenance()_"""
        if domains == None:
            domains = StorageProcessed.get_storage_derivatives(storage_id)

        for domain_id in domains:
            Helpers.owns_domain_id(payload, domain_id)

        for i in range(0, len(domains), batch_size):
            batch_ids = domains[i : i + batch_size]
            with cls._rdb_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"status": "Maintenance", "current_action": action}
                ).run(cls._rdb_connection)

    @classmethod
    def get_unused_desktops(cls, from_deployments=False):
        """_From api/libv2/api_desktops_persistent.py get_unused_desktops()_

        Retrieve a list of unused desktops that have not been accessed considering the specified cutoff time defined in the unused_item_timeout table.

        :return: A list of desktops that have not been accessed within the specified cutoff_time.
        :rtype: list
        """

        desktops = []
        start = absolute_start = time.time()

        with cls._rdb_context():
            users_with_desktops = list(
                r.table("domains")
                .get_all(
                    r.args(
                        [
                            ["desktop", "Stopped"],
                            ["desktop", "Maintenance"],
                            ["desktop", "Failed"],
                        ]
                    ),
                    index="kind_status",
                )
                .pluck("user")
                .distinct()["user"]
                .run(cls._rdb_connection)
            )

        log.debug(
            "api_desktops_persistent get unused desktops: Retrieved users with desktops in %s seconds",
            time.time() - start,
        )

        for user in users_with_desktops:
            start = time.time()
            try:
                payload = Helpers.gen_payload_from_user(user)
                user_timeout_rule = get_unused_item_timeout(
                    payload, "send_unused_desktops_to_recycle_bin"
                )
            except TypeError as e:
                # If the user does not exist then send to the recycle bin all of its deployments
                log.error(
                    "api_desktops_persistent get unused desktops: Could not generate payload for user %s",
                    user,
                )
                user_timeout_rule = {"cutoff_time": 0}

            if user_timeout_rule is False or user_timeout_rule["cutoff_time"] is None:
                continue
            log.debug(
                "api_desktops_persistent get unused desktops: User %s applied rule %s",
                user,
                user_timeout_rule,
            )
            cutoff_time = timedelta(days=user_timeout_rule["cutoff_time"] * 30)
            cutoff_timestamp = (datetime.now() - cutoff_time).timestamp()
            query = r.row["accessed"] < cutoff_timestamp
            if not from_deployments:
                query = query & (r.row["tag"] == False)

            with cls._rdb_context():
                user_desktops = list(
                    r.table("domains")
                    .get_all(
                        r.args(
                            [
                                ["desktop", "Stopped", user],
                                ["desktop", "Maintenance", user],
                                ["desktop", "Failed", user],
                            ]
                        ),
                        index="kind_status_user",
                    )
                    .filter(query)
                    .pluck("id", "user", "name", "accessed")
                    .run(cls._rdb_connection)
                )
            log.debug(
                "api_desktops_persistent get unused desktops: Retrieved user unused desktops and applied rule in %s seconds",
                time.time() - start,
            )
            desktops += user_desktops

        log.debug(
            "api_desktops_persistent get unused desktops: Retrieved users with desktops in %s seconds",
            time.time() - absolute_start,
        )

        return desktops

    # @classmethod
    # def get_user_desktops(cls, user_id):
    #     """_From api/libv2/api_users.py ApiUsers.Desktops()_"""
    #     if not User.exists(user_id):
    #         raise Error(
    #             "not_found",
    #             "User not found",
    #             traceback.format_exc(),
    #             description_code="user_not_found",
    #         )

    #     try:
    #         with cls._rdb_context():
    #             desktops = list(
    #                 r.table("domains")
    #                 .get_all(["desktop", user_id], index="kind_user")
    #                 .order_by("name")
    #                 .pluck(
    #                     [
    #                         "id",
    #                         "name",
    #                         "icon",
    #                         "image",
    #                         "user",
    #                         "group",
    #                         "category",
    #                         "status",
    #                         "description",
    #                         "parents",
    #                         "persistent",
    #                         "os",
    #                         "guest_properties",
    #                         "tag",
    #                         "tag_visible",
    #                         {"viewer": {"guest_ip", "passwd"}},
    #                         {
    #                             "create_dict": {
    #                                 "hardware": ["interfaces", "videos", "disks"],
    #                                 "reservables": True,
    #                             }
    #                         },
    #                         "server",
    #                         "progress",
    #                         "booking_id",
    #                         "scheduled",
    #                         "tag",
    #                         "current_action",
    #                     ]
    #                 )
    #                 .merge(
    #                     lambda domain: {
    #                         "bastion_targets": r.table("targets")
    #                         .get_all(domain["id"], index="desktop_id")
    #                         .pluck(
    #                             [
    #                                 "id",
    #                                 "http",
    #                                 "ssh",
    #                                 "domain",
    #                             ]
    #                         )
    #                         .coerce_to("array")
    #                     }
    #                 )
    #                 .run(cls._rdb_connection)
    #             )
    #         return [
    #             cls._parse_desktop(desktop)
    #             for desktop in desktops
    #             if not desktop.get("tag")
    #             or desktop.get("tag")
    #             and desktop.get("tag_visible")
    #         ]

    #     except:
    #         raise Error(
    #             "internal_server",
    #             "Internal server error",
    #             traceback.format_exc(),
    #             description_code="generic_error",
    #         )

    @classmethod
    def stop_user_desktops(cls, user_id: str, force: bool = None):
        try:
            # Since this statuses are already stopping the desktop they will be ignored
            ignored_statuses = {
                DesktopStatusEnum.stopped.value,
                DesktopStatusEnum.stopping.value,
                DesktopStatusEnum.shutting_down.value,
                DesktopStatusEnum.failed.value,
            }

            # If forcing then the shutting down desktops will be set to stopping too
            if force:
                ignored_statuses.discard(DesktopStatusEnum.shutting_down.value)

            valid_statuses = {
                status.value
                for status in DesktopStatusEnum
                if status not in ignored_statuses
            }
            compound_keys = [["desktop", status, user_id] for status in valid_statuses]

            new_status = (
                DesktopStatusEnum.stopping.value
                if force
                else DesktopStatusEnum.shutting_down.value
            )

            with cls._rdb_context():
                result = (
                    r.table(cls._rdb_table)
                    .get_all(*compound_keys, index="kind_status_user")
                    .update(
                        {
                            "status": new_status,
                            "accessed": int(time.time()),
                        },
                        return_changes=True,
                    )
                    .run(cls._rdb_connection)
                )

            # Return the IDs of the desktops that were updated
            return [change["new_val"]["id"] for change in result.get("changes", [])]

        except Exception:
            raise Error(
                "internal_server",
                "Internal server error",
                traceback.format_exc(),
                description_code="generic_error",
            )
