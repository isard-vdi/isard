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

from pydantic import BaseModel, Field

# -- /stats/{kind} per-kind response models --


class StatsKindUser(BaseModel):
    id: str
    role: str
    category: str
    group: str


class StatsKindDesktop(BaseModel):
    id: str
    user: str


class StatsKindTemplate(BaseModel):
    id: str


class StatsKindHypervisor(BaseModel):
    id: str
    status: str
    only_forced: bool


class StatsKindCategory(BaseModel):
    id: str
    name: str


class StatsKindGroup(BaseModel):
    id: str
    name: str
    parent_category: str


# -- /stats/categories response models --


class StatsCategoryUsersDetail(BaseModel):
    total: int
    status: dict[str, int]
    roles: dict[str, int]


class StatsCategoryDesktopsDetail(BaseModel):
    total: int
    status: dict[str, int]


class StatsCategoryTemplatesDetail(BaseModel):
    total: int
    status: dict[str, int]


class StatsCategoryDetail(BaseModel):
    users: StatsCategoryUsersDetail
    desktops: StatsCategoryDesktopsDetail
    templates: StatsCategoryTemplatesDetail


class StatsCategoriesResponse(BaseModel):
    category: dict[str, StatsCategoryDetail]


# -- /stats/categories/deployments --


class StatsCategoriesDeploymentsResponse(BaseModel):
    categories: dict[str, int]


# -- /stats/domains/status --


class StatsDomainsStatusResponse(BaseModel):
    desktop: dict[str, int] = Field(default_factory=dict)
    template: dict[str, int] = Field(default_factory=dict)
