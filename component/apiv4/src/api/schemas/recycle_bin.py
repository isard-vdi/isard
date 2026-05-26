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

from enum import Enum
from typing import Optional

from isardvdi_common.schemas.recycle_bin import RecycleBinStatusEnum
from pydantic import BaseModel, Field

from .allowed import Allowed


class DeleteActionEnum(str, Enum):
    """Action to perform when deleting items."""

    recycle = "recycle"
    permanent = "permanent"


class OldEntriesActionEnum(str, Enum):
    """Action for old recycle bin entries cleanup."""

    delete = "delete"
    keep = "keep"


class RecycleBinCutoffTimeResponse(BaseModel):
    """Recycle bin cutoff time response model.

    Emits the value under both spellings: the apiv3 contract used
    ``recycle_bin_cuttoff_time`` (double-t typo) and the Vue 2
    frontend still reads it that way. Vue 3 and other Pythonic
    consumers expect the corrected ``recycle_bin_cutoff_time``.
    Returning both keeps both fronts working without a breaking
    change.
    """

    recycle_bin_cutoff_time: int
    recycle_bin_cuttoff_time: int


class RecycleBinResponse(BaseModel):
    accessed: float
    # System/external agents have no category/group/role (helpers/recycle_bin.py:1326-1332).
    agent_category_id: Optional[str] = None
    agent_category_name: Optional[str] = None
    agent_group_id: Optional[str] = None
    agent_group_name: Optional[str] = None
    agent_id: str
    agent_name: str
    agent_role: Optional[str] = None
    agent_type: str
    categories: list[dict]
    deployments: list[dict]
    desktops: list[dict]  # Simplified to handle complex desktop structure
    groups: list[dict]
    id: str
    item_name: str
    item_type: str
    logs: list[dict]  # Changed from 'last' to 'logs' to match mock data
    owner_category_id: str
    owner_category_name: str
    owner_group_id: str
    owner_group_name: str
    owner_id: str
    owner_name: str
    owner_role: str
    size: int
    status: RecycleBinStatusEnum
    storages: list[dict]
    targets: list[dict]
    tasks: Optional[list[dict]]  # Removed default value to fix ogen generation
    templates: list[dict]
    users: list[dict]


class RecycleBinLastAction(BaseModel):
    """Last action performed on recycle bin item"""

    action: str
    # System/external agents have no category/group/role (helpers/recycle_bin.py:1326-1332).
    agent_category_id: Optional[str] = None
    agent_category_name: Optional[str] = None
    agent_id: str
    agent_name: str
    agent_role: Optional[str] = None
    agent_type: str
    time: int


class RecycleBinEntry(BaseModel):
    accessed: float
    # System/external agents have no category/group/role (helpers/recycle_bin.py:1326-1332).
    agent_category_id: Optional[str] = None
    agent_category_name: Optional[str] = None
    agent_group_id: Optional[str] = None
    agent_group_name: Optional[str] = None
    agent_id: str
    agent_name: str
    agent_role: Optional[str] = None
    agent_type: str
    categories: int
    deployments: int
    desktops: int
    groups: int
    id: str
    item_name: str
    item_type: str
    last: Optional[RecycleBinLastAction]
    owner_category_id: str
    owner_category_name: str
    owner_group_id: str
    owner_group_name: str
    owner_id: str
    owner_name: str
    owner_role: str
    size: int
    status: RecycleBinStatusEnum
    storages: int
    targets: list[dict]
    templates: int
    users: int


class RecycleBinEntriesResponse(BaseModel):
    """List of recycle bin item counts"""

    entries: list[RecycleBinEntry]


class RecycleBinBulkRequest(BaseModel):
    """Request for bulk recycle bin operations."""

    recycle_bin_ids: list[str]


class RecycleBinBulkResponse(BaseModel):
    """Response for bulk recycle bin operations.

    The route handler is fire-and-forget — it schedules the per-id work
    on a background task and returns the list of ids it accepted. The
    pre-fix schema only had ``success`` / ``failed`` fields and the
    route's ``RecycleBinBulkResponse(recycle_bin_ids=ids)`` call had
    its kwarg silently dropped by Pydantic, so the wire response was
    always ``{success: [], failed: []}`` regardless of input. Replace
    with the canonical ``recycle_bin_ids`` echoing what was scheduled.
    """

    recycle_bin_ids: list[str] = []


class RecycleBinStatusResponse(BaseModel):
    """Recycle bin status overview."""

    total: int = 0
    by_status: dict = {}


class RecycleBinOldEntriesConfig(BaseModel):
    """Configuration for old entries cleanup."""

    max_time: Optional[int] = None
    action: Optional[str] = None


class RecycleBinSetDefaultDeleteRequest(BaseModel):
    """Request to set default delete behavior."""

    rb_default: bool


class RecycleBinSystemCutoffTimeResponse(BaseModel):
    """System-wide recycle bin cutoff time."""

    recycle_bin_cuttoff_time: int


class RecycleBinUpdateCutoffTimeRequest(BaseModel):
    """Request to update system cutoff time."""

    recycle_bin_cuttoff_time: int


class UnusedItemTimeoutRule(BaseModel):
    """A single unused item timeout rule.

    Mirrors apiv3 ``main:api/src/api/schemas/unused_item_timeout.yml``:
    ``op`` selects which scheduler hook the rule applies to (e.g.
    ``send_unused_desktops_to_recycle_bin``); ``cutoff_time`` is the
    threshold in hours after which the action fires (nullable for
    "never"); ``priority`` orders rules with overlapping allowed-sets;
    ``allowed`` scopes the rule by users/groups/categories/roles.
    """

    id: Optional[str] = None
    name: str = ""
    description: str = ""
    op: str = ""
    cutoff_time: Optional[int] = None
    priority: int = 0
    allowed: Allowed = Field(default_factory=Allowed)


class UnusedItemTimeoutRuleCreateRequest(BaseModel):
    """Request to create an unused item timeout rule.

    Field set matches the apiv3 ``Cerberus`` schema and the webapp
    admin form (``recycle_bin_config.js``) which posts
    ``{name, description, op, cutoff_time, priority}``.
    """

    name: str = Field(max_length=50)
    description: str = Field(default="", max_length=255)
    op: str
    cutoff_time: Optional[int] = None
    priority: int
    allowed: Optional[Allowed] = None


class UnusedItemTimeoutRuleUpdateRequest(BaseModel):
    """Request to update an unused item timeout rule.

    Webapp PUT sends the full set of editable fields with optional
    ``cutoff_time`` (nullable) so the schema mirrors that.
    """

    name: Optional[str] = Field(default=None, max_length=50)
    description: Optional[str] = Field(default=None, max_length=255)
    op: Optional[str] = None
    cutoff_time: Optional[int] = None
    priority: Optional[int] = None
    allowed: Optional[Allowed] = None


class UnusedItemTimeoutRulesResponse(BaseModel):
    """List of unused item timeout rules."""

    rules: list[UnusedItemTimeoutRule] = []
