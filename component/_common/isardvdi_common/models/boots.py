#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
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


from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel
from rethinkdb import r

from ..schemas.shared.allowed import Allowed


class BootModel(BaseModel):
    id: str
    name: str
    description: str
    allowed: Allowed | None = None


class Boot(RethinkCustomBase):
    """
    Manage Boot Objects

    Use constructor with keyword arguments to create new Boot Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Boot Object.
    """

    _rdb_table = "boots"

    @classmethod
    @cached(TTLCache(maxsize=3, ttl=300))
    def get_boots_names(cls):
        with cls._rdb_context():
            boots = r.table("boots").pluck("id", "name").run(cls._rdb_connection)
        return {b["id"]: b["name"] for b in boots}
