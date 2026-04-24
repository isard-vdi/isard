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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """Notification response model"""

    # This will be None for the status bar notifications mock
    # Add specific fields when actual notification structure is defined
    pass


class StatusBarNotificationResponse(BaseModel):
    """Status bar notification response model (can be None)"""

    text: Optional[str] = None
    level: Optional[str] = None
    migration_config: Optional[dict] = None


class NotificationItem(BaseModel):
    """Individual notification item"""

    id: str
    vars: Optional[Dict[str, str]] = None
    text: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    footer: Optional[str] = None


class NotificationTemplate(BaseModel):
    """Notification template"""

    body: str
    footer: str
    title: str


class NotificationUserData(BaseModel):
    """User notification data"""

    display: List[str]
    action_id: str
    template_id: str
    force_accept: bool
    notifications: List[NotificationItem]
    template: Optional[NotificationTemplate] = None


class NotificationsUserTriggerDisplayResponse(BaseModel):
    """User notification displays response model"""

    notifications: Dict[int, Dict[str, NotificationUserData]] = {}


class NotificationFlatItem(BaseModel):
    """Flat notification item ready to render, with template already resolved."""

    id: str
    title: str = ""
    body: str = ""
    footer: Optional[str] = None
    force_accept: bool = False


class NotificationsUserTriggerDisplayFlatResponse(BaseModel):
    """User trigger notifications as a flat, ordered list.

    The server has already resolved the user's language template against
    each item and sorted by the notification's ``order`` field, so the
    client can render the list as-is.
    """

    notifications: List[NotificationFlatItem] = []


class NotificationsUserDisplaysTriggerResponse(BaseModel):
    """User notification displays for a trigger response model"""

    displays: List[str] = []
