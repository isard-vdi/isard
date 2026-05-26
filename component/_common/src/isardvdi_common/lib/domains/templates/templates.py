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

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.cards import Cards
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.xml_compression import compress_xml, decompress_xml
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.user import User
from isardvdi_common.schemas.domains import TemplateCreation
from isardvdi_common.schemas.shared.allowed import Allowed
from rethinkdb import r


class TemplatesProcessed(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def get_template_with_user_info(cls, category=None):
        """
        Get template domains with user info according to category
        """
        query = r.table(cls._rdb_table).get_all("template", index="kind")

        if category:
            query = query.filter(lambda domain: domain["category"] == category)

        query = query.map(
            lambda domain: domain.merge(
                {
                    "user_data": r.table("users").get(domain["user"]).default({}),
                    "group_data": r.table("groups").get(domain["group"]).default({}),
                    "category_data": r.table("categories")
                    .get(domain["category"])
                    .default({}),
                }
            )
        )

        query = query.map(
            lambda domain: domain.merge(
                {
                    "create_dict": domain["create_dict"].merge(
                        {
                            "hardware": domain["create_dict"]["hardware"].merge(
                                {
                                    "isos": r.branch(
                                        domain["create_dict"]["hardware"].has_fields(
                                            "isos"
                                        ),
                                        domain["create_dict"]["hardware"]["isos"].map(
                                            lambda iso: r.branch(
                                                iso.has_fields("name"),
                                                iso,
                                                r.table("media")
                                                .get(iso["id"])
                                                .default({})
                                                .pluck("id", "name"),
                                            )
                                        ),
                                        [],
                                    )
                                }
                            )
                        }
                    )
                }
            )
        )

        query = query.map(
            lambda domain: domain.merge(
                {
                    "user": domain["user_data"]["username"],
                    "user_name": domain["user_data"]["name"],
                    "group": domain["group_data"]["id"],
                    "category": domain["category_data"]["id"],
                    "description": domain["description"],
                    "image": domain["image"],
                    "id": domain["id"],
                    "name": domain["name"],
                }
            )
        )
        query = query.pluck(
            "allowed",
            "id",
            "create_dict",
            "guest_properties",
            "name",
            "user",
            "user_name",
            "group",
            "category",
            "description",
            "image",
        )

        with cls._rdb_context():
            templates = list(query.run(cls._rdb_connection))

        for template in templates:
            template["create_dict"]["hardware"]["interfaces"] = [
                i["id"]
                for i in template["create_dict"]
                .get("hardware", {})
                .get("interfaces", [])
            ]

        return templates

    @classmethod
    def is_duplicate(cls, template_id):
        """_From api/libv2/api_templates.py is_duplicate()_"""
        with cls._rdb_context():
            return (
                r.table("domains")
                .get(template_id)
                .has_fields("duplicate_parent_template")
                .run(cls._rdb_connection)
            )

    @classmethod
    def check_template_status(cls, template_id=None, template=None):
        """_From api/libv2/api_desktops_persistent.py check_template_status()_"""
        if template_id:
            template = Caches.get_document("templates", template_id)

        if template["status"] == "Failed":
            raise Error(
                "bad_request",
                "Can't create a desktop with a Failed template.",
                traceback.format_exc(),
                description_code="template_failed",
            )

    @classmethod
    def new_template(
        cls,
        user_id,
        template_id,
        name,
        desktop_id,
        allowed={"roles": False, "categories": False, "groups": False, "users": False},
        description="",
        enabled=False,
    ):
        """_From api/src/api/libv2/api_templates.py ApiTemplates.New()_"""
        try:
            with cls._rdb_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "category", "group", "provider", "username", "uid")
                    .run(cls._rdb_connection)
                )
        except Exception:
            raise Error(
                "not_found",
                "User not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        with cls._rdb_context():
            desktop = r.table("domains").get(desktop_id).run(cls._rdb_connection)
        if desktop == None:
            raise Error(
                "not_found",
                "Desktop not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        if desktop.get("status") != "Stopped":
            raise Error(
                "precondition_required",
                "To create a template, status desktop must be Stopped",
                traceback.format_exc(),
            )
        if desktop.get("server"):
            raise Error(
                "internal_server",
                "Can't create a template from a server",
                traceback.format_exc(),
            )
        if not Domain(desktop.get("id")).storage_ready:
            raise Error(
                error="precondition_required",
                description="Desktop storages are not ready",
                description_code="desktop_storage_not_ready",
            )

        # Resolve the desktop's existing storage row. The chain rewrites
        # its on-disk file from a base disk into an overlay backed by the
        # new template — the row stays bound to the desktop and its
        # ``parent`` is flipped to the template by the trailing
        # ``qemu_img_info_backing_chain`` -> ``storage_update`` pair.
        desktop_disks = (
            desktop.get("create_dict", {}).get("hardware", {}).get("disks") or []
        )
        if not desktop_disks:
            raise Error(
                "internal_server",
                "Desktop has no disks",
                traceback.format_exc(),
                description_code="desktop_no_disks",
            )
        if len(desktop_disks) > 1:
            # Legacy engine looped ``for i in range(1)`` — multi-disk
            # templates were never wired, and the apiv4 chain isn't
            # designed for them. Stay explicit until that lands.
            raise Error(
                "not_implemented",
                "Multi-disk templates are not supported",
                description_code="multi_disk_templates_unsupported",
            )
        desktop_storage_id = desktop_disks[0].get("storage_id")
        if not desktop_storage_id:
            raise Error(
                "internal_server",
                f"Desktop {desktop_id} has no storage_id on its first disk",
                description_code="desktop_disk_no_storage_id",
            )
        # Storage(...) goes through RethinkBase.__init__ which raises a
        # generic "Document with id <id> does not exist." Reframe it so
        # the message names both the desktop and the missing storage row
        # — otherwise a dangling create_dict.hardware.disks[].storage_id
        # surfaces as if the desktop itself were gone.
        if not Storage.exists(desktop_storage_id):
            raise Error(
                "not_found",
                f"Desktop {desktop_id} references storage {desktop_storage_id}, "
                "but no such row exists in the storage table",
                description_code="desktop_storage_missing",
            )
        desktop_storage = Storage(desktop_storage_id)
        if desktop_storage.status != "ready":
            raise Error(
                "precondition_required",
                f"Desktop storage is not ready (status={desktop_storage.status})",
                description_code="desktop_storage_not_ready",
            )

        # Pre-check the source storage's pending-task state BEFORE
        # allocating the template storage or inserting the template row.
        # ``Storage.create_task(blocking=True)`` runs this same check
        # later inside ``enqueue_template_creation_chain_from_desktop``;
        # by the time it raises, the template doc + template storage row
        # are already in the DB and never get cleaned up (orphans), so
        # every retry hits 409 on the orphan name and no chain ever runs.
        # Mirror the predicate here so we fail fast and leave nothing
        # behind.
        from isardvdi_common.models.task import Task

        if (
            desktop_storage.task
            and Task.exists(desktop_storage.task)
            and Task(desktop_storage.task).pending
        ):
            raise Error(
                "precondition_required",
                f"Desktop {desktop_id} has a pending storage task; "
                "please retry once it completes",
                description_code="storage_pending_task",
            )

        if Domain.exists(template_id):
            raise Error(
                "conflict",
                "Template id already exists: " + str(template_id),
                description_code="template_already_exists" + str(template_id),
            )

        # Allocate the new template Storage row. ``pool_usage="template"``
        # routes the file under the pool's templates dir AND sets
        # ``perms=["r"]`` (read-only) — matches the engine's legacy
        # ``create_storage(..., perms=["r"])`` call. Inheriting
        # ``desktop_storage.parent`` keeps the new template at the same
        # backing-chain depth the desktop disk currently sits at.
        template_storage = Storage.new_dict(
            user_id=user_id,
            pool_usage="template",
            parent_id=desktop_storage.parent,
        )
        template_storage.status_logs = [{"time": int(time.time()), "status": "created"}]

        hardware = desktop["create_dict"]["hardware"]
        # Pre-wire the template disk with both ``storage_id`` and
        # ``file`` *before* domain insert — same invariant
        # ``DesktopService.create_from_media`` enforces, so apiv4 restart
        # cleanup can trace the in-flight chain via the
        # ``domains.storage_ids`` multi-index. The lineage-marker
        # ``parent`` (path string) is intentionally NOT written: nothing
        # on this branch reads it (engine resolves the backing chain
        # from ``storage.parent`` directly in ``domain_xml.py:1602``,
        # the chain cascade walks ``domain.parents`` UUIDs, and the
        # qcow2 file header is the on-disk ground truth). Leaving it
        # unset keeps the field None per the optional Disk schema.
        hardware["disks"] = [
            {
                "extension": "qcow2",
                "storage_id": template_storage.id,
                "file": template_storage.path,
            }
        ]

        create_dict = Helpers._parse_media_info({"hardware": hardware})
        create_dict["origin"] = desktop_id
        # ``CreateDictDomainTemplate`` requires ``personal_vlans`` (no
        # default), so the template row must carry it forward from the
        # source desktop. The default-False fallback covers very old
        # desktops that pre-date the field landing in ``CreateDictDomain``.
        create_dict["personal_vlans"] = desktop["create_dict"].get(
            "personal_vlans", False
        )

        if desktop["create_dict"].get("reservables"):
            create_dict = {
                **create_dict,
                **{"reservables": desktop["create_dict"]["reservables"]},
            }
        create_dict["hardware"]["qos_disk_id"] = False

        template_dict = {
            "accessed": int(time.time()),
            "id": template_id,
            "name": name,
            "description": description,
            "kind": "template",
            "user": user["id"],
            "username": user["username"],
            "status": "CreatingTemplate",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            # desktops created via ``from-media`` never have ``xml`` /
            # ``os`` populated by the apiv4 service — those fields are
            # written by the engine when the domain first starts. Make
            # the template inherit whatever the desktop has, or leave
            # empty so the engine regenerates on first start.
            "xml": decompress_xml(desktop.get("xml")) or "",
            "icon": desktop.get("icon", ""),
            "image": Cards.get_domain_stock_card(template_id),
            "os": desktop.get("os", ""),
            "guest_properties": desktop["guest_properties"],
            "create_dict": create_dict,
            "hypervisors_pools": ["default"],
            "parents": desktop["parents"] if "parents" in desktop.keys() else [],
            "allowed": Allowed(**allowed).model_dump(mode="json"),
            "enabled": enabled,
            "tag": False,
            "tag_name": False,
            "tag_visible": False,
            "favourite_hyp": desktop.get("favourite_hyp", False),
            "forced_hyp": desktop.get("forced_hyp", False),
        }

        # Validate the template_dict before insert. Mirrors the
        # desktop-side validation in ``DesktopsProcessed.new_from_template``
        # (desktops.py around the ``DesktopFromTemplate(**new_desktop)``
        # call). Without this, any future field-drop slips into the
        # ``domains`` table and only blows up on the next
        # "create desktop from this template" — exactly how the
        # ``personal_vlans`` regression on 2026-04-27 went undetected.
        try:
            valid_template = TemplateCreation(**template_dict).model_dump(
                mode="json", exclude_unset=True
            )
        except Exception:
            raise Error(
                "bad_request",
                "new_template: Invalid template data",
                traceback.format_exc(),
                description_code="invalid_template_data",
            )

        if "xml" in valid_template:
            valid_template["xml"] = compress_xml(valid_template["xml"])
        new_desktop_parents = (desktop.get("parents") or []) + [template_id]
        with cls._rdb_context():
            r.table("domains").insert(valid_template).run(cls._rdb_connection)
            r.table("domains").get(desktop_id).update(
                {
                    "status": "CreatingTemplate",
                    "parents": new_desktop_parents,
                }
            ).run(cls._rdb_connection)

        # Chain enqueue can still raise after the pre-check above on a
        # tight race (e.g. another concurrent click slips a task in
        # between). Roll back the template doc + template storage so
        # the next user click gets a clean retry instead of a 409 on the
        # orphan name (and an unrecoverable "Parent storage is not
        # ready" 428 on every subsequent derive attempt).
        try:
            desktop_storage.enqueue_template_creation_chain_from_desktop(
                desktop_id=desktop_id,
                template_id=template_id,
                template_storage_id=template_storage.id,
            )
        except Exception:
            with cls._rdb_context():
                r.table("domains").get(template_id).delete().run(cls._rdb_connection)
                r.table("storage").get(template_storage.id).delete().run(
                    cls._rdb_connection
                )
                r.table("domains").get(desktop_id).update(
                    {"status": "Stopped", "parents": desktop.get("parents") or []}
                ).run(cls._rdb_connection)
            raise

        return template_id

    @classmethod
    def duplicate_template(
        cls,
        payload,
        template_id,
        name,
        allowed={"roles": False, "categories": False, "groups": False, "users": False},
        description="",
        enabled=False,
    ):
        """_From api/src/api/libv2/api_templates.py ApiTemplates.Duplicate()_"""
        with cls._rdb_context():
            template = (
                r.table("domains")
                .get(template_id)
                .without("id", "history_domain")
                .run(cls._rdb_connection)
            )
        if not template:
            raise Error(
                "not_found",
                "Template id not found",
                traceback.format_exc(),
                description_code="not_found",
            )

        template = {**template, **Helpers.get_user_data(payload["user_id"])}
        template["name"] = name
        template["description"] = description
        template["allowed"] = Allowed(**allowed).model_dump(mode="json")
        template["enabled"] = enabled
        template["status"] = "Stopped"
        template["accessed"] = int(time.time())
        template["parents"] = template.get("parents", [])
        template["duplicate_parent_template"] = template.get(
            "duplicate_parent_template", template_id
        )

        try:
            with cls._rdb_context():
                new_template_id = (
                    # TODO(move-domains-to-common): pydantic
                    r.table("domains")
                    .insert(template)["generated_keys"][0]
                    .run(cls._rdb_connection)
                )
        except Exception:
            raise Error(
                "internal_server",
                "Unable to insert duplicate template",
                traceback.format_exc(),
            )
        return new_template_id

    @classmethod
    def get_template(cls, template_id):
        """_From api/libv2/api_templates.py ApiTemplates.Get()_"""
        template = Caches.get_document(
            "domains",
            template_id,
            [
                "id",
                "name",
                "icon",
                "image",
                "description",
                "allowed",
                "guest_properties",
                "create_dict",
                "status",
                "kind",
                "user",
                "category",
            ],
        )
        if template is None:
            raise Error("not_found", "Template id not found", traceback.format_exc())
        return template

    @classmethod
    def update_template(cls, template_id, data):
        """_From api/libv2/api_templates.py ApiTemplates.UpdateTemplate()_"""
        with cls._rdb_context():
            template = r.table("domains").get(template_id).run(cls._rdb_connection)
        if not template:
            raise Error(
                "not_found",
                "Unable to update inexistent template",
                traceback.format_exc(),
                description_code="not_found",
            )
        if template and template["kind"] == "template":
            if "xml" in data:
                data["xml"] = compress_xml(data["xml"])
            with cls._rdb_context():
                r.table("domains").get(template_id).update(data).run(
                    cls._rdb_connection
                )
            with cls._rdb_context():
                template = r.table("domains").get(template_id).run(cls._rdb_connection)
            return template
        raise Error(
            "conflict",
            "Unable to update enable in a non template kind domain",
            traceback.format_exc(),
            description_code="unable_to_update",
        )

    @classmethod
    def delete_non_persistent_desktops(cls, template_id):
        """_From api/libv2/api_templates.py delete_desktops_non_persistent()_

        Cascade-flag every non-persistent desktop derived from the given
        template to ``ForceDeleting`` so the engine cleans them up. Used
        when an admin disables a template — without this, ephemeral
        desktops keep running forever even though their template is no
        longer usable.
        """
        with cls._rdb_context():
            r.table("domains").get_all(template_id, index="parents").filter(
                {"persistent": False}
            ).update({"status": "ForceDeleting"}).run(cls._rdb_connection)

    @classmethod
    def check_children(cls, payload, domain_tree):
        """_From api/libv2/api_templates.py ApiTemplates.check_children()_"""
        try:
            Helpers.owns_domain_id(payload, domain_tree["id"])
            domains = [
                {
                    "id": domain_tree["id"],
                    "kind": domain_tree["kind"],
                    "name": domain_tree["title"],
                    "user": domain_tree["user"],
                }
            ]
            deployments = []
            pending = False
        except Exception:
            domains = [{}]
            deployments = []
            pending = True

        for item in domain_tree["children"]:
            item_result = {
                "id": item["id"],
                "kind": item["kind"],
                "name": item["title"],
                "user": item["user"],
            }

            if item.get("children"):
                child_result = cls.check_children(payload, item)
                domains.extend(child_result["domains"])
                pending = pending or child_result["pending"]
            else:
                if item["kind"] == "deployment":
                    try:
                        Helpers.owns_deployment_id(payload, item["id"], True)
                        deployments.append(item_result)
                    except Exception:
                        pending = True
                        deployments.append({})
                else:
                    try:
                        Helpers.owns_domain_id(payload, item["id"])
                        domains.append(item_result)
                    except Exception:
                        pending = True
                        domains.append({})

        return {"deployments": deployments, "domains": domains, "pending": pending}

    @classmethod
    def get_deployments_with_template(cls, template_id, return_username=False):
        """_From api/libv2/api_templates.py ApiTemplates.get_deployments_with_template()_"""
        query = r.table("deployments").get_all(template_id, index="template")
        if return_username:
            with cls._rdb_context():
                return list(
                    query.merge(
                        lambda deployment: {
                            "username": r.table("users").get(deployment["user"])[
                                "username"
                            ]
                        }
                    ).run(cls._rdb_connection)
                )
        else:
            with cls._rdb_context():
                return list(query.run(cls._rdb_connection))

    @classmethod
    def get_user_templates(cls, user_id):
        """_From api/libv2/api_users.py ApiUsers.Templates()_"""
        if not User.exists(user_id):
            raise Error(
                "not_found",
                "User not found",
                traceback.format_exc(),
                description_code="user_not_found",
            )

        try:
            with cls._rdb_context():
                templates = (
                    r.table("domains")
                    .get_all(["template", user_id], index="kind_user")
                    .order_by("name")
                    .pluck(
                        {
                            "id",
                            "name",
                            "allowed",
                            "enabled",
                            "kind",
                            "category",
                            "group",
                            "icon",
                            "image",
                            "user",
                            "description",
                            "status",
                            # Surfaced for templates in CreatingTemplate
                            # status so the UI can render a progress bar
                            # (written by ``move()`` during the chain's
                            # rsync branch).
                            "progress",
                        },
                        {"create_dict": {"hardware": {"disks": {"storage_id": True}}}},
                    )
                    .run(cls._rdb_connection)
                )

            return templates

        except Exception:
            raise Error(
                "internal_server", "Internal server error", traceback.format_exc()
            )

    @classmethod
    def get_template_details(cls, desktop_id):
        with cls._rdb_context():
            details = (
                r.table("domains")
                .get(desktop_id)
                .pluck(
                    "name",
                    "description",
                    {
                        "create_dict": {
                            "hardware": {
                                "interfaces": True,
                                "disks": True,
                                "boot_order": True,
                                "disk_bus": True,
                                "graphics": True,
                                "isos": True,
                                "memory": True,
                                "vcpus": True,
                                "videos": True,
                            },
                            "reservables": True,
                        },
                        "guest_properties": True,
                    },
                )
                .run(cls._rdb_connection)
            )

        return details

    @classmethod
    def list_derivative_categories(cls, template_id: str) -> list[dict]:
        """Return ``[{"category": <id>}, ...]`` for every domain that
        descends from ``template_id`` (via the ``parents`` index).

        Used by managers' delete-template guard: if any derivative
        sits in a category outside the manager's own, the operation
        is forbidden.
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(template_id, index="parents")
                .pluck("category")
                .run(cls._rdb_connection)
            )

    @classmethod
    def has_cross_category_derivatives(cls, template_id: str, category_id: str) -> bool:
        """Return ``True`` if ``template_id`` has any derivative in a
        category other than ``category_id``.

        Used to flag the template tree for managers (so the UI can
        warn that some derivatives are out of scope).
        """
        with cls._rdb_context():
            cross = list(
                r.table("domains")
                .get_all(template_id, index="parents")
                .filter(lambda d: d["category"] != category_id)
                .limit(1)
                .run(cls._rdb_connection)
            )
        return len(cross) > 0
