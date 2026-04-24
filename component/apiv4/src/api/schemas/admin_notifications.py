#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, RootModel

from .allowed import Allowed

# --- Template schemas ---


class TemplateCreateRequest(BaseModel):
    """Request to create a notification template"""

    language: str
    title: str
    body: str
    footer: str
    name: Optional[str] = None
    description: Optional[str] = None
    default: Optional[str] = None
    kind: Optional[str] = None


class TemplateUpdateRequest(BaseModel):
    """Request to update a notification template"""

    language: str
    title: str
    body: str
    footer: str
    name: Optional[str] = None
    description: Optional[str] = None
    default: Optional[str] = None


class TemplatePreviewRequest(BaseModel):
    """Request to preview a notification template rendering"""

    event: str
    user_id: Optional[str] = None
    data: Dict[str, Any] = {}


class TemplateResponse(BaseModel):
    """Single notification template response"""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None
    default: Optional[str] = None
    lang: Optional[Dict[str, Any]] = None
    system: Optional[Dict[str, Any]] = None


class TemplateListResponse(BaseModel):
    """List of notification templates"""

    templates: List[Dict[str, Any]]


class TemplatePreviewResponse(BaseModel):
    """Preview of rendered template"""

    title: Optional[str] = None
    body: Optional[str] = None
    footer: Optional[str] = None
    channels: Optional[List[str]] = None


# --- Notification schemas ---


class NotificationCreateRequest(BaseModel):
    """Request to create a notification"""

    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    display: Optional[List[str]] = None
    template_id: Optional[str] = None
    action_id: Optional[str] = None
    item_type: Optional[str] = None
    order: Optional[int] = None
    enabled: Optional[bool] = None
    force_accept: Optional[bool] = None
    compute: Optional[Any] = None
    ignore_after: Optional[str] = None
    keep_time: Optional[int] = None
    allowed: Allowed = Field(default_factory=Allowed)


class NotificationUpdateRequest(BaseModel):
    """Request to update a notification"""

    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    display: Optional[List[str]] = None
    template_id: Optional[str] = None
    action_id: Optional[str] = None
    item_type: Optional[str] = None
    order: Optional[int] = None
    enabled: Optional[bool] = None
    force_accept: Optional[bool] = None
    compute: Optional[Any] = None
    ignore_after: Optional[str] = None
    keep_time: Optional[int] = None
    allowed: Optional[Allowed] = None


class NotificationDeleteRequest(BaseModel):
    """Request body for deleting a notification"""

    delete_logs: bool = True


class NotificationResponse(BaseModel):
    """Single notification response"""

    id: Optional[str] = None


class NotificationDetailResponse(RootModel[Dict[str, Any]]):
    """Full notification row. RootModel so datetime fields (``ignore_after``)
    go through Pydantic's JSON serializer instead of Starlette's default
    encoder."""


class NotificationListResponse(BaseModel):
    """List of notifications"""

    notifications: List[Dict[str, Any]]


class NotificationActionsResponse(BaseModel):
    """List of notification actions"""

    actions: List[Dict[str, Any]]


# --- Notification data schemas ---


class NotificationDataListResponse(BaseModel):
    """List of notification data entries"""

    data: List[Dict[str, Any]]


class NotificationStatusesResponse(BaseModel):
    """List of notification statuses"""

    statuses: List[str]


class NotificationGroupedDataResponse(BaseModel):
    """Grouped notification data response"""

    data: List[Dict[str, Any]]


# --- User display schemas ---


class AdminUserDisplaysResponse(BaseModel):
    """Admin user notification displays response"""

    displays: List[str]
