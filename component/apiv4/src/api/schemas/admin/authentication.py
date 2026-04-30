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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# --- Policy schemas ---


class PolicyCreateRequest(BaseModel):
    """Request to create an authentication policy"""

    category: str
    role: str
    type: str
    disclaimer: Optional[bool] = None
    email_verification: Optional[bool] = False
    password: Optional[Dict[str, Any]] = None


class PolicyEditRequest(BaseModel):
    """Request to edit an authentication policy"""

    category: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    disclaimer: Optional[Any] = None
    email_verification: Optional[bool] = None
    password: Optional[Dict[str, Any]] = None


# --- Provider config schemas ---


class ProviderConfigUpdateRequest(BaseModel):
    """Request to update a provider configuration"""

    migration: Optional[Dict[str, Any]] = None


# --- Migration exception schemas ---


class MigrationExceptionCreateRequest(BaseModel):
    """Request to add a migration exception"""

    item_type: str
    item_ids: List[str]


# --- Response schemas ---


class PolicyResponse(BaseModel):
    """One row of ``GET /admin/authentication/policies`` and the matching
    per-id read. The persisted policy doc is freeform and may carry
    fields the schema doesn't enumerate."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    category: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    disclaimer: Optional[Any] = None
    email_verification: Optional[bool] = None
    password: Optional[Dict[str, Any]] = None


class ProvidersResponse(BaseModel):
    """Response shape for ``GET /admin/authentication/providers``.

    The service returns a flat ``dict[str, bool]`` mapping provider
    name (``local`` / ``google`` / ``saml`` / ``ldap``) to its enabled
    flag. Modelled with explicit fields so the OpenAPI schema is
    self-documenting.
    """

    local: bool = False
    google: bool = False
    saml: bool = False
    ldap: bool = False


class DisclaimerResponse(BaseModel):
    """Response shape for ``GET /disclaimer``.

    The service returns the current user's disclaimer template as a
    dict ``{title, body}``; both are markdown text.
    """

    model_config = {"extra": "allow"}

    title: Optional[str] = None
    body: Optional[str] = None


class ProviderConfigResponse(BaseModel):
    """Response shape for ``GET /authentication/provider/{provider}``.

    The provider config is the raw ``Configuration.<provider>`` blob
    plus a derived ``migration`` block. Permissive — each provider has
    its own field set.
    """

    model_config = {"extra": "allow"}


class MigrationException(BaseModel):
    """One row of ``GET /authentication/migrations/exceptions``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    item_type: Optional[str] = None
    item_ids: Optional[List[str]] = None
    created_at: Optional[str] = None
