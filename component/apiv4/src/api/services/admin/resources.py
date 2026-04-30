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

from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_vpn import IsardVpn
from isardvdi_common.lib.api_admin import ApiAdmin


class AdminResourcesService:

    @staticmethod
    def get_remote_vpn(vpn_id: str, kind: str = "config", os: str = None) -> dict:
        """Get remote VPN configuration data."""
        if not os and kind != "config":
            raise Error("bad_request", "RemoteVpn: no OS supplied")
        return IsardVpn.vpn_data("remotevpn", kind, os, vpn_id)

    @staticmethod
    def add_qos_disk(data: dict) -> dict:
        """Add a new QoS disk profile."""
        Helpers.check_duplicate("qos_disk", data["name"])
        errors = AdminResourcesService._check_qos_burst_limits(data.get("iotune", {}))
        if errors:
            raise Error(
                "bad_request",
                "QoS burst limit validation failed: " + "; ".join(errors),
            )
        ApiAdmin.insert_table_item("qos_disk", data)
        return {}

    @staticmethod
    def update_qos_disk(data: dict) -> dict:
        """Update an existing QoS disk profile."""
        qos_disk_id = data["id"]
        Helpers.check_duplicate("qos_disk", data["name"], item_id=qos_disk_id)
        if data.get("iotune"):
            errors = AdminResourcesService._check_qos_burst_limits(data["iotune"])
            if errors:
                raise Error(
                    "bad_request",
                    "QoS burst limit validation failed: " + "; ".join(errors),
                )
        ApiAdmin.update_table_item("qos_disk", data)
        return {}

    @staticmethod
    def _check_qos_burst_limits(iotune: dict) -> list:
        """Check that burst limits are higher than base limits."""
        errors = []
        for key, value in iotune.items():
            if "_sec" in key and not key.endswith("_max"):
                max_key = key + "_max"
                if max_key in iotune:
                    if iotune[max_key] < value:
                        errors.append(
                            f"{key} burst value should be higher than limit value"
                        )
        return errors
