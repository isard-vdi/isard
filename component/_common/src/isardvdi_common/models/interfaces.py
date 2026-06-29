#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Miriam Melina Gamboa Valdez
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

from cachetools import cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from pydantic import BaseModel
from rethinkdb import r

from ..schemas.shared.allowed import Allowed


class InterfaceModel(BaseModel):
    id: str
    description: str
    ifname: str
    kind: str
    model: str
    name: str
    net: str
    qos_id: str
    allowed: Allowed | None = None


class Interface(RethinkCustomBase):
    """
    Manage Interface Objects

    Use constructor with keyword arguments to create new Interface Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Interface Object.
    """

    _rdb_table = "interfaces"

    @classmethod
    @cached(SynchronizedTTLCache(maxsize=3, ttl=300))
    def get_interfaces_names(cls):
        with cls._rdb_context():
            interfaces = (
                r.table("interfaces").pluck("id", "name").run(cls._rdb_connection)
            )
        return {b["id"]: b["name"] for b in interfaces}
