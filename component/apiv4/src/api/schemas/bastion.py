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


from typing import Optional

from pydantic import BaseModel, Field


class BastionHttpConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="If true, the bastion HTTP access will be enabled for the desktop.",
    )
    http_port: int = Field(
        default=80,
        description="HTTP port for the bastion.",
    )
    https_port: int = Field(
        default=443,
        description="HTTPS port for the bastion.",
    )


class BastionSshConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="If true, the bastion SSH access will be enabled for the desktop.",
    )
    port: int = Field(
        default=22,
        description="SSH port for the bastion.",
    )
    authorized_keys: list[Optional[str]] = Field(
        default=[],
        description="List of SSH public keys to be authorized for the bastion SSH access. If empty, the authorized keys will be cleared.",
    )


# TODO: Review if this schema is needed or if it can be removed
class BastionResponse(BaseModel):
    """Response model for bastion configuration"""

    desktop_id: str
    http: BastionHttpConfig
    id: str
    ssh: BastionSshConfig
    user_id: str
    domain: str | None = None
    domains: list[str] = Field(default=[])


class BastionActiveSshStatus(BaseModel):
    """SSH access status without exposing the authorized keys."""

    enabled: bool = Field(default=False)
    port: int = Field(default=22)


class BastionActiveResponse(BaseModel):
    """Lightweight, read-only bastion status for a desktop.

    Returned by the non-mutating ``/bastion/active`` endpoint used by the
    desktop-card "Bastion" entry: it never creates a target and carries just
    enough to decide whether to open the read-only access modal (``ssh.enabled``
    / ``http.enabled``) and to render the access links.
    """

    exists: bool = Field(
        default=False,
        description="Whether a bastion target exists for this desktop.",
    )
    id: str | None = Field(default=None, description="The bastion target ID.")
    domain: str | None = Field(default=None, description="Custom domain, if any.")
    domains: list[str] = Field(default=[], description="Additional custom domains.")
    ssh: BastionActiveSshStatus = Field(default_factory=BastionActiveSshStatus)
    http: BastionHttpConfig = Field(default_factory=BastionHttpConfig)
    bastion_domain: str | None = Field(
        default=None, description="The global bastion domain."
    )
    bastion_ssh_port: str | None = Field(
        default=None, description="The global bastion SSH port (None if disabled)."
    )
    bastion_enabled: bool = Field(
        default=False, description="Whether bastion is globally enabled."
    )


class BastionRequest(BaseModel):
    http: BastionHttpConfig | None = Field(
        default=None,
        description="Bastion HTTP configuration. If not provided, the bastion HTTP configuration will not be modified.",
    )
    ssh: BastionSshConfig | None = Field(
        default=None,
        description="Bastion SSH configuration. If not provided, the bastion SSH configuration will not be modified.",
    )
    domain: str | None = Field(
        default=None,
        description="Custom domain name to access the bastion. If the the bastion target hasn't been yet created and domain verification is required, the domain cannot be set.",
    )


class AdminBastionConfigResponse(BaseModel):
    """Response model for admin bastion configuration overview"""

    bastion_enabled: bool = Field(
        description="Whether bastion is currently enabled (both in config and database).",
    )
    bastion_enabled_in_cfg: bool = Field(
        description="Whether bastion is enabled in the environment configuration.",
    )
    bastion_enabled_in_db: bool = Field(
        description="Whether bastion is enabled in the database configuration.",
    )
    bastion_domain: str | None = Field(
        description="The bastion domain configured.",
    )
    bastion_ssh_port: str | None = Field(
        description="The SSH port for bastion connections. None if bastion is disabled.",
    )
    domain_verification_required: bool = Field(
        description="Whether domain verification is required for bastion domains.",
    )


class AdminBastionConfigUpdateRequest(BaseModel):
    """Request model for updating bastion configuration"""

    enabled: bool = Field(
        description="Whether to enable or disable bastion.",
    )
    bastion_domain: str = Field(
        description="The bastion domain to set.",
    )
    domain_verification_required: bool = Field(
        description="Whether domain verification should be required.",
    )


class BastionDomainVerificationConfigResponse(BaseModel):
    """Response model for bastion domain verification configuration"""

    domain_verification_required: bool = Field(
        description="Whether domain verification is required for bastion domains.",
    )


class BastionAuthorizedKeysRequest(BaseModel):
    """Request model for updating bastion SSH authorized keys"""

    authorized_keys: list[str] = Field(
        ...,
        description="List of SSH public keys to authorize for bastion SSH access.",
    )


class BastionDomainsRequest(BaseModel):
    """Request model for updating bastion custom domains"""

    domains: list[str] = Field(
        ...,
        max_length=10,
        description="List of custom domain names for the bastion target. Maximum 10.",
    )


class BastionDomainVerifyRequest(BaseModel):
    """Request model for verifying a single bastion domain's DNS"""

    domain: str = Field(
        ...,
        min_length=1,
        description="Domain name to verify DNS for.",
    )


class BastionDomainVerifyResponse(BaseModel):
    """Response model for bastion domain verification"""

    verified: bool = Field(
        description="Whether the domain's DNS is correctly configured.",
    )


class DeleteBastionDisallowedTargetsResponse(BaseModel):
    removed_targets: list[str] = Field(
        description="List of bastion target IDs that were removed because they are no longer allowed.",
    )
