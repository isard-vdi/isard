#
#   Copyright © 2025 IsardVDI
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

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel

# ── Branding ─────────────────────────────────────────────────────────────


class BrandingDomain(BaseModel):
    """Branding domain configuration."""

    enabled: bool = False
    name: Optional[str] = None
    certificate_source: Optional[Literal["acme", "custom"]] = None
    certificate_data: Optional[str] = None


class BrandingLogo(BaseModel):
    """Branding logo configuration. data is a base64 data URL."""

    enabled: bool = False
    data: Optional[str] = None


class BrandingUpdateData(BaseModel):
    """Request body for updating category branding."""

    domain: Optional[BrandingDomain] = None
    logo: Optional[BrandingLogo] = None


# ── Login Notification ───────────────────────────────────────────────────


class CategoryLoginNotificationData(BaseModel):
    """Request body for updating per-category login notification."""

    cover: Optional[Dict[str, Any]] = None
    form: Optional[Dict[str, Any]] = None


class CategoryLoginNotificationEnableData(BaseModel):
    """Request body for enabling/disabling a category login notification."""

    enabled: bool
