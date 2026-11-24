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

import re
from datetime import datetime
from typing import Annotated, Any, ClassVar, Dict, List, Literal, Optional, Union

from isardvdi_common.helpers.url_validation import validate_url_scheme
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import InitErrorDetails, PydanticCustomError

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


_GO_DURATION_UNITS = {
    "ns": 1,
    "us": 10**3,
    "µs": 10**3,  # U+00B5
    "μs": 10**3,  # U+03BC
    "ms": 10**6,
    "s": 10**9,
    "m": 60 * 10**9,
    "h": 3600 * 10**9,
}
_GO_DURATION_PART = re.compile(r"([0-9]*)\.?([0-9]*)(ns|us|µs|μs|ms|s|m|h)")


def _fits_go_duration(value: str) -> str:
    """Range check of Go's ``time.ParseDuration``, with its same arithmetic."""
    total = 0
    for integer, fraction, name in _GO_DURATION_PART.findall(value):
        unit = _GO_DURATION_UNITS[name]
        digits, scale = 0, 1
        for digit in fraction:
            if digits > (2**63 - 1) // 10 or digits * 10 + int(digit) > 2**63:
                break
            digits, scale = digits * 10 + int(digit), scale * 10
        total += int(integer.lstrip("0") or 0) * unit
        total += int(float(digits) * (unit / scale))
    if total > (2**63 if value.startswith("-") else 2**63 - 1):
        raise ValueError("duration out of range")
    return value


# A value Go can't parse makes the authentication service fail to decode the
# whole ``config.auth``, other providers included.
GoDuration = Annotated[
    str,
    Field(pattern=r"^[+\-]?(0|(([0-9]+(\.[0-9]*)?|\.[0-9]+)(ns|us|µs|μs|ms|s|m|h))+)$"),
    AfterValidator(_fits_go_duration),
]


def _drop_defaults(schema: dict[str, Any]) -> None:
    for prop in schema.get("properties", {}).values():
        prop.pop("default", None)


class ProviderPartialUpdate(BaseModel):
    """Block merged into the stored provider: an omitted field keeps its value,
    so the OpenAPI schema must not advertise the Python defaults."""

    model_config = ConfigDict(extra="forbid", json_schema_extra=_drop_defaults)


class ProviderNotificationBarUpdate(ProviderPartialUpdate):
    enabled: bool = False
    template: Optional[str] = None
    level: Optional[Literal["info", "warning", "danger"]] = None


class ProviderMigrationUpdate(ProviderPartialUpdate):
    import_: bool = Field(default=False, alias="import")
    export: bool = False
    force_migration: bool = False
    action_after_migrate: Optional[Literal["", "none", "delete", "disable"]] = None
    notification_bar: ProviderNotificationBarUpdate = Field(
        default_factory=ProviderNotificationBarUpdate
    )


class ProviderConfigBlockUpdate(ProviderPartialUpdate):
    """``<provider>_config`` block, validated as the webapp provider form."""

    name: str = ""

    def required_fields(self) -> list[str]:
        """Fields the form requires, given the values of the others."""
        return []

    def missing_fields(self) -> dict[str, str]:
        """Error message of each required field that is absent or blank."""
        return {
            field: "Field required"
            for field in self.required_fields()
            if not self._filled(field)
        }

    def _filled(self, field: str) -> bool:
        if field not in self.model_fields_set:
            return False
        value = getattr(self, field)
        return not isinstance(value, str) or bool(value.strip())


class GoogleConfigUpdate(ProviderConfigBlockUpdate):
    client_id: str = ""
    client_secret: str = ""

    def required_fields(self) -> list[str]:
        return ["client_id"]


class MappedConfigUpdate(ProviderConfigBlockUpdate):
    """Fields shared by the providers that map external users (LDAP and SAML)."""

    allow_insecure_tls: bool = False

    field_uid: str = ""
    regex_uid: str = ""
    field_username: str = ""
    regex_username: str = ""
    field_name: str = ""
    regex_name: str = ""
    field_email: str = ""
    regex_email: str = ""
    field_photo: str = ""
    regex_photo: str = ""

    guess_category: bool = False
    field_category: str = ""
    regex_category: str = ""

    auto_register: bool = False
    auto_register_roles: list[Literal["admin", "manager", "advanced", "user"]] = Field(
        default_factory=list
    )
    group_default: str = ""
    field_group: str = ""
    regex_group: str = ""
    role_default: Literal["", "user", "advanced", "manager", "admin"] = ""
    role_admin_ids: str = ""
    role_manager_ids: str = ""
    role_advanced_ids: str = ""
    role_user_ids: str = ""

    save_email: bool = False

    def regex_by_field(self) -> dict[str, str]:
        """Visible fields that need their regex once they have a value."""
        pairs = {
            "field_username": "regex_username",
            "field_name": "regex_name",
            "field_email": "regex_email",
            "field_photo": "regex_photo",
        }
        if self.guess_category:
            pairs["field_category"] = "regex_category"
        if self.auto_register:
            pairs["field_group"] = "regex_group"
        return pairs

    def required_fields(self) -> list[str]:
        required = ["field_uid", "regex_uid"]
        if self.guess_category:
            required.append("field_category")
        required.extend(
            regex
            for field, regex in self.regex_by_field().items()
            if getattr(self, field)
        )
        return required


class LdapConfigUpdate(MappedConfigUpdate):
    protocol: str = ""
    host: str = ""
    port: int = 0
    bind_dn: str = ""
    password: str = ""
    base_search: str = ""
    filter: str = ""

    role_list_search_base: str = ""
    role_list_filter: str = ""
    role_list_use_user_dn: bool = False
    role_list_field: str = ""
    role_list_regex: str = ""

    def regex_by_field(self) -> dict[str, str]:
        pairs = super().regex_by_field()
        if self.auto_register:
            pairs["role_list_field"] = "role_list_regex"
        return pairs

    def required_fields(self) -> list[str]:
        required = ["protocol", "host", "port", "bind_dn", "base_search", "filter"]
        required.extend(super().required_fields())
        if self.auto_register:
            required.extend(
                ["role_list_search_base", "role_list_filter", "role_list_field"]
            )
        return required


class SamlConfigUpdate(MappedConfigUpdate):
    metadata_url: str = ""
    metadata_file: str = ""
    entity_id: str = ""
    signature_method: str = ""
    key_file: str = ""
    cert_file: str = ""
    max_issue_delay: GoDuration = ""
    # Not in the webapp form, read by the authentication service.
    request_tracker_max_age: GoDuration = ""

    field_role: str = ""
    regex_role: str = ""

    logout_redirect_url: str = ""

    @field_validator("logout_redirect_url")
    @classmethod
    def _logout_redirect_url_scheme(cls, value: str) -> str:
        validate_url_scheme(value)
        return value

    def regex_by_field(self) -> dict[str, str]:
        pairs = super().regex_by_field()
        if self.auto_register:
            pairs["field_role"] = "regex_role"
        return pairs

    def required_fields(self) -> list[str]:
        required = ["key_file", "cert_file", "max_issue_delay"]
        required.extend(super().required_fields())
        required.append("logout_redirect_url")
        return required

    def missing_fields(self) -> dict[str, str]:
        missing = super().missing_fields()
        if not self._filled("metadata_url") and not self._filled("metadata_file"):
            missing["metadata_url"] = "Field required unless metadata_file is set"
        return missing


class ProviderConfigUpdateRequest(BaseModel):
    """Update a provider."""

    model_config = ConfigDict(extra="forbid")

    _config_block: ClassVar[Optional[str]] = None

    enabled: bool
    migration: ProviderMigrationUpdate = Field(default_factory=ProviderMigrationUpdate)

    @model_validator(mode="after")
    def _complete_when_enabled(self):
        if not self.enabled or self._config_block is None:
            return self
        missing = getattr(self, self._config_block).missing_fields()
        if missing:
            # A ValueError would put the whole body, secrets included, in the
            # ``input`` that the 400 response echoes.
            raise ValidationError.from_exception_data(
                type(self).__name__,
                [
                    InitErrorDetails(
                        type=PydanticCustomError("missing", message),
                        loc=(self._config_block, field),
                        input=None,
                    )
                    for field, message in missing.items()
                ],
            )
        return self


class GoogleProviderConfigUpdateRequest(ProviderConfigUpdateRequest):
    _config_block: ClassVar[Optional[str]] = "google_config"

    google_config: GoogleConfigUpdate = Field(default_factory=GoogleConfigUpdate)


class LdapProviderConfigUpdateRequest(ProviderConfigUpdateRequest):
    _config_block: ClassVar[Optional[str]] = "ldap_config"

    ldap_config: LdapConfigUpdate = Field(default_factory=LdapConfigUpdate)


class SamlProviderConfigUpdateRequest(ProviderConfigUpdateRequest):
    _config_block: ClassVar[Optional[str]] = "saml_config"

    saml_config: SamlConfigUpdate = Field(default_factory=SamlConfigUpdate)


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


class ProviderNotificationBarResponse(BaseModel):
    enabled: Optional[bool] = None
    template: Optional[str] = None
    template_name: Optional[str] = None
    level: Optional[str] = None


class ProviderMigrationResponse(BaseModel):
    import_: Optional[bool] = Field(default=None, alias="import")
    export: Optional[bool] = None
    force_migration: Optional[bool] = None
    action_after_migrate: Optional[str] = None
    notification_bar: Optional[ProviderNotificationBarResponse] = None


class GoogleConfigResponse(BaseModel):
    name: Optional[str] = None
    client_id: Optional[str] = None


class MappedConfigResponse(BaseModel):
    """Fields shared by the providers that map external users (LDAP and SAML)."""

    name: Optional[str] = None
    allow_insecure_tls: Optional[bool] = None

    field_uid: Optional[str] = None
    regex_uid: Optional[str] = None
    field_username: Optional[str] = None
    regex_username: Optional[str] = None
    field_name: Optional[str] = None
    regex_name: Optional[str] = None
    field_email: Optional[str] = None
    regex_email: Optional[str] = None
    field_photo: Optional[str] = None
    regex_photo: Optional[str] = None

    guess_category: Optional[bool] = None
    field_category: Optional[str] = None
    regex_category: Optional[str] = None

    auto_register: Optional[bool] = None
    auto_register_roles: Optional[list[str]] = None
    group_default: Optional[str] = None
    field_group: Optional[str] = None
    regex_group: Optional[str] = None
    role_default: Optional[str] = None
    role_admin_ids: Optional[str] = None
    role_manager_ids: Optional[str] = None
    role_advanced_ids: Optional[str] = None
    role_user_ids: Optional[str] = None

    save_email: Optional[bool] = None


class LdapConfigResponse(MappedConfigResponse):
    protocol: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    bind_dn: Optional[str] = None
    base_search: Optional[str] = None
    filter: Optional[str] = None

    role_list_search_base: Optional[str] = None
    role_list_filter: Optional[str] = None
    role_list_use_user_dn: Optional[bool] = None
    role_list_field: Optional[str] = None
    role_list_regex: Optional[str] = None


class SamlConfigResponse(MappedConfigResponse):
    metadata_url: Optional[str] = None
    metadata_file: Optional[str] = None
    entity_id: Optional[str] = None
    signature_method: Optional[str] = None
    key_file: Optional[str] = None
    cert_file: Optional[str] = None
    max_issue_delay: Optional[str] = None
    request_tracker_max_age: Optional[str] = None

    field_role: Optional[str] = None
    regex_role: Optional[str] = None

    logout_redirect_url: Optional[str] = None


class ProviderConfigResponse(BaseModel):
    """Stored settings of a provider, without its secrets. Looser than the update
    request, as they may predate its validation."""

    enabled: Optional[bool] = None
    status: Optional[ProviderStatus] = None
    migration: Optional[ProviderMigrationResponse] = None
    google_config: Optional[GoogleConfigResponse] = None
    ldap_config: Optional[LdapConfigResponse] = None
    saml_config: Optional[SamlConfigResponse] = None


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
