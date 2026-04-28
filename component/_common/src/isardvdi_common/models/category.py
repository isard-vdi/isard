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


from typing import Dict, Optional
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel, Field
from rethinkdb import r

from ..schemas.category import *


class CategoryModel(BaseModel):
    authentication: Dict[str, AuthenticationModel] = Field(
        default_factory=lambda: {
            "google": AuthenticationModel(),
            "ldap": AuthenticationModel(),
            "saml": AuthenticationModel(),
            "local": AuthenticationModel(),
        }
    )
    auto: Optional[bool] = False
    custom_url_name: str
    description: Optional[str] = ""
    ephimeral: bool = False
    frontend: bool
    id: str = Field(default_factory=lambda: str(uuid4()))
    limits: Optional[dict | bool] = False
    maintenance: Optional[bool] = False
    name: str
    quota: Optional[dict | bool] = False
    recycle_bin_cutoff_time: Optional[int] = None
    uid: str
    photo: Optional[str] = None


class Category(RethinkCustomBase):
    """
    Manage Category Objects

    Use constructor with keyword arguments to create new Category Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Category Object.
    """

    _rdb_table = "categories"
