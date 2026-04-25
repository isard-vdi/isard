#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

import base64
import json
import logging as log
import os
import secrets
import time
import traceback
import urllib
import uuid
from datetime import datetime, timedelta
from typing import List, Literal, Optional
from uuid import uuid4

import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_base import PydanticBase, pydantic_optional
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_viewer import IsardViewer
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.models.category import Category
from isardvdi_common.models.group import Group
from pydantic import BaseModel
from pydantic.experimental.missing_sentinel import MISSING
from rethinkdb import r

from ..schemas.domains import *
from ..schemas.shared.allowed import Allowed
from ..schemas.shared.hardware import GuestProperties, Hardware
from ..schemas.shared.image import Image
from . import storage

isard_viewer = IsardViewer()


class DomainModel(PydanticBase):
    accessed: float | None = None
    allowed: Allowed | None = None
    booking_id: str | bool | None = False
    category: str
    create_dict: CreateDictDomain | None = None
    description: str | None = ""
    detail: str | None = ""
    disks_info: list[dict] | None = None
    favourite_hyp: bool | list[str] | None = False
    forced_hyp: bool | list[str] | None = False
    from_template: str | None = None
    group: str
    guest_properties: GuestProperties | None = None
    hardware: Hardware | None = None
    hardware_from_xml: dict | None = None
    history_domain: list[dict] | None = []
    hw_stats: dict | None = None
    hyp_started: str | bool | None = False
    hypervisors_pools: list[str] | None = None
    icon: str | None = None
    image: Image | None = None
    kind: DomainKindEnum
    name: str
    options: dict | None = None
    os: str | None = None
    parents: list[str] | None = None
    persistent: bool
    server: bool | str | None = None
    status: DesktopStatusEnum
    tag: str | bool | None = False
    tag_desktop_id: str | bool | None = False
    tag_visible: bool | None = False
    user: str | None = None
    username: str | None = None
    xml: str | None = None
    id: str = str(uuid4())


@pydantic_optional
class DomainUpdateModel(DomainModel):
    pass


# TODO: Use a Pydantic model before all inserts/updates to the DB.
#       If none exists, create one in ..schemas/domains.py (can inherit DomainModel)
#       For updates, use .model_dump(exclude_unset=True); # for inserts, use .model_dump().
#       Modify existing functions only—don’t create new ones.


class Domain(RethinkCustomBase):
    """
    Manage Domain Objects

    Use constructor with keyword arguments to create new Domain Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Domain Object.
    """

    _rdb_table = "domains"

    @property
    def storages(self):
        """
        Returns domain Storages.
        """
        return [
            storage.Storage(disk["storage_id"])
            for disk in self.create_dict.get("hardware", {}).get("disks", [])
            if "storage_id" in disk and storage.Storage.exists(disk["storage_id"])
        ]

    @property
    def storage_ready(self):
        """
        Returns True if storages are ready, otherwise False
        """
        for storage in self.storages:
            if storage.status != "ready":
                return False
        return True

    @classmethod
    def get_with_storage(cls, storage):
        """
        Get domains with specific Storage
        """
        return cls.get_index([storage.id], index="storage_ids")

    def toggle_user_visible(self):
        """
        Returns True if the domain is visible to the user, otherwise False
        """
        if not self.tag:
            raise ValueError("Domain is not from a deployment")
        self.tag_visible = not self.tag_visible

    @classmethod
    def get_desktops(
        cls,
        start_after: str | int = None,
        page_size: int = 20,
        sort_order: str = "desc",
        index: str = "kind_user_accessed",
        index_value: List = ["desktop"],
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
    ) -> List[dict]:
        return cls.query_paginated_raw(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
            # TODO: Evaluate if python or RethinkDB is better for this
            # Currently, it is done in python through the _parse_desktop function
            # merge_fn=lambda desktop: {
            #     "group_name": (
            #         r.table(GroupsProcessed._rdb_table)
            #         .get(desktop["group"])
            #         .pluck("name")
            #         .default({"name": "DELETED"})["name"]
            #     ),
            #     "viewers": desktop["guest_properties"]["viewers"].keys(),
            #     "reservables": desktop["create_dict"]["reservables"].default(
            #         {"vgpus": None}
            #     ),
            #     "create_dict": r.literal(),
            #     "guest_properties": r.literal(),
            #     "ip": desktop["viewer"]["guest_ip"].default(None),
            #     "booking": {
            #         "id": desktop["booking_id"].default(None),
            #         "required": desktop["reservables"]["vgpus"] is not None,
            #     },
            # },
            pluck=[
                "id",
                "accessed",
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
            ],
        )

    @classmethod
    def get_all_desktops(
        cls,
        start_after: str | int = None,
        page_size: int = 20,
        sort_order: str = "desc",
        index: str = "kind",
        index_value: List = ["desktop"],
        search: Optional[str] = None,
        search_field: str = "name",
        # filters: Optional[dict] = None,
    ) -> List[dict]:
        return cls.query_paginated_raw(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            # filters=filters,
            merge_fn=lambda desktop: {
                "category_name": r.table(Category._rdb_table)
                .get(desktop["category"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
                "group_name": (
                    r.table(Group._rdb_table)
                    .get(desktop["group"])
                    .pluck("name")
                    .default({"name": "DELETED"})["name"]
                ),
                "reservables": desktop["create_dict"]["reservables"].default(
                    {"vgpus": None}
                ),
                "create_dict": r.literal(),
                "guest_properties": r.literal(),
            },
            pluck=[
                "id",
                {"image": ["id", "type", "url"]},
                "name",
                "status",
                "ip",
                "description",
                "tag_visible",
                "accessed",
                "user_id",
                "viewers",
                "category_name",
                "group_name",
                "guest_properties",
            ],
        )

    @classmethod
    def get_templates(
        cls,
        start_after: str | int = None,
        page_size: int = 20,
        sort_order: str = "desc",
        index: str = "kind_user_accessed",
        index_value: List = ["template"],
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
    ) -> List[dict]:
        return cls.query_paginated_raw(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=filters,
            pluck=["id", "name", "image", "description"],
        )

    @classmethod
    def get_user_allowed_templates(
        cls,
        user_id: str,
        user_category: str,
        user_group: str,
        user_role: str,
        start_after: str | int = None,
        page_size: int = 20,
        sort_order: str = "desc",
        index: str = "enabled_kind_accessed",
        index_value: List = [True, DomainKindEnum.template.value],
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
    ) -> List[dict]:

        build_shared_templates_filter = Alloweds.build_shared_items_filter(
            user_role=user_role,
            user_category=user_category,
            user_group=user_group,
            user_id=user_id,
            consider_user_role=True,
        )

        # Combine with additional filters if provided
        combined_filters = None
        if filters:

            def combined_filter_func(template):
                return r.and_(
                    build_shared_templates_filter(template),
                    filters(template) if callable(filters) else filters,
                )

            combined_filters = combined_filter_func
        else:
            combined_filters = build_shared_templates_filter

        rows = cls.query_paginated_raw(
            start_after=start_after,
            page_size=page_size,
            sort_order=sort_order,
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=combined_filters,
            pluck=[
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
            merge_fn=lambda template: {
                "category_name": r.table("categories")
                .get(template["category"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
                "group_name": r.table("groups")
                .get(template["group"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
                "user_name": r.table("users")
                .get(template["user"])
                .pluck("name")
                .default({"name": "DELETED"})["name"],
            },
        )

        total = cls.query_count_raw(
            index=index,
            index_value=index_value,
            search=search,
            search_field=search_field,
            filters=combined_filters,
        )

        return {
            "rows": rows,
            "total": total,
        }

    @classmethod
    @cached(cache=TTLCache(maxsize=200, ttl=10))
    def get_cached_available_domain_storage_pool_id(cls, domain_id):
        # Used to virtualize the storage pool for the domain
        # No virtualitzation for a disabled storage_pool should be available
        if Domain.exists(domain_id):
            domain_obj = Domain(domain_id)
        else:
            raise Error(
                "not_found",
                f"Domain {domain_id} not found",
                description_code="not_found",
            )
        if not domain_obj.storage_ready:
            raise Error(
                "precondition_required",
                f"Domain {domain_id} storage not ready",
                description_code="desktop_storage_not_ready",
            )
        domain_storage_objs = domain_obj.storages
        if len(domain_storage_objs) == 0:
            raise Error(
                "precondition_required",
                f"Domain {domain_id} storage not found",
                description_code="storage_not_found",
            )
        domain_storage_pool_obj = domain_storage_objs[0].pool
        if not domain_storage_pool_obj:
            ## This can only happen if we created it in an storage pool that has been deleted
            # Default storage pool is used if no storage pool matches the domain storage_id,
            # but likely will fail
            # This can lead to allowing a domain to be started in any hypervisor with default storage pool
            virt_pool_id = DEFAULT_STORAGE_POOL_ID
        else:
            virt_pool_id = domain_storage_pool_obj.id

        # Check if the virt_pool is enabled
        log.debug(f"Checking if virt_pool {virt_pool_id} is enabled")
        if virt_pool_id not in [
            esp["id"] for esp in Caches.get_cached_enabled_virt_pools()
        ]:
            raise Error(
                "precondition_required",
                f"Virt pool {virt_pool_id} is disabled so no storage pool available for domain {domain_id}",
                description_code="storage_pool_disabled",
            )
        return virt_pool_id
