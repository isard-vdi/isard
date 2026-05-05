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


from uuid import uuid4

from api.services.error import Error
from api.services.users import UsersService
from cachetools import TTLCache, cached
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.api_admin import ApiAdmin as CommonApiAdmin
from isardvdi_common.lib.domains.desktops.desktops import (
    DesktopsProcessed as CommonDesktops,
)
from isardvdi_common.lib.domains.domains import DomainsProcessed as CommonDomains
from isardvdi_common.lib.domains.templates.templates import (
    TemplatesProcessed as CommonTemplates,
)
from isardvdi_common.lib.media.media import MediaProcessed as CommonMedia
from isardvdi_common.lib.storage.storage import StorageProcessed as CommonStorage
from isardvdi_common.models.boots import Boot as RethinkBoot
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.interfaces import Interface as RethinkInterfaces
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.models.videos import Video as RethinkVideos

templates_cache = TTLCache(maxsize=1, ttl=360)


def clear_templates_cache() -> None:
    """Invalidate the admin template list cache.

    Called from write paths that mutate a template's user-visible fields
    (create/duplicate/delete, enable, owner change, allowed change), so
    the next GET returns fresh data instead of the 6 min TTL'd response.
    """
    templates_cache.clear()


class TemplateService:
    @staticmethod
    @cached(cache=templates_cache)
    def get_all_templates() -> list[dict]:
        return CommonTemplates.get_template_with_user_info()

    @staticmethod
    def get_user_templates(user_id: str) -> list[dict]:
        return CommonTemplates.get_user_templates(user_id)

    @classmethod
    def get_user_templates_paginated(
        cls,
        user_id: str,
        start_after: str | None = None,
        page_size: int = 10,
        sort_field: str = "accessed",
        sort_order: str = "desc",
        search: str | None = None,
        search_field: str = "name",
        filters: dict | None = None,
    ) -> dict:
        """
        Get all templates for a specific user.
        Returns a paginated list of templates.
        """
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )

        if sort_field == "accessed":
            index = "kind_user_accessed"
        index_value = ["template", user_id]

        templates = RethinkDomain.get_templates(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
        )

        total = RethinkDomain.query_count_raw(
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
        )

        return {
            "rows": templates,
            "total": total,
        }

    @staticmethod
    def get_user_allowed_templates_flat(payload: dict, kind: str) -> list[dict]:
        """Return a flat list of templates the user can use.

        ``kind`` controls the filter:
          * ``"shared"``: only templates shared with the user (not owned) and
            enabled — dropdown semantics.
          * ``"all"`` (or anything else): all enabled templates the user can
            see (owned + shared).
        """
        if not RethinkUser.exists(payload["user_id"]):
            raise Error(
                "not_found",
                f"User with ID {payload['user_id']} not found",
                description_code="not_found",
            )
        # Use the declarative ``exclude_owner_user_id`` /
        # ``require_enabled`` kwargs on ``get_items_allowed`` —
        # services delegate ReQL construction to ``_common`` (cf.
        # ``test_no_rethink_in_services`` architectural pin). The
        # "shared" filter is: enabled AND NOT owned by the caller.
        kwargs = {"require_enabled": True}
        only_in_allowed = False
        if kind == "shared":
            kwargs["exclude_owner_user_id"] = payload["user_id"]
            only_in_allowed = True
        return Alloweds.get_items_allowed(
            payload,
            table="domains",
            query_pluck=[
                "id",
                "name",
                "kind",
                "category",
                "group",
                "icon",
                "image",
                "user",
                "description",
                "status",
                "enabled",
            ],
            index_key="kind",
            index_value="template",
            order="name",
            query_merge=True,
            only_in_allowed=only_in_allowed,
            **kwargs,
        )

    @staticmethod
    def get_user_shared_templates(payload: dict) -> list[dict]:
        if not RethinkUser.exists(payload["user_id"]):
            raise Error(
                "not_found",
                f"User with ID {payload['user_id']} not found",
                description_code="not_found",
            )

        return Alloweds.get_items_allowed(
            payload,
            table=RethinkDomain._rdb_table,
            query_pluck=[
                "id",
                "name",
                "image",
                "description",
                "category",
                "group",
                "accessed",
                "user",
                "username",
                "allowed",
            ],
            index_key="template_enabled",
            index_value=["template", True],
            order="name",
            only_in_allowed=True,
        )

    @classmethod
    def get_user_allowed_templates(
        cls,
        user_id: str,
        user_category: str,
        user_group: str,
        user_role: str,
        start_after: str | None = None,
        page_size: int = 10,
        sort_field: str = "accessed",
        sort_order: str = "desc",
        search: str | None = None,
        search_field: str = "name",
    ) -> list[dict]:
        if not RethinkUser.exists(user_id):
            raise Error(
                "not_found",
                f"User with ID {user_id} not found",
                description_code="not_found",
            )

        # Determine index strategy based on user role
        if user_role == "admin":
            if sort_field == "accessed":
                # Admin users can access all templates, ignoring if enabled or not
                index = "kind_accessed"
            index_value = ["template"]
        else:
            if sort_field == "accessed":
                # Non-admin users can only access enabled templates
                index = "enabled_kind_accessed"
            index_value = [True, "template"]

        # Delegate complex filtering logic to the domain model
        templates = RethinkDomain.get_user_allowed_templates(
            user_id=user_id,
            user_category=user_category,
            user_group=user_group,
            user_role=user_role,
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
        )

        return templates

    @staticmethod
    def create_template(payload: dict, data: dict) -> dict:
        Helpers.check_user_duplicated_domain_name(
            name=data["name"],
            user_id=payload["user_id"],
            kind="template",
        )

        result = CommonTemplates.new_template(
            user_id=payload["user_id"],
            template_id=str(uuid4()),
            name=data["name"],
            desktop_id=data["desktop_id"],
            allowed=data["allowed"],
            description=data["description"],
            enabled=data["enabled"],
        )
        clear_templates_cache()
        return result

    @staticmethod
    def toggle_enabled(template_id: str) -> None:
        template = RethinkDomain(template_id)
        template.enabled = not template.enabled
        clear_templates_cache()

    @staticmethod
    def set_enabled(template_id: str, enabled: bool, payload: dict) -> dict:
        """Enable or disable a template.

        Side effects:

        * On enable: ``Quotas.template_create(user_id)`` raises if the
          user has hit their template quota — preventing a quota bypass.
        * On disable: ``TemplatesProcessed.delete_non_persistent_desktops``
          flags every non-persistent desktop derived from this template
          as ``ForceDeleting`` so the engine cleans them up — without
          this, ephemeral desktops outlive their (now-unusable) template.

        Then writes the new ``enabled`` value via the existing
        ``TemplatesProcessed.update_template`` common helper.
        """
        if enabled:
            Quotas.template_create(payload["user_id"])
        else:
            CommonTemplates.delete_non_persistent_desktops(template_id)
        result = CommonTemplates.update_template(template_id, {"enabled": enabled})
        clear_templates_cache()
        return result

    @staticmethod
    def change_owner(payload: dict, template_id: str, new_user_id: str) -> None:
        """Reassign a template to a different user.

        Mirrors v3 ``api_v3_template_change_owner``
        (``api/views/CommonView.py:200``). Both ``ownsUserId`` and
        ``ownsDomainId`` are enforced before the DB flip.
        """
        Helpers.owns_user_id(payload=payload, user_id=new_user_id)
        Helpers.owns_domain_id(payload=payload, domain_id=template_id)
        Helpers.change_owner_template(user_id=new_user_id, template_id=template_id)
        clear_templates_cache()

    @staticmethod
    def duplicate_template(payload: dict, template_id: str, data: dict) -> dict:
        Helpers.check_user_duplicated_domain_name(
            name=data["name"],
            user_id=payload["user_id"],
            kind="template",
        )

        result = CommonTemplates.duplicate_template(
            payload,
            template_id,
            data["name"],
            data["allowed"],
            description=data["description"],
            enabled=data["enabled"],
        )
        clear_templates_cache()
        return result

    @staticmethod
    def delete_template(payload: dict, template_id: str) -> dict:
        # Block managers from deleting templates with cross-category derivatives
        if payload["role_id"] == "manager":
            derivatives = CommonTemplates.list_derivative_categories(template_id)
            cross_cat = [
                d for d in derivatives if d.get("category") != payload["category_id"]
            ]
            if cross_cat:
                raise Error(
                    "forbidden",
                    "Template has derivatives in other categories. Contact an administrator.",
                    description_code="template_cross_category_derivatives",
                )
        result = DesktopEvents.templates_delete(template_id, payload["user_id"])
        clear_templates_cache()
        return result

    @staticmethod
    def convert_to_desktop(
        payload: dict, template_id: str, name: str | None = None
    ) -> dict:
        name = name or RethinkDomain(template_id).name

        Helpers.check_user_duplicated_domain_name(
            name=name,
            user_id=payload["user_id"],
            kind="desktop",
            item_id=template_id,
        )

        result = CommonDesktops.convert_template_to_desktop(
            {
                "template_id": template_id,
                "name": name,
            }
        )
        clear_templates_cache()
        return result

    def get_template_allowed(template_id: str, category_id: str) -> dict:
        if not RethinkDomain.exists(template_id):
            raise Error(
                "not_found",
                f"Template with ID {template_id} not found.",
            )

        return {
            "selected": RethinkDomain.get(template_id)["allowed"],
            "available_groups": Alloweds.get_allowed_groups(category_id),
        }

    @staticmethod
    def update_template_allowed(template_id: str, allowed: dict) -> None:
        if not RethinkDomain.exists(template_id):
            raise Error(
                "not_found",
                f"Template with ID {template_id} not found.",
            )
        Alloweds.update_table_item_allowed(
            table="domains",
            item_id=template_id,
            allowed=allowed,
        )
        clear_templates_cache()

    @staticmethod
    def get_template_tree(template_id: str, payload: dict) -> dict:
        tree = CommonApiAdmin.get_template_tree_list(template_id, payload["user_id"])[0]

        derivates = CommonTemplates.check_children(payload, tree)
        derivates["is_duplicated"] = CommonTemplates.is_duplicate(template_id)

        deployments = CommonTemplates.get_deployments_with_template(
            template_id, return_username=True
        )
        derivates["deployments"] = []
        for dp in deployments:
            try:
                Helpers.owns_deployment_id(payload, dp["id"])
                derivates["deployments"].append(
                    {
                        "id": dp["id"],
                        "kind": "deployment",
                        "name": dp["name"],
                        "user": dp["username"],
                    }
                )
            except Exception:
                derivates["deployments"].append({})
                derivates["pending"] = True

        derivates["cross_category"] = CommonTemplates.has_cross_category_derivatives(
            template_id, payload["category_id"]
        )

        return derivates

    @staticmethod
    def get_template_details(template_id: str) -> dict:
        if not RethinkDomain.exists(template_id):
            raise Error(
                "not_found",
                f"Template with ID {template_id} not found",
                description_code="not_found",
            )
        details = CommonTemplates.get_template_details(template_id)
        boots_names = RethinkBoot.get_boots_names()
        videos_names = RethinkVideos.get_videos_names()
        interfaces_names = RethinkInterfaces.get_interfaces_names()
        parsed_details = {
            "name": details["name"],
            "description": details["description"],
            "ip": details.get("viewer", {}).get("guest_ip"),
            "vcpu": details["create_dict"]["hardware"].get("vcpus", 0),
            "memory": details["create_dict"]["hardware"].get("memory", 0)
            / (1024 * 1024),
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
            "disk_bus": details["create_dict"]["hardware"].get("disk_bus", ""),
            "videos": [
                {"id": v, "name": videos_names[v]}
                for v in details["create_dict"]["hardware"].get("videos", [])
            ],
            "interfaces": [
                {"id": i["id"], "name": interfaces_names[i["id"]]}
                for i in details["create_dict"]["hardware"].get("interfaces", [])
            ],
            "viewers": list(
                details.get("guest_properties", {}).get("viewers", {}).keys()
            ),
            "fullscreen": details.get("guest_properties", {}).get("fullscreen", False),
            "reservables": details["create_dict"].get("reservables", {"vgpus": None}),
            "credentials": details.get("credentials", {}),
        }

        if details["create_dict"]["hardware"].get("isos"):
            media_ids = [
                media["id"]
                for media in details["create_dict"]["hardware"].get("isos", [])
            ]
            parsed_details["isos"] = CommonMedia.get_medias_names(media_ids=media_ids)
        else:
            parsed_details["isos"] = None

        return parsed_details
