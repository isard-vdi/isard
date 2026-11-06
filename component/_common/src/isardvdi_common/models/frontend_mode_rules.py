#
#   Copyright © 2026 Pau Abril Iranzo
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

from isardvdi_common.connections.rethink_base import PydanticBase, pydantic_optional
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.schemas.shared.allowed import Allowed
from pydantic import Field
from rethinkdb import r


class FrontendModeEnum(str, Enum):
    # Only `old-frontend` is allowed
    deprecated = "deprecated"
    # Only `frontend` is allowed
    actual = "actual"
    # Both `frontend` and `old-frontend` are allowed with a switch in the UI
    all = "all"
    # Both `frontend` and `old-frontend` are allowed without the UI switch
    hidden = "hidden"


class FrontendModeRulesModel(PydanticBase):
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
    frontend_mode: FrontendModeEnum


@pydantic_optional
class FrontendModeRulesUpdateModel(FrontendModeRulesModel):
    pass


class FrontendModeRules(RethinkCustomBase):
    _rdb_table = "frontend_mode_rules"
    _rdb_table_schema = FrontendModeRulesModel
    _rdb_table_update_schema = FrontendModeRulesUpdateModel
