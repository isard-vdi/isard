#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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

from pydantic import BaseModel, Field


class Quota(BaseModel):
    desktops: int = Field(..., ge=0)
    volatile: int = Field(..., ge=0)
    desktops_disk_size: int = Field(..., ge=0)
    isos: int = Field(..., ge=0)
    vcpus: int = Field(..., ge=0)
    memory: int = Field(..., ge=1)
    running: int = Field(..., ge=0)
    templates: int = Field(..., ge=0)
    total_size: int = Field(..., ge=0)
    total_soft_size: int = Field(..., ge=0)
    deployments_total: int = Field(..., ge=0)
    deployment_desktops: int = Field(..., ge=0)
    deployment_users: int = Field(..., ge=0)
    started_deployment_desktops: int = Field(..., ge=0)


class Limits(BaseModel):
    desktops: int = Field(..., ge=0)
    desktops_disk_size: int = Field(..., ge=0)
    isos: int = Field(..., ge=0)
    vcpus: int = Field(..., ge=0)
    memory: int = Field(..., ge=1)
    running: int = Field(..., ge=0)
    templates: int = Field(..., ge=0)
    users: int = Field(..., ge=0)
    total_size: int = Field(..., ge=0)
    total_soft_size: int = Field(..., ge=0)
    deployments_total: int = Field(..., ge=0)
