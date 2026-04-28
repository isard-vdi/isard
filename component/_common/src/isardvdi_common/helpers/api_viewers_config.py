#
#   Copyright © 2024 Miriam Melina Gamboa Valdez
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

from cachetools import TTLCache, cached
from rethinkdb import r

from ..connections.rethink_connection_factory import RethinkSharedConnection

_viewers = TTLCache(maxsize=1, ttl=3600)


class ViewersConfig(RethinkSharedConnection):

    ## Config view functions

    @classmethod
    def get_viewers_config(cls):
        custom = []
        with cls._rdb_context():
            config_row = r.table("config").get(1).default({}).run(cls._rdb_connection)
        viewers_dict = (config_row or {}).get("viewers") or {}
        for viewer, value in viewers_dict.items():
            custom.append(value)
        return custom

    @classmethod
    def update_viewers_config(cls, viewer, custom):
        with cls._rdb_context():
            r.table("config").get(1).update(
                {"viewers": {viewer: {"custom": custom}}}
            ).run(cls._rdb_connection)
        _viewers.clear()

    @classmethod
    def reset_viewers_config(cls, viewer):
        with cls._rdb_context():
            r.table("config").get(1).update(
                {"viewers": {viewer: {"custom": r.row["viewers"][viewer]["default"]}}}
            ).run(cls._rdb_connection)
        _viewers.clear()

    ## IsardVDI viewers configuration

    @classmethod
    @cached(_viewers)
    def get_viewers(cls):
        with cls._rdb_context():
            config_row = r.table("config").get(1).default({}).run(cls._rdb_connection)
        return (config_row or {}).get("viewers") or {}

    @classmethod
    def rdp_file_viewer(cls):
        return cls.get_viewers()["file_rdpvpn"]

    @classmethod
    def rdpgw_file_viewer(cls):
        return cls.get_viewers()["file_rdpgw"]

    @classmethod
    def spice_file_viewer(cls):
        return cls.get_viewers()["file_spice"]
