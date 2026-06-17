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

FrontendMode = Literal["deprecated", "actual", "all"]


class FaroConfig(BaseModel):
    """Faro client configuration delivered to the browser at startup."""

    enabled: bool = Field(..., description="Whether the Faro SDK should initialize")
    url: Optional[str] = Field(
        None,
        description=(
            "Receiver endpoint. Relative paths target the local HAProxy route; "
            "absolute URLs point to an external Faro receiver."
        ),
    )


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
    user_storage: Optional[UserStorageModel] = Field(
        default=None,
        description="User storage configuration model",
    )


class UserConfigResponse(BaseModel):
    """User configuration response model"""

    show_bookings_button: bool
    # Admins always; managers only with the 'plannings' manager permission;
    # never for regular users. Drives the old-frontend planner nav gate. (!4546)
    show_gpu_plannings: bool = False
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
    frontend_mode: FrontendMode = Field(
        "deprecated",
        description=(
            "Which frontend to serve: 'deprecated' (Vue 2 only), "
            "'actual' (Vue 3 only), or 'all' (both, with toggler)."
        ),
    )
    faro: FaroConfig = Field(
        description="Faro telemetry configuration for the browser SDK.",
    )


class HardwareItem(BaseModel):
    allowed: Allowed
    description: str = Field(description="Description of the hardware item")
    id: str = Field(description="Unique identifier for the hardware item")
    name: str = Field(description="Display name of the hardware item")
    editable: bool = Field(description="Whether this item can be edited")


class ReservableVgpuItem(HardwareItem):
    """A bookable vGPU plus the hypervisor/NUMA grouping the hardware selector
    uses to group passthrough cards by socket/hypervisor (so otherwise-identical
    cards on different sockets or hosts are distinguishable).

    ``hypervisor_groups``/``numa_by_group`` are anonymized and present for every
    role; ``hypervisors``/``numa_by_hypervisor`` carry real hypervisor names and
    are populated for admins/managers only. All default empty for backward
    compatibility.
    """

    hypervisor_groups: list[int] = Field(
        default_factory=list,
        description="Anonymized indices of the hypervisor groups that can host this vGPU",
    )
    numa_by_group: dict[str, list[int]] = Field(
        default_factory=dict,
        description="NUMA nodes per hypervisor-group index (keyed by group index)",
    )
    hypervisors: list[str] = Field(
        default_factory=list,
        description="Hypervisor names hosting this vGPU (admins/managers only)",
    )
    numa_by_hypervisor: dict[str, list[int]] = Field(
        default_factory=dict,
        description="NUMA nodes per hypervisor name (admins/managers only)",
    )


class Reservables(BaseModel):
    vgpus: list[ReservableVgpuItem] = Field(
        description="List of available virtual GPUs"
    )


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


class UserBastionSshKeyResponse(BaseModel):
    """The user's single bastion SSH public key."""

    ssh_key: Optional[str] = Field(
        default=None,
        description="The user's bastion SSH public key, or null if none is set.",
    )


class UserSetBastionSshKeyPutData(BaseModel):
    """Request body for setting the user's bastion SSH public key."""

    ssh_key: str = Field(
        ...,
        description="A single SSH public key (e.g. 'ssh-ed25519 AAAA... comment').",
    )


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


class UserListItem(BaseModel):
    """One row of the ``/items/users`` listing.

    Mirrors the columns plucked by
    ``CommonUsers.get_with_category`` (id / name / category /
    category_name / photo / accessed). This is the shape the
    deployments / lab forms read to populate the user multi-select.
    """

    id: str = Field(description="The ID of the user.")
    name: str = Field(description="The full name of the user.")
    category: str = Field(description="The category ID of the user.")
    category_name: str = Field(description="The name of the user's category.")
    photo: str = Field(default="", description="The URL of the user's photo.")
    accessed: Optional[float] = Field(
        default=None,
        description="Timestamp of the user's last access.",
    )


class WebappDomainItem(BaseModel):
    """Common shape returned by the legacy ``/item/user/webapp-desktops``
    and ``/item/user/webapp-templates`` endpoints.

    Both endpoints return raw rows from the ``domains`` table
    (``DomainsProcessed.list_webapp_desktops_for_user`` /
    ``list_webapp_templates_for_user``) with a few heavy fields
    stripped (``xml``, ``history_domain``, ``allowed`` for desktops;
    plus ``viewer`` for templates). Every field is ``Optional`` —
    ``DomainModel`` itself only requires ``category``, ``group``,
    ``kind``, ``name``, ``persistent``, ``status`` and ``id``, but
    real rows from older schemas may have any of these missing.
    """

    id: str = Field(description="ID of the domain row.")
    name: Optional[str] = None
    kind: Optional[str] = Field(
        default=None,
        description="``desktop`` or ``template``.",
    )
    status: Optional[str] = None
    description: Optional[str] = ""
    detail: Optional[str] = ""
    persistent: Optional[bool] = None
    user: Optional[str] = None
    username: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None
    accessed: Optional[float] = None
    icon: Optional[str] = None
    image: Optional[dict] = None
    os: Optional[str] = None
    parents: Optional[list[str]] = None
    create_dict: Optional[dict] = None
    guest_properties: Optional[dict] = None
    hardware: Optional[dict] = None
    hardware_from_xml: Optional[dict] = None
    options: Optional[dict] = None
    booking_id: Union[str, bool, None] = False
    server: Union[bool, str, None] = None
    tag: Union[str, bool, None] = False
    tag_desktop_id: Union[str, bool, None] = False
    tag_visible: Optional[bool] = False
    progress: Optional[dict] = None
    viewer: Optional[dict] = Field(
        default=None,
        description=(
            "Full viewer subdocument. Present on desktops; stripped "
            "on the templates listing."
        ),
    )
    forced_hyp: Union[bool, list[str], None] = False
    favourite_hyp: Union[bool, list[str], None] = False
    hyp_started: Union[bool, str, None] = False
    hypervisors_pools: Optional[list[str]] = None
    disks_info: Optional[list[dict]] = None
    hw_stats: Optional[dict] = None
    from_template: Optional[str] = None
    current_action: Optional[str] = None
    scheduled: Optional[dict] = None
    enabled: Optional[bool] = None


class UserHardwareKindAllowedResponse(BaseModel):
    """Response for ``/item/user/hardware/{kind}/allowed``.

    ``Quotas.get_hardware_kind_allowed`` returns a partial subset of
    the full ``UserAllowedHardwareResponse`` shape: only the requested
    ``kind`` key is populated (``isos`` populates both ``isos`` and
    ``floppies``; ``quota`` populates ``quota`` and
    ``restriction_applied`` from the applied quota lookup). Every
    field is therefore declared ``Optional`` so a single strict model
    covers all kinds without drift from the canonical
    ``UserAllowedHardwareResponse``.
    """

    interfaces: Optional[list[HardwareItem]] = None
    graphics: Optional[list[HardwareItem]] = None
    videos: Optional[list[HardwareItem]] = None
    boot_order: Optional[list[HardwareItem]] = None
    qos_id: Optional[list[HardwareItem]] = None
    isos: Optional[list[HardwareItem]] = None
    floppies: Optional[list[HardwareItem]] = None
    reservables: Optional[Reservables] = None
    disk_bus: Optional[list[HardwareItem]] = None
    forced_hyp: Optional[list[str]] = None
    favourite_hyp: Optional[list[str]] = None
    quota: Union[bool, dict, None] = None
    restriction_applied: Optional[
        Literal["user_quota", "role_quota", "group_quota", "category_quota"]
    ] = None
