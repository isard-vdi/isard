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


class MainDomainCertificate(BaseModel):
    """The deployment main-domain certificate config (names ordered, names[0]
    primary; see certificates_config)."""

    names: Optional[List[str]] = None
    certificate_source: Optional[Literal["acme"]] = None
    email: Optional[str] = None
    acme_server: Optional[str] = None
    # Derived from certificate_source for display; never stored.
    acme_challenge: Optional[Literal["http-01"]] = None

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
