#
#   Copyright © 2025 Adrià Garriga Bassas
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

from api.schemas.allowed import Allowed
from isardvdi_common.models.frontend_mode_rules import FrontendModeEnum
from pydantic import BaseModel, Field


class FrontendModeRulesBase(BaseModel):
    """The fields of a frontend mode rule that administrators choose."""

    name: str = Field(
        ...,
        description="The name of the rule.",
        max_length=50,
    )
    description: str = Field(
        ...,
        description="The description of the rule.",
        max_length=255,
    )
    priority: int = Field(
        ...,
        description="When several rules match a user, only the one with the highest priority applies.",
    )
    allowed: Allowed = Field(
        ...,
        description="The allowed values where the rule will be applied.",
    )
    frontend_mode: FrontendModeEnum = Field(
        ...,
        description=(
            "The frontend mode applied to the matched users. "
            "`deprecated`: only the old frontend is allowed. "
            "`actual`: only the new frontend is allowed. "
            "`all`: both frontends are allowed, with a switch in the UI. "
            "`hidden`: both frontends are allowed, without the UI switch."
        ),
    )


class FrontendModeRules(FrontendModeRulesBase):
    """A rule that decides which frontend mode applies to the users it matches."""

    id: str = Field(
        ...,
        description="The id of the rule",
    )


class FrontendModeRulesResponse(BaseModel):
    """List of frontend mode rules, ordered by priority (highest first)."""

    rules: list[FrontendModeRules]


class FrontendModeRulesCreateRequest(FrontendModeRulesBase):
    """Request model for creating a new frontend mode rule."""

    description: str = Field(
        default="",
        description="The description of the rule.",
        max_length=255,
    )


class FrontendModeRulesUpdateRequest(BaseModel):
    """Request model for updating a frontend mode rule. Only the fields sent change."""

    name: Optional[str] = Field(
        default=None,
        description="The name of the rule.",
        max_length=50,
    )
    description: Optional[str] = Field(
        default=None,
        description="The description of the rule.",
        max_length=255,
    )
    priority: Optional[int] = Field(
        default=None,
        description="When several rules match a user, only the one with the highest priority applies.",
    )
    allowed: Optional[Allowed] = Field(
        default=None,
        description="The allowed values where the rule will be applied. Replaces the whole object.",
    )
    frontend_mode: Optional[FrontendModeEnum] = Field(
        default=None,
        description="The frontend mode applied to the matched users.",
    )
