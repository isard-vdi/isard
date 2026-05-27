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

from pydantic import BaseModel, ConfigDict

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


class BrandingResponse(BaseModel):
    """Response shape for ``GET /admin/item/category/{id}/branding``.

    Mirrors the request shape — ``BrandingUpdateData`` — but is a
    distinct class because the response side of branding is the
    persisted value (i.e. ``Category.branding``), and the response
    model is what FastAPI uses to filter the wire payload. Keeps both
    sub-objects optional because freshly-created categories may have
    no branding row at all.
    """

    domain: Optional[BrandingDomain] = None
    logo: Optional[BrandingLogo] = None


class CategoryAuthenticationResponse(BaseModel):
    """Response shape for ``GET /admin/item/category/{id}/authentication``.

    Permissive (``ConfigDict(extra="allow")``) because the underlying
    ``Category.authentication`` blob is provider-specific freeform
    (``local`` / ``ldap`` / ``saml`` / ``google``), and the service
    pre-strips the secret keys (password, client_secret) before
    returning. The response is consumed by the admin edit-modal which
    inspects fields per-provider.
    """

    model_config = ConfigDict(extra="allow")


# ── Login Notification ───────────────────────────────────────────────────


class CategoryLoginNotificationData(BaseModel):
    """Request body for updating per-category login notification."""

    cover: Optional[Dict[str, Any]] = None
    form: Optional[Dict[str, Any]] = None


class CategoryLoginNotificationEnableData(BaseModel):
    """Request body for enabling/disabling a category login notification."""

    enabled: bool
