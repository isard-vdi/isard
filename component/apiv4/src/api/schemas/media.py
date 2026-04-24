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

from enum import Enum
from typing import Literal, Optional

from api.schemas.common import PaginationResponseList
from isardvdi_common.schemas.domains import DesktopStatusEnum, DomainKindEnum
from isardvdi_common.schemas.media import MediaKindEnum, MediaStatusEnum
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .allowed import Allowed


class CreateMediaRequest(BaseModel):
    """Request model for creating media"""

    name: str = Field(
        description="Name of the media.",
        min_length=4,
        max_length=50,
    )
    description: str = Field(
        default="",
        description="Description of the media.",
        max_length=255,
    )
    allowed: Allowed
    kind: MediaKindEnum
    url: HttpUrl
    hypervisors_pools: list[str]


class MediaResponse(BaseModel):
    id: str
    name: str
    category: str
    allowed: Allowed
    description: str
    status: MediaStatusEnum
    user: str
    username: str
    kind: MediaKindEnum
    accessed: Optional[int] = None
    group: Optional[str] = None


class MediaProgress(BaseModel):
    """Media download progress model.

    Mirrors the dict written by the engine into the RethinkDB ``progress``
    column (see ``services/media.py:create_media``). Fields are Optional with
    defaults so partial documents (legacy rows, freshly-inserted media before
    the engine populates) don't 500 the entire ``GET /items/media`` response.
    """

    received: str = "0"
    received_percent: int = 0
    total: str = ""
    total_percent: int = 0
    speed_current: str = ""
    speed_download_average: str = ""


class MediaItemResponse(BaseModel):
    """Media item response model for user media list"""

    id: str
    name: str
    description: str
    kind: MediaKindEnum
    url_isard: bool | str = Field(validation_alias="url-isard")
    url_web: bool | str = Field(validation_alias="url-web")
    status: MediaStatusEnum
    progress: MediaProgress = Field(default_factory=MediaProgress)
    user: str
    category: str
    group: str
    accessed: float
    icon: str
    editable: bool

    @field_validator("progress", mode="before")
    @classmethod
    def _default_progress(cls, value):
        return value if value is not None else {}


# class MediaAllowedTableResponse(BaseModel):
#     """Response model for allowed users/roles/groups/categories for media"""

#     categories: bool
#     groups: bool
#     roles: bool
#     users: list[dict[str, str]]


class MediaDesktopResponse(BaseModel):
    """Desktop using media response model"""

    create_dict: dict
    id: str
    kind: DomainKindEnum = DomainKindEnum.desktop.value
    name: str
    status: DesktopStatusEnum
    user: str
    user_name: str


class MediaQuotaCheckResponse(BaseModel):
    """Media quota check response (empty for success)"""

    pass


class DesktopAttachedMediaItem(BaseModel):
    """Single media item attached to a desktop's hardware (iso or floppy).

    Returned by ``GET /item/desktop/{id}/media-list`` (replaces the v3
    ``POST /desktops/media_list`` shim). Mirrors the v3
    ``api_media.List()`` shape.
    """

    id: str
    name: str
    kind: Literal["iso", "floppy"]
    size: Optional[int] = None


class MediaCheckResponse(BaseModel):
    """Response for the schedule-check action.

    The action is a no-op when the media is not currently downloaded
    (``task_id`` is ``None``); otherwise the queued RQ task id is
    returned so the caller can poll its progress.
    """

    task_id: Optional[str] = None


class MediaInstallItem(BaseModel):
    """Single virt_install template entry returned by
    ``GET /items/media/installs`` (replaces v3 ``GET /media/installs``).

    The route exposes the catalogue of OS install profiles the
    ``Add Install`` modal in the webapp uses to bootstrap a desktop
    from an ISO. Pluck mirrors the v3 ``admin_table_list("virt_install",
    pluck=["id", "name", "description", "vers"])``.
    """

    id: str
    name: str
    description: Optional[str] = ""
    vers: Optional[str] = None

    class Config:
        # The underlying ``AdminTablesService.get_table`` returns the
        # full row; allow extra keys so consumers that already render
        # additional fields don't break on schema migration.
        extra = "allow"


class UserAllowedMediaSearchFields(str, Enum):
    name = "name"
    description = "description"
    group_name = "group_name"
    category_name = "category_name"


class MediaUser(BaseModel):
    id: str = Field(
        description="ID of the user that allowed the media",
    )
    name: str = Field(
        description="Name of the user that allowed the media",
    )
    photo: Optional[str] = Field(
        default=None,
        description="Photo of the user that allowed the media",
    )


class UserSharedMedia(BaseModel):
    id: str = Field(
        description="ID of the allowed media",
    )
    name: str = Field(
        description="Name of the allowed media",
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the allowed media",
    )
    user: Optional[MediaUser] = Field(
        default=None,
        description="Name of the user that allowed the media",
    )
    group_name: Optional[str] = Field(
        default=None,
        description="Name of the group that allowed the template",
    )
    category_name: Optional[str] = Field(
        default=None,
        description="Name of the category of the allowed template",
    )
    accessed: float = Field(description="Timestamp of the last access to the media.")
    kind: MediaKindEnum = Field(description="Kind of the media")
    status: MediaStatusEnum = Field(description="Status of the media")
    progress: MediaProgress = Field(
        default_factory=MediaProgress,
        description="Download progress of the media",
    )

    @field_validator("progress", mode="before")
    @classmethod
    def _default_progress(cls, value):
        return value if value is not None else {}


class UserMediaResponse(BaseModel):
    """List of media items response model"""

    media: list[MediaItemResponse] = Field(
        description="List of user media",
    )


class UserSharedMediaResponse(BaseModel):
    media: list[UserSharedMedia]


class UserAllowedMediaPaginationResponse(PaginationResponseList[UserSharedMedia]):
    rows: list[UserSharedMedia] = Field(
        description="List of allowed media for the current page"
    )
