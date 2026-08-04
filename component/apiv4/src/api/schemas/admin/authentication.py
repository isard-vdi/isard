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

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

# --- Policy schemas ---


class PolicyCreateDisclaimerRequest(BaseModel):
    template: Optional[str] = None


class PolicyCreateRequest(BaseModel):
    """Request to create an authentication policy"""

    category: str
    role: str
    type: str
    disclaimer: Optional[PolicyCreateDisclaimerRequest | bool] = None
    email_verification: Optional[bool] = False
    password: Optional[Dict[str, Any]] = None


class PolicyEditRequest(BaseModel):
    """Request to edit an authentication policy"""

    category: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    disclaimer: Optional[Union[bool, Dict[str, Any]]] = None
    email_verification: Optional[bool] = None
    password: Optional[Dict[str, Any]] = None


# --- Provider config schemas ---


class ProviderStatus(BaseModel):
    """Health status of an authentication provider, written by the
    authentication service and read by the admin UI. Mirrors the Go
    ``model.ProviderStatus`` struct."""

    healthy: bool = False
    msg: str = ""
    last_updated: Optional[datetime] = None


class ProviderConfigUpdateRequest(BaseModel):
    """Update a provider configuration.

    ``extra: allow`` passes the full provider block (``enabled``,
    ``<provider>_config``, …) through to ``update_provider_config``, which does
    the validation; without it Pydantic would drop ``enabled``.
    """

    model_config = {"extra": "allow"}

    migration: Optional[Dict[str, Any]] = None


# --- Migration exception schemas ---


class MigrationExceptionCreateRequest(BaseModel):
    """Request to add a migration exception"""

    item_type: str
    item_ids: List[str]


# --- Response schemas ---


class PolicyResponse(BaseModel):
    """One row of ``GET /admin/items/authentication/policies`` and the matching
    per-id read. The persisted policy doc is freeform and may carry
    fields the schema doesn't enumerate."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    category: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    disclaimer: Optional[Union[bool, Dict[str, Any]]] = None
    email_verification: Optional[bool] = None
    password: Optional[Dict[str, Any]] = None


class ProviderEntry(BaseModel):
    """Enabled flag of one authentication provider."""

    enabled: bool = False


class ProviderWithNameEntry(ProviderEntry):
    """Provider entry with the optional display name read from
    ``config.auth.<provider>.<provider>_config.name``."""

    name: Optional[str] = None


class ProvidersResponse(BaseModel):
    """Response shape for ``GET /admin/items/authentication/providers``.

    The service returns a dict mapping provider name (``local`` /
    ``google`` / ``saml`` / ``ldap``) to its enabled flag, plus the
    optional display name for the nameable providers (``local`` can
    never have one). Modelled with explicit fields so the OpenAPI
    schema is self-documenting.
    """

    local: ProviderEntry = Field(default_factory=ProviderEntry)
    google: ProviderWithNameEntry = Field(default_factory=ProviderWithNameEntry)
    saml: ProviderWithNameEntry = Field(default_factory=ProviderWithNameEntry)
    ldap: ProviderWithNameEntry = Field(default_factory=ProviderWithNameEntry)


class DisclaimerResponse(BaseModel):
    """Response shape for ``GET /item/disclaimer``.

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

    status: Optional[ProviderStatus] = None


class MigrationException(BaseModel):
    """One row of ``GET /authentication/migrations/exceptions``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    item_type: Optional[str] = None
    item_ids: Optional[List[str]] = None
    # Stored as a rethinkdb timestamp; FastAPI's jsonable_encoder
    # serialises ``datetime`` to ISO 8601. Typing this as ``str``
    # crashes ``MigrationException(**row)`` with
    # ``ValidationError: Input should be a valid string``.
    created_at: Optional[datetime] = None
