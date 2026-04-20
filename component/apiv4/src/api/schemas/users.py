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

from typing import Literal, Optional, Union

from isardvdi_common.schemas.shared.allowed import Allowed
from isardvdi_common.schemas.user import UserStorageModel
from pydantic import BaseModel, Field


class UserVpnWireguardKeys(BaseModel):
    """VPN Wireguard keys model"""

    private: str
    public: str


class UserVpnWireguard(BaseModel):
    """VPN Wireguard configuration model"""

    Address: str
    AllowedIPs: str
    connected: bool
    extra_client_nets: Optional[str]
    keys: UserVpnWireguardKeys
    remote_ip: Optional[str]
    remote_port: Optional[int]


class UserVpn(BaseModel):
    """User VPN configuration model"""

    iptables: list[str]
    wireguard: UserVpnWireguard


class UserResponse(BaseModel):

    name: str
    email: str
    role: str
    role_name: str
    photo: str = Field(description="The URL of the user's photo.", default="")
    items_in_bin: int


class SecondaryGroupsData(BaseModel):
    id: str
    name: str


class UserDetailsResponse(BaseModel):
    """User response model"""

    id: str = Field(description="The ID of the user.")
    username: str = Field(description="The username of the user.")
    photo: str = Field(default="", description="The URL of the user's photo.")
    name: str = Field(description="The full name of the user.")
    email: str = Field(description="The email address of the user.")
    email_verified: bool | int | None = Field(
        default=None,
        description="Indicates if the user's email is verified.",
    )
    lang: Optional[str] = Field(
        default=None, description="The preferred language of the user."
    )
    provider: str = Field(description="The authentication provider for the user.")
    category: str = Field(description="The category ID of the user.")
    category_name: str = Field(description="The name of the category of the user.")
    group: str = Field(description="The primary group ID of the user.")
    group_name: str = Field(description="The name of the primary group of the user.")
    role: str = Field(description="The role ID of the user.")
    role_name: str = Field(description="The name of the role of the user.")
    secondary_groups_data: list[SecondaryGroupsData] = Field(
        description="List of secondary groups IDs and names the user belongs to."
    )
    user_storage: Optional[UserStorageModel] = None


class UserConfigResponse(BaseModel):
    """User configuration response model"""

    show_bookings_button: bool
    documentation_url: str
    viewers_documentation_url: str
    show_change_email_button: bool
    show_temporal_tab: bool
    http_port: str
    https_port: str
    bastion_domain: str | None
    bastion_ssh_port: str | None
    can_use_bastion: bool
    can_use_bastion_individual_domains: bool
    migrations_block: bool
    session: dict
    frontend_mode: Literal["deprecated", "actual", "all"] = "deprecated"


class HardwareItem(BaseModel):
    allowed: Allowed
    description: str = Field(description="Description of the hardware item")
    id: str = Field(description="Unique identifier for the hardware item")
    name: str = Field(description="Display name of the hardware item")
    editable: bool = Field(description="Whether this item can be edited")


class Reservables(BaseModel):
    vgpus: list[HardwareItem] = Field(description="List of available virtual GPUs")


class UserAllowedHardwareResponse(BaseModel):
    virtualization_nested: bool | None = Field(
        default=False,  # Default value for nested virtualization
        description="Whether nested virtualization is enabled",
    )
    interfaces: list[HardwareItem] = Field(
        description="List of available network interfaces"
    )
    graphics: list[HardwareItem] = Field(
        description="List of available graphics configurations"
    )
    videos: list[HardwareItem] = Field(description="List of available video cards")
    boot_order: list[HardwareItem] = Field(
        description="List of available boot order options"
    )
    qos_id: list[HardwareItem] = Field(
        description="List of available Quality of Service profiles"
    )
    isos: list[HardwareItem] = Field(description="List of available ISO images")
    floppies: list[HardwareItem] = Field(
        description="List of available floppy disk images"
    )
    reservables: Reservables = Field(description="Reservable resources like vGPUs")
    disk_bus: list[HardwareItem] = Field(description="List of available disk bus types")
    forced_hyp: list[str] = Field(description="List of forced hypervisors")
    favourite_hyp: list[str] = Field(description="List of favorite hypervisors")
    quota: Union[bool, dict] = Field(
        description="User quota information or boolean if no quota applies"
    )
    restriction_applied: Literal[
        "user_quota", "role_quota", "group_quota", "category_quota"
    ] = Field(description="Type of quota restriction that was applied")


class UserQuota(BaseModel):
    desktops: int
    volatile: int
    templates: int
    isos: int
    total_size: float
    deployments_total: int
    deployment_desktops: int
    deployment_users: int
    started_deployment_desktops: int
    running: int
    memory: float
    vcpus: int
    desktops_disk_size: float
    total_soft_size: float


class UserQuotaUsed(BaseModel):
    desktops: int
    volatile: int
    templates: int
    isos: int
    total_size: float
    media_size: float
    storage_size: float
    deployments_total: int
    deployment_desktops: int
    deployment_users: int
    started_deployment_desktops: int
    running: int
    memory: float
    vcpus: int


class UserQuotaResponse(BaseModel):
    """User quota response model"""

    restriction_applied: str = Field(
        description="The type of quota restriction applied to the user.",
    )
    quota: UserQuota | Literal[False] = Field(
        description="The quota limits for the user or False if no quota applies.",
    )
    used: UserQuotaUsed = Field(
        description="Current resource usage of the user.",
    )


class RegisterPostData(BaseModel):
    code: str


class UserPasswordPolicyResponse(BaseModel):
    """User password policy response model"""

    digits: int = Field(description="Minimum number of digits required in the password")
    expiration: int = Field(description="Password expiration time in days")
    length: int = Field(description="Minimum length of the password")
    lowercase: int = Field(
        description="Minimum number of lowercase letters required in the password",
    )
    not_username: bool = Field(
        description="Whether the password should be able to include the username",
    )
    old_passwords: int = Field(
        description="Number of old passwords to remember and not allow reuse"
    )
    special_characters: int = Field(
        description="Minimum number of special characters required in the password",
    )
    uppercase: int = Field(
        description="Minimum number of uppercase letters required in the password",
    )


class UserSetEmailPutData(BaseModel):
    email: str


class UserAPIKeyResponse(BaseModel):
    exists: bool
    expires: float


class UserSetLangPutData(BaseModel):
    lang: str


class UserSetPasswordPutData(BaseModel):
    current_password: str
    password: str


class GroupsUsersCountPutData(BaseModel):
    """Request body for counting users in groups."""

    groups: list[str] = Field(description="List of group IDs to count users for.")


class GroupsUsersCountResponse(BaseModel):
    """Response for groups users count."""

    quantity: int = Field(description="Total number of users in the specified groups.")


class UserAppliedQuotaResponse(BaseModel):
    """Response for user applied quota."""

    quota: dict | Literal[False] = Field(
        description="The applied quota or False if no quota applies.",
    )
    restriction_applied: str = Field(
        description="The type of quota restriction applied to the user.",
    )


class UserOwnsDesktopRequest(BaseModel):
    """
    Request body for the three ``owns_desktop`` variants.

    Exactly one of the three (mutually-exclusive) shapes below must be
    set by the caller. The route dispatches based on the JWT payload
    and the fields populated:

    1. ``ip`` alone → look up the running desktop by its viewer
       ``guest_ip``. If the JWT is a direct-viewer token that
       already carries ``desktop_id``, the ``ip`` is instead
       interpreted as the ``connection_ip`` to match the desktop's
       ``viewer.guest_ip``.
    2. ``proxy_video`` + ``proxy_hyper_host`` + ``port`` → look up
       the desktop by the composite ``proxies`` index.

    Used by rdpgw, websockify and guac as a service-side preflight
    before proxying a direct-viewer connection.
    """

    ip: Optional[str] = Field(
        default=None,
        description=(
            "Either the caller's connection IP (when the direct-viewer "
            "token carries a ``desktop_id``) or the desktop's viewer "
            "``guest_ip`` to look up (otherwise)."
        ),
    )
    proxy_video: Optional[str] = Field(
        default=None,
        description=(
            "The proxy video host, optionally with port "
            "(``host`` or ``host:port``). Used together with "
            "``proxy_hyper_host`` and ``port``."
        ),
    )
    proxy_hyper_host: Optional[str] = Field(
        default=None,
        description="The hypervisor host behind the proxy.",
    )
    port: Optional[int] = Field(
        default=None,
        description="The viewer port to match.",
    )


# -- Response models --


class UserDesktop(BaseModel):
    id: str
    name: str
    status: str
    kind: str
    image: Optional[dict] = None
    description: Optional[str] = ""
    tag_visible: Optional[bool] = False
    accessed: Optional[float] = None
    user: Optional[str] = None
    ip: Optional[str] = None


class UserVpnData(BaseModel):
    kind: Optional[str] = None
    content: Optional[str] = None
    name: Optional[str] = None
    ext: Optional[str] = None
    mime: Optional[str] = None
