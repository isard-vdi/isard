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

from cachetools import cached
from isardvdi_common.helpers.rdp_security import (
    allowed_rdp_security,
    certificate_check,
    with_certificate_check,
)
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r

from ..connections.rethink_connection_factory import RethinkSharedConnection

_viewers = SynchronizedTTLCache(maxsize=1, ttl=3600)


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

    ## RDP security policy

    RDP_FILE_VIEWERS = ("file_rdpgw", "file_rdpvpn")

    @classmethod
    def get_rdp_security(cls):
        """Allowed guest security levels, and the certificate check the RDP files carry."""
        with cls._rdb_context():
            config_row = r.table("config").get(1).default({}).run(cls._rdb_connection)
        viewers = (config_row or {}).get("viewers") or {}
        return {
            "allowed_protocols": list(allowed_rdp_security(config_row)),
            "certificate_check": certificate_check(
                (viewers.get("file_rdpgw") or {}).get("custom")
            ),
        }

    @classmethod
    def update_rdp_security(cls, allowed_protocols, certificate_check_level=None):
        """Store the allowed levels; set the certificate check in both RDP files' custom part."""
        from isardvdi_common.models.config import Config

        with cls._rdb_context():
            update = {
                "rdp_security": r.literal({"allowed_protocols": allowed_protocols})
            }
            if certificate_check_level is not None:
                viewers = (
                    r.table("config")
                    .get(1)
                    .get_field("viewers")
                    .default({})
                    .run(cls._rdb_connection)
                )
                update["viewers"] = {
                    viewer: {
                        "custom": with_certificate_check(
                            viewers[viewer].get("custom"), certificate_check_level
                        )
                    }
                    for viewer in cls.RDP_FILE_VIEWERS
                    if viewer in viewers
                }
            r.table("config").get(1).update(update).run(cls._rdb_connection)
        _viewers.clear()
        Config.clear_get_config_cache()

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
