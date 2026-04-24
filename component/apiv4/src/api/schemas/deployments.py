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

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional
from uuid import uuid4

from api.schemas.domains.desktops import CreateDesktopRequest, DesktopEditRequest
from api.schemas.domains.hardware import DomainImage
from isardvdi_common.models.deployment import Deployment as RethinkDeployment
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.user import User as RethinkUser
from isardvdi_common.schemas.domains import DesktopStatusEnum, DomainViewerEnum, Image
from isardvdi_common.schemas.shared.hardware import GuestProperties, Hardware
from pydantic import (
    UUID4,
    BaseModel,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from .allowed import Allowed, AllowedBase


class DeploymentUser(BaseModel):
    """Deployment user model"""

    id: str
    name: str
    username: str
    photo: Optional[str] = None
    accessed: float = 0
    started_desktops: int = 0
    total_desktops: int = 0


class DeploymentGroup(BaseModel):
    """User model with necessary fields to show in the avatar"""

    id: str
    name: str
    category_id: str
    category_name: str


class UserList(BaseModel):
    """List of users model"""

    users: list[DeploymentUser]


class CreateDict(BaseModel):
    """Deployment create dict model"""

    guest_properties: GuestProperties
    hardware: Hardware
    image: Image
    name: str
    description: Optional[str]
    reservables: dict
    template: str


class Resource(BaseModel):
    """Deployment resource model"""

    resource_file: Optional[str]


class Deployment(BaseModel):
    """Deployment base model. Imitates what can be found in the database"""

    allowed: Allowed
    co_owners: Optional[list[str]]
    # create_dict: list[CreateDict]
    description: Optional[str]
    id: str
    name: str
    image: Image
    tag: str
    tag_visible: bool
    user: str
    user_permissions: list[str]
    resources: Optional[list[Resource]]


class DeploymentPermissions(str, Enum):
    recreate = "recreate"


class CreateDeploymentRequest(BaseModel):
    name: str = Field(
        description="Name of the deployment",
        min_length=4,
        max_length=50,
    )
    description: str | None = Field(
        default=None,
        description="Description of the deployment",
        max_length=255,
    )
    allowed: AllowedBase = Field(
        description="Who can access the deployment. At least one user or group must be provided."
    )
    create_owner_desktop: bool = Field(
        default=True,
        description="Whether to create a desktop for the user creating the deployment.",
    )
    visible: bool | None = Field(
        default=False,
        description="Whether the deployment is visible to it's users.",
    )
    co_owners: list[str] | None = Field(
        default=[],
        description="List of user IDs that will be co-owners of the deployment.",
    )
    user_permissions: list[DeploymentPermissions] | None = Field(
        default=[],
        description="List of permissions the user creating the deployment has over it.",
    )
    image: DomainImage | None = Field(
        default=None,
        description="Image to use for the deployment. If not provided, the image from the first desktop will be used.",
    )

    desktops: list[CreateDesktopRequest] = Field(
        description="List of different desktop types to create in the deployment. "
        "Each entry will create a number of desktops with the same configuration. "
        "All desktops will be persistent and without bastion target.",
        min_length=1,
    )

    resources: list[Resource] = Field(
        default=[],
        description="UNIMPLEMENTED: List of resources to attach to the deployment",
    )

    @field_validator("allowed")
    @classmethod
    def validate_allowed_not_empty(cls, value: AllowedBase) -> AllowedBase:
        if not (value.users or value.groups):
            raise ValueError("At least one allowed field must be non-empty")
        return value

    @field_serializer("desktops")
    @classmethod
    def serialize_desktops(
        cls, value: list[CreateDesktopRequest]
    ) -> list[CreateDesktopRequest]:
        for desktop in value:
            desktop.persistent = True
            desktop.bastion_target = None
        return value


class DeploymentEditData(BaseModel):
    """Deployment model to edit a deployment, with default values like ID generation"""

    name: Optional[str]
    tag_visible: Optional[bool]
    description: Optional[str]
    co_owners: Optional[list[str]]
    resources: Optional[list[Resource]]
    allowed: Optional[Allowed]
    image: Optional[Image]
    create_dict: Optional[list[CreateDict]]


class DeploymentDesktopEditRequest(DesktopEditRequest):
    tag_desktop_id: Annotated[
        UUID4,
        Field(description="Unique identifier for the desktop within the deployment."),
    ]

    @field_validator("bastion_target")
    @classmethod
    def validate_no_bastion(cls, value):
        return None


class DeploymentEditRequest(BaseModel):

    name: str = Field(description="Name of the deployment", default=None)
    description: str = Field(description="Description of the deployment", default=None)
    image: DomainImage | None = Field(
        default=None,
        description="Image to use for the deployment. If not provided, the image from the first desktop will be used.",
    )
    visible: bool = Field(
        default=None,
        description="Whether the deployment is visible to it's users.",
    )
    allowed: AllowedBase = Field(
        default=None,
        description="Who can access the deployment. At least one user or group must be provided.",
    )
    user_permissions: list[DeploymentPermissions] = Field(
        default=[],
        description="List of permissions the user creating the deployment has over it.",
    )

    desktops_to_edit: list[DeploymentDesktopEditRequest] = Field(
        description="List of different desktop types to edit in the deployment. "
        "If a desktop is present in both edit and delete lists, it will be deleted from the edit list.",
        default=[],
    )
    desktops_to_delete: list[UUID4] = Field(
        description="List of desktop IDs to delete from the deployment. "
        "The IDs must correspond to the `tag_desktop_id` field of the desktops in the deployment. "
        "If a desktop is present in both edit and delete lists, it will be deleted. "
        "At least one desktop must remain in the deployment.",
        default=[],
    )
    desktops_to_create: list[CreateDesktopRequest] = Field(
        description="List of different desktop types to create in the deployment. "
        "Each entry will create a number of desktops with the same configuration. "
        "All desktops will be persistent and without bastion target.",
        default=[],
    )

    resources: list[Resource] = Field(
        default=[],
        description="**UNIMPLEMENTED**: List of resources to attach to the deployment",
    )

    @model_validator(mode="after")
    def validate_edit_request(self) -> "DeploymentEditRequest":
        """If there is a desktop in both edit and delete lists, remove it from the edit list"""
        self.desktops_to_edit = [
            desktop
            for desktop in self.desktops_to_edit
            if desktop.tag_desktop_id not in self.desktops_to_delete
        ]
        return self

    @field_validator("desktops_to_delete")
    @classmethod
    def deduplicate_deletes(cls, value: list[UUID4]) -> list[UUID4]:
        """Remove duplicates from the delete list"""
        return list(set(value))

    @field_validator("desktops_to_edit")
    @classmethod
    def validate_desktops_to_edit_deduplicated(cls, value: list[dict]) -> list[dict]:
        tag_ids = [desktop.tag_desktop_id for desktop in value]
        if len(tag_ids) != len(set(tag_ids)):
            raise ValueError("Duplicate tag_desktop_id found in desktops_to_edit")
        return value

    @field_validator("desktops_to_create")
    @classmethod
    def serialize_desktops(
        cls, value: list[CreateDesktopRequest]
    ) -> list[CreateDesktopRequest]:
        for desktop in value:
            desktop.persistent = True
            desktop.bastion_target = None
        return value


# class DeploymentWithDesktopsResponse(DeploymentResponse):
#     """Deployment response model with its desktops"""

#     desktops: list[Desktop]


class DeploymentUsers(BaseModel):
    """Deployment users model"""

    total: int
    info: list[DeploymentUser]


class DeploymentCsvResponse(BaseModel):
    """Deployment CSV export response model"""

    csv_content: str


## THIS HAS BEEN REVIEWED AND THE DEFINITION MATCHES THE ENDPOINT


class OwnedDeployment(BaseModel):
    id: str = Field(description="ID of the deployment")
    name: str = Field(description="Name of the deployment")
    description: str = Field(description="Description of the deployment")
    image: Image | None = Field(
        default=None,
        description="Image associated with the deployment (may be missing on legacy rows)",
    )
    desktop_names: list[str] = Field(
        description="List of desktop names associated with the deployment"
    )
    started_desktops: int = Field(
        description="Number of desktops that have been started"
    )
    tag_visible: bool = Field(
        default=True, description="Indicates if the deployment is visible"
    )
    total_desktops: int = Field(
        description="Total number of desktops associated with the deployment"
    )
    visible_desktops: int = Field(
        description="Number of visible desktops associated with the deployment"
    )
    total_users: int = Field(
        description="Total number of users associated with the deployment"
    )
    co_owner: bool = Field(
        description="Indicates if the user is a co-owner of the deployment"
    )
    needs_booking: bool = Field(description="Indicates if the deployment needs booking")
    next_booking_start: Optional[datetime] = Field(
        default=None,
        description="Start time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    next_booking_end: Optional[datetime] = Field(
        default=None,
        description="End time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    booking_id: Optional[str | bool] = Field(
        default=None,
        description="Current booking id. Only set when there is an active booking.",
    )


class OwnedDeploymentsResponse(BaseModel):
    deployments: list[OwnedDeployment] = Field(
        description="List of deployments owned and co-owned by the user"
    )


class DesktopStatus(BaseModel):
    """Desktop status count model"""

    status: str = Field(description="Status of the desktops")
    amount: int = Field(description="Number of desktops with the status")


class DeploymentUserDetail(BaseModel):
    """Detailed deployment user model"""

    id: str = Field(description="ID of the user")
    name: str = Field(description="Name of the user")
    username: str = Field(description="Username of the user")
    photo: Optional[str] = Field(description="Photo of the user", default=None)
    desktops_statuses: list[DesktopStatus] = Field(
        description="List of desktop statuses associated with the user", default=[]
    )
    visible: bool = Field(
        description="Indicates if the user has visible desktops", default=False
    )
    last_access: Optional[int] = Field(
        description="Timestamp of the last access of the user", default=None
    )


class DeploymentDetail(BaseModel):
    """Detailed deployment model"""

    id: str = Field(description="ID of the deployment")
    name: str = Field(description="Name of the deployment")
    description: str = Field(description="Description of the deployment")
    tag_visible: bool = Field(
        description="Indicates if the deployment is visible", default=False
    )
    started_desktops: int = Field(
        description="Number of desktops that have been started"
    )
    visible_desktops: int = Field(
        description="Number of visible desktops associated with the deployment"
    )
    total_users: int = Field(
        description="Total number of users associated with the deployment"
    )
    total_desktops: int = Field(
        description="Total number of desktops associated with the deployment"
    )
    desktops_each_user: int = Field(
        description="Number of desktops assigned to each user"
    )


class DeploymentResponse(BaseModel):
    """Deployment response model"""

    info: DeploymentDetail = Field(
        description="Detailed information about the deployment"
    )
    users: list[DeploymentUserDetail] = Field(
        description="List of users associated with the deployment"
    )


class SharedDeploymentUser(BaseModel):
    """Owner info for a shared deployment"""

    name: Optional[str] = Field(
        default=None, description="Name of the deployment owner"
    )
    photo: Optional[str] = Field(
        default=None, description="Photo URL of the deployment owner"
    )


class SharedDeployment(BaseModel):
    """Shared deployment response model"""

    id: str = Field(description="ID of the shared deployment")
    name: str = Field(description="Name of the shared deployment")
    description: Optional[str] = Field(
        description="Description of the shared deployment"
    )
    image: Image | None = Field(
        default=None,
        description="Image associated with the shared deployment (may be missing on legacy rows)",
    )
    user: SharedDeploymentUser = Field(description="Owner of the shared deployment")
    total_desktops: int = Field(
        description="Total number of desktops in the shared deployment"
    )
    started_desktops: int = Field(
        description="Number of started desktops in the shared deployment"
    )
    needs_booking: bool = Field(
        default=False,
        description="If true, the desktop needs to be booked before use. If false, no booking is required.",
    )
    next_booking_start: Optional[datetime] = Field(
        default=None,
        description="Start time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    next_booking_end: Optional[datetime] = Field(
        default=None,
        description="End time of the next booking for the desktop. If None, no booking is scheduled.",
    )
    booking_id: Optional[str | bool] = Field(
        default=None,
        description="Current booking id. Only set when there is an active booking.",
    )


class SharedDeploymentsResponse(BaseModel):
    deployments: list[SharedDeployment] = Field(
        description="List of deployments that have been shared with the user"
    )


class UserDeploymentResource(BaseModel):
    """User deployment resource model"""

    instructions: Optional[str] = Field(
        description="Instructions to use the resource", default=None
    )
    files: Optional[list[str]] = Field(
        description="Files associated with the resource", default=None
    )
    annotations: Optional[str] = Field(
        description="Annotations for the resource", default=None
    )


class UserDeploymentUserInfo(BaseModel):
    """Deployment user info model"""

    id: str = Field(description="ID of the user")
    name: str = Field(description="Name of the user")
    username: str = Field(description="Username of the user")
    photo: Optional[str] = Field(description="Photo of the user", default=None)


class UserDeploymentInfo(BaseModel):
    """Deployment user info model"""

    id: str = Field(description="ID of the deployment")
    name: str = Field(description="Name of the deployment")
    description: Optional[str] = Field(
        description="Description of the deployment", default=None
    )
    tag_visible: bool = Field(description="Indicates if the deployment is visible")
    user: UserDeploymentUserInfo = Field(
        description="Information about the user associated with the deployment"
    )
    owner: UserDeploymentUserInfo = Field(
        description="Information about the owner of the deployment"
    )
    resources: Optional[UserDeploymentResource] = Field(
        description="Resources associated with the deployment", default=None
    )


class UserDeploymentDesktop(BaseModel):
    """User deployment desktop model"""

    id: str = Field(description="ID of the desktop")
    status: DesktopStatusEnum = Field(description="Status of the desktop")
    viewers: list[DomainViewerEnum] = Field(
        default=[],
        description="List of viewers that will be available to access the desktop.",
    )


class UserDeploymentResponse(BaseModel):
    """List of user deployment desktops response model"""

    info: UserDeploymentInfo = Field(
        description="Information about deployment and user"
    )
    desktops: list[UserDeploymentDesktop] = Field(
        description="List of desktops associated with the user in the deployment"
    )


class BulkDeleteDeploymentsRequest(BaseModel):
    ids: list[str] = Field(description="List of deployment IDs to delete")
    permanent: bool = Field(
        default=False,
        description="Whether to permanently delete the deployments",
    )


class BulkDeleteDeploymentsErrorResponse(BaseModel):
    exceptions: list[str] = Field(
        description="List of error messages for deployments that could not be deleted"
    )


class CheckQuotaRequest(BaseModel):
    allowed: Optional[AllowedBase] = Field(
        default=None,
        description="Allowed users and groups to check quota against",
    )


class CoOwnersRequest(BaseModel):
    co_owners: list[str] = Field(description="List of user IDs to set as co-owners")


class CoOwnerUser(BaseModel):
    """Co-owner entry returned by the get co-owners endpoint."""

    id: str = Field(description="User ID")
    name: str = Field(description="User full name")
    photo: Optional[str] = Field(default=None, description="User photo URL")


class CoOwnersResponse(BaseModel):
    co_owners: list[CoOwnerUser] = Field(
        description="List of co-owners of the deployment"
    )


class DeploymentEditUsersRequest(BaseModel):
    """Request body for editing a deployment's allowed users/groups."""

    allowed: dict = Field(
        description="Allowed users and groups dict with keys: groups (list|false), users (list|false)"
    )
