#
#   Copyright © 2025 Pau Abril Iranzo
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


from typing import Literal, Union

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel
from rethinkdb import r

from ..schemas.shared.quotas import Limits


class GroupModel(BaseModel):
    """
    Group Model for managing group objects.
    """

    id: str
    name: str
    parent_category: str
    auto: bool = False
    description: str = ""
    external_app_id: str = ""
    external_gid: str = ""
    limits: Union[Limits, Literal[False]] = False


class Group(RethinkCustomBase):
    """
    Manage Group Objects

    Use constructor with keyword arguments to create new Group Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Group Object.
    """

    _rdb_table = "groups"
