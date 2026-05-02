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

from typing import Optional

from pydantic import BaseModel, Field

# -- /stats/{kind} per-kind response models --


class StatsKindUser(BaseModel):
    # Bug 46: same orphan-row family as Bugs 43/44 — the ``users``
    # table can carry rows with only ``id`` (+ stranded vpn config)
    # for users whose document was deleted but whose wireguard peer
    # was not. The strict ``str`` types rejected those rows and
    # 500'd the entire ``/stats/users`` endpoint via Pydantic's
    # response_model validation. Make every non-id field Optional
    # so the orphan row surfaces with empty cells instead of breaking
    # the admin user-stats panel.
    id: str
    role: Optional[str] = None
    category: Optional[str] = None
    group: Optional[str] = None


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


class StatsGenericResponse(BaseModel):
    """Permissive response shape for the stats endpoints whose service
    methods return varied / nested dicts (general stats, desktop status,
    category status, category limits, kind/state breakdowns, started-
    count). The webapp admin renders these per-key.
    """

    model_config = {"extra": "allow"}
