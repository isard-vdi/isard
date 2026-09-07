#
#   Copyright © 2026 Josep Maria Viñolas Auquer
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
"""Schemas for the global (admin-only) main-domain certificate configuration."""

from typing import List, Literal, Optional

from pydantic import BaseModel, field_validator

# Let's Encrypt caps a certificate at 100 identifiers.
_MAX_NAMES = 100


class AcmeDnsCredentials(BaseModel):
    """One acme-dns registration. All fields optional: the operator fills this
    in stages. password is write-only and never returned; password_set is the
    read-only flag telling the form whether one is stored.
    """

    base_url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    subdomain: Optional[str] = None
    fulldomain: Optional[str] = None
    auto_register: Optional[bool] = None
    verified: Optional[bool] = None
    # Derived on read, never stored.
    password_set: Optional[bool] = None


class MainDomainCertificate(BaseModel):
    """The deployment main-domain certificate config (names ordered, names[0]
    primary; see certificates_config)."""

    names: Optional[List[str]] = None
    certificate_source: Optional[Literal["acme", "acme_dns"]] = None
    email: Optional[str] = None
    acme_server: Optional[str] = None
    # Derived from certificate_source for display; never stored.
    acme_challenge: Optional[Literal["http-01", "dns-01"]] = None
    acmedns: Optional[AcmeDnsCredentials] = None

    @field_validator("names")
    @classmethod
    def _validate_names(cls, names: Optional[List[str]]) -> Optional[List[str]]:
        if names is None:
            return names
        normalised = [name.strip().lower() for name in names]
        if not normalised or any(not name for name in normalised):
            raise ValueError("at least one non-empty certificate name is required")
        if len(normalised) > _MAX_NAMES:
            raise ValueError(f"a certificate may carry at most {_MAX_NAMES} names")
        if len(set(normalised)) != len(normalised):
            raise ValueError("certificate names must be unique")
        return normalised


class CertificatesConfigResponse(BaseModel):
    """Response for ``GET /admin/config/certificates``."""

    main_domain: Optional[MainDomainCertificate] = None


class CertificatesConfigUpdate(BaseModel):
    """Request body for ``PUT /admin/config/certificates``."""

    main_domain: Optional[MainDomainCertificate] = None


class AcmeDnsRegisterRequest(BaseModel):
    """Request body for ``POST /admin/config/certificates/acmedns/register``."""

    base_url: str
    # Required to overwrite: re-registering abandons the first account (acme-dns
    # cannot delete it) and breaks any CNAME created for it.
    replace: bool = False


class AcmeDnsRegisterResponse(BaseModel):
    """What the operator has to act on: the delegation to ask their customer for."""

    cname_record: str
    cname_target: str
    username: str
    subdomain: str
    fulldomain: str
    password_set: bool


class AcmeDnsVerifyResponse(BaseModel):
    """The state of the delegation, as seen from here."""

    verified: bool
    message: str
    observed: Optional[str] = None
    expected: Optional[str] = None
    resolver: Optional[str] = None
