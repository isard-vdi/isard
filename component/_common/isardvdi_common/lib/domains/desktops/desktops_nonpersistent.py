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


import time
import traceback
import uuid

from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.desktop_nonpersistent_events import (
    DesktopNonpersistentEvents,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.scheduler import Scheduler
from isardvdi_common.lib.domains.disk_resolver import resolve_parent_disk
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed
from isardvdi_common.models.domain import DomainModel
from isardvdi_common.models.storage import Storage
from rethinkdb import r
from socketio import RedisManager

socketio = RedisManager(socketio_url(), write_only=True)


class DesktopsNonpersistentProcessed(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def new_desktop(cls, user_id, template_id, *, name=None, description=None):
        """_From api/libv2/api_desktops_nonpersistent.py ApiDesktopsNonPersistent.New()_"""
        with cls._rdb_context():
            if r.table("users").get(user_id).run(cls._rdb_connection) is None:
                raise Error("not_found", "User not found", traceback.format_exc())
        # Has a desktop with this template? Then return it (start it if stopped)
        with cls._rdb_context():
            desktops = list(
                r.db("isard")
                .table("domains")
                .get_all(user_id, index="user")
                .filter({"from_template": template_id, "persistent": False})
                .run(cls._rdb_connection)
            )
        if len(desktops) == 1:
            if desktops[0]["status"] == "Started":
                return desktops[0]["id"]
            HypervisorsProcessed.check_virt_storage_pool_availability(desktops[0]["id"])
            DesktopEvents.desktop_start(desktops[0]["id"], wait_seconds=1)
            Scheduler.add_desktop_timeouts(
                Helpers.gen_payload_from_user(user_id), desktops[0]["id"]
            )
            return desktops[0]["id"]

        # and get a new nonpersistent desktops from this template
        return cls._nonpersistent_desktop_create_and_start(
            user_id, template_id, name, description
        )

    @classmethod
    def delete_desktop(cls, desktop_id):
        """_From api/libv2/api_desktops_nonpersistent.py ApiDesktopsNonPersistent.Delete()_"""
        DesktopNonpersistentEvents.desktop_non_persistent_delete(desktop_id)

    @classmethod
    def _nonpersistent_desktop_create_and_start(
        cls, user_id, template_id, name=None, description=None
    ):
        """_From api/libv2/api_desktops_nonpersistent.py ApiDesktopsNonPersistent._nonpersistent_desktop_create_and_start()_"""
        with cls._rdb_context():
            user = r.table("users").get(user_id).run(cls._rdb_connection)
        if user == None:
            raise Error("not_found", "User not found", traceback.format_exc())
        HypervisorsProcessed.check_create_storage_pool_availability(
            user.get("category_id")
        )
        # Create the domain from that template
        desktop_id = cls._nonpersistent_desktop_from_tmpl(
            user_id, template_id, name, description
        )

        # Disk is created by engine and not ready yet, thus commented this check
        # check_virt_storage_pool_availability(desktop_id)
        DesktopEvents.desktop_start(desktop_id)
        payload = Helpers.gen_payload_from_user(user_id)
        Scheduler.add_desktop_timeouts(payload, desktop_id)
        return {"id": desktop_id}

    @classmethod
    def _nonpersistent_desktop_from_tmpl(
        cls, user_id, template_id, name=None, description=None
    ):
        """_From api/libv2/api_desktops_nonpersistent.py ApiDesktopsNonPersistent._nonpersistent_desktop_from_tmpl()_"""
        with cls._rdb_context():
            template = r.table("domains").get(template_id).run(cls._rdb_connection)
        if not template:
            raise Error("not_found", "Template not found", traceback.format_exc())
        with cls._rdb_context():
            user = r.table("users").get(user_id).run(cls._rdb_connection)
        if not user:
            raise Error("not_found", "NewNonPersistent: user id not found.")
        with cls._rdb_context():
            group = r.table("groups").get(user["group"]).run(cls._rdb_connection)
        if not group:
            raise Error("not_found", "NewNonPersistent: group id not found.")

        parent_disk = resolve_parent_disk(template)
        # Capture the template's parent storage id BEFORE the disks array
        # is replaced below — the storage-task chain needs it as backing
        # for the new storage, and overwriting first would hide it.
        parent_storage_id = (
            template.get("create_dict", {})
            .get("hardware", {})
            .get("disks", [{}])[0]
            .get("storage_id")
        )

        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]

        # Pre-allocate the storage so disks[0] already carries
        # storage_id/file at insert time. Engine restart cleanup needs
        # this to trace the in-flight task via the storage_ids index.
        if not parent_storage_id:
            raise Error(
                "precondition_required",
                f"Template {template_id} has no storage_id on disk 0; "
                "cannot create non-persistent desktop via storage task.",
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
        create_dict = Helpers._parse_media_info(create_dict)

        template["create_dict"]["hardware"]["interfaces"] = [
            i["id"] for i in template["create_dict"]["hardware"]["interfaces"]
        ]

        create_dict["hardware"] = {
            **template["create_dict"]["hardware"],
            **Helpers.parse_domain_insert(template["create_dict"])["hardware"],
        }

        # TODO: Evaluate reservables for non-persistent desktops, perhaps someday
        if create_dict.get("reservables", {}).get("vgpus"):
            raise Error(
                "bad_request",
                "Can't create temporal desktop from a template with a reservable",
                traceback.format_exc(),
                "temporal_new_reservable",
            )

        new_desktop = {
            "id": str(uuid.uuid4()),
            "name": name or template["name"],
            "description": description or template["description"],
            "kind": "desktop",
            "user": user_id,
            "username": user["username"],
            "status": "CreatingAndStarting",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": None,
            "icon": template.get("icon", ""),
            "image": template.get("image"),
            "server": False,
            # Templates derived from from-media desktops don't carry
            # ``os`` until the engine writes it on first start.
            "os": template.get("os", ""),
            "guest_properties": template["guest_properties"],
            "create_dict": {
                "hardware": create_dict["hardware"],
                "origin": template["id"],
            },
            "hypervisors_pools": template["hypervisors_pools"],
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "accessed": int(time.time()),
            "persistent": False,
            "from_template": template["id"],
            "tag": False,
        }

        # new_desktop = _validate_item("domains", new_desktop)

        new_desktop = DomainModel(
            **new_desktop,
        ).model_dump()

        # Preserve the CreatingAndStarting status (the one Creating* value
        # the frontend collapsing keeps) while flagging the domain for
        # engine's auto-start after libvirt define. Set after model_dump
        # because DomainModel drops unknown fields.
        new_desktop["start_after_created"] = True

        with cls._rdb_context():
            r.table("domains").insert(new_desktop).run(cls._rdb_connection)

        pending_storage.enqueue_disk_creation_chain_for_domain(
            domain_id=new_desktop["id"],
        )
        return new_desktop["id"]

    @classmethod
    def delete_template_desktops_non_persistent(cls, template_id):
        """_From api/libv2/api_templates.py delete_desktops_non_persistent()_"""
        with cls._rdb_context():
            r.table("domains").get_all(template_id, index="parents").filter(
                {"persistent": False}
            ).update({"status": "ForceDeleting"}).run(cls._rdb_connection)
