#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar, Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StorageStatusEnum(str, Enum):
    """Enum for storage status"""

    ready = "ready"
    maintenance = "maintenance"
    recycled = "recycled"
    orphan = "orphan"
    deleted = "deleted"


class FormatSpecific(BaseModel):
    data: Dict[str, Any]
    type: str


class QemuImgChildInfo(BaseModel):
    actual_size: int
    children: List[Any] = []
    dirty_flag: bool
    filename: str
    format: str
    format_specific: FormatSpecific
    virtual_size: int


class QemuImgChild(BaseModel):
    info: QemuImgChildInfo
    name: str


class QemuImgFormatSpecific(BaseModel):
    data: Dict[str, Any]
    type: str


class QemuImgInfo(BaseModel):
    actual_size: int
    backing_filename: Optional[str]
    backing_filename_format: Optional[str]
    children: List[QemuImgChild] = []
    cluster_size: int
    dirty_flag: bool
    filename: str
    format: str
    format_specific: QemuImgFormatSpecific
    full_backing_filename: Optional[str]
    virtual_size: int


class StatusLog(BaseModel):
    status: str
    time: float
