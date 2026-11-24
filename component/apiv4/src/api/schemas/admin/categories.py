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

from typing import Any, ClassVar, Dict, Literal, Optional

from api.schemas.admin.authentication import (
    GoogleConfigResponse,
    GoogleConfigUpdate,
    LdapConfigResponse,
    LdapConfigUpdate,
    MappedConfigUpdate,
    ProviderPartialUpdate,
    ProviderStatus,
    SamlConfigResponse,
    SamlConfigUpdate,
    missing_fields_error,
)
from pydantic import BaseModel, Field, model_validator

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
    logo_collapsed: Optional[BrandingLogo] = None


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
    logo_collapsed: Optional[BrandingLogo] = None


class EmailDomainRestrictionResponse(BaseModel):
    enabled: Optional[bool] = None
    allowed: Optional[list[str]] = None


class CategoryProviderResponse(BaseModel):
    disabled: Optional[bool] = None
    email_domain_restriction: Optional[EmailDomainRestrictionResponse] = None
    config_source: Optional[str] = None
    max_role: Optional[str] = None
    status: Optional[ProviderStatus] = None


class CategoryGoogleConfigResponse(GoogleConfigResponse):
    client_secret_set: Optional[bool] = None


class CategoryGoogleResponse(CategoryProviderResponse):
    google_config: Optional[CategoryGoogleConfigResponse] = None


class CategoryLdapConfigResponse(LdapConfigResponse):
    password_set: Optional[bool] = None


class CategoryLdapResponse(CategoryProviderResponse):
    ldap_config: Optional[CategoryLdapConfigResponse] = None


class CategorySamlResponse(CategoryProviderResponse):
    saml_config: Optional[SamlConfigResponse] = None


class CategoryAuthenticationResponse(BaseModel):
    """Stored provider settings of a category, without their secrets. Looser than
    the update request, as they may predate its validation."""

    local: Optional[CategoryProviderResponse] = None
    google: Optional[CategoryGoogleResponse] = None
    ldap: Optional[CategoryLdapResponse] = None
    saml: Optional[CategorySamlResponse] = None


class EmailDomainRestrictionUpdate(ProviderPartialUpdate):
    enabled: bool
    allowed: list[str] = Field(default_factory=list)


class CategoryProviderUpdate(ProviderPartialUpdate):
    """Provider settings in a category, validated as the webapp category form.
    A disabled provider needs nothing else."""

    _config_block: ClassVar[Optional[str]] = None

    disabled: bool
    email_domain_restriction: EmailDomainRestrictionUpdate = Field(
        default_factory=lambda: EmailDomainRestrictionUpdate(enabled=False)
    )
    config_source: Literal["global", "custom"] = "global"
    max_role: Optional[Literal["", "user", "advanced", "manager", "admin"]] = None

    @model_validator(mode="after")
    def _complete_when_enabled(self):
        if self.disabled:
            return self
        missing: dict[tuple[str, ...], str] = {
            (field,): "Field required"
            for field in ("email_domain_restriction", "config_source")
            if field not in self.model_fields_set
        }
        restriction = self.email_domain_restriction
        if restriction.enabled and "allowed" not in restriction.model_fields_set:
            missing[("email_domain_restriction", "allowed")] = "Field required"
        if self._config_block is not None:
            config = getattr(self, self._config_block)
            fields = config.missing_fields() if self.config_source == "custom" else {}
            if (
                restriction.enabled
                and isinstance(config, MappedConfigUpdate)
                and not config.filled("field_email")
            ):
                fields["field_email"] = "Field required"
            for field, message in fields.items():
                missing[(self._config_block, field)] = message
        if missing:
            raise missing_fields_error(type(self).__name__, missing)
        return self


class CategoryGoogleUpdate(CategoryProviderUpdate):
    _config_block: ClassVar[Optional[str]] = "google_config"

    google_config: GoogleConfigUpdate = Field(default_factory=GoogleConfigUpdate)


class CategoryLdapUpdate(CategoryProviderUpdate):
    _config_block: ClassVar[Optional[str]] = "ldap_config"

    ldap_config: LdapConfigUpdate = Field(default_factory=LdapConfigUpdate)


class CategorySamlUpdate(CategoryProviderUpdate):
    _config_block: ClassVar[Optional[str]] = "saml_config"

    saml_config: SamlConfigUpdate = Field(default_factory=SamlConfigUpdate)


class CategoryAuthenticationUpdate(ProviderPartialUpdate):
    """Omitted providers keep their stored settings."""

    local: CategoryProviderUpdate = Field(default=None)
    google: CategoryGoogleUpdate = Field(default=None)
    ldap: CategoryLdapUpdate = Field(default=None)
    saml: CategorySamlUpdate = Field(default=None)


# ── Login Notification ───────────────────────────────────────────────────


class CategoryLoginNotificationData(BaseModel):
    """Request body for updating per-category login notification."""

    cover: Optional[Dict[str, Any]] = None
    form: Optional[Dict[str, Any]] = None


class CategoryLoginNotificationEnableData(BaseModel):
    """Request body for enabling/disabling a category login notification."""

    enabled: bool
