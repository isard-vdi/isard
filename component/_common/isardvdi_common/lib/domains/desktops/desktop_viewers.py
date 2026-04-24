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


import base64
import json
import logging as log
import os
import secrets
import time
import traceback
import urllib.parse
import uuid
from datetime import datetime, timedelta

import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.redis_urls import socketio_url
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.api_notify import notify_admins, send_socket_user
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.lib.bookings.bookings import BookingsProcessed
from rethinkdb import r
from socketio import RedisManager

socketio = RedisManager(socketio_url(), write_only=True)


class DesktopViewers(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def get_novnc_data(cls, desktop):
        if not desktop.get("viewer"):
            return False
        viewer_url = "https://" + desktop["viewer"]["static"]
        data = {
            "vmName": desktop["name"],
            "vmHost": desktop["viewer"]["proxy_hyper_host"],
            "vmPort": str(desktop["viewer"]["base_port"] + 2),
            "host": desktop["viewer"]["proxy_video"],
            "port": desktop["viewer"].get("html5_ext_port", "443"),
            "token": desktop["viewer"].get("passwd", ""),
            "exp": (datetime.now(pytz.utc) + timedelta(minutes=240)).timestamp(),
        }
        cookie = base64.b64encode(
            json.dumps({"web_viewer": data}).encode("utf-8")
        ).decode("utf-8")
        if os.environ.get("DIRECTVIEWER_MODE") == "url":
            viewer = viewer_url + "/viewer/noVNC?cookie=" + cookie
        else:
            viewer = viewer_url + "/viewer/noVNC/"
        urlp = (
            viewer_url
            + "/viewer/noVNC/?vmName="
            + urllib.parse.quote_plus(desktop["name"])
            + "&vmHost="
            + desktop["viewer"]["proxy_hyper_host"]
            + "&host="
            + desktop["viewer"]["proxy_video"]
            + "&port="
            + data["port"]
            + "&vmPort="
            + data["vmPort"]
            + "&passwd="
            + desktop["viewer"].get("passwd", "")
        )
        return {
            "kind": "browser",
            "protocol": "vnc",
            "viewer": viewer,
            "urlp": urlp,
            "cookie": cookie,
            "values": data,
        }

    @staticmethod
    def check_viewers(data, domain):
        if data.get("hardware") is None:
            data["hardware"] = {}
        if data.get("guest_properties") is None:
            data["guest_properties"] = {}
        if data.get("guest_properties", {}).get("viewers") == None:
            data["guest_properties"] = domain["guest_properties"]
        elif not data.get("guest_properties", {}).get("viewers"):
            raise Error(
                "bad_request",
                "At least one viewer must be selected.",
                traceback.format_exc(),
                description_code="one_viewer_minimum",
            )
        hardware = {}
        if not data.get("hardware", {}).get("videos") or not data.get(
            "hardware", {}
        ).get("interfaces"):
            viewers_hardware = {}
            if not data.get("hardware", {}).get("videos"):
                viewers_hardware["videos"] = domain["create_dict"]["hardware"]["videos"]
            else:
                viewers_hardware["videos"] = data["hardware"]["videos"]

            if data.get("hardware", {}).get("interfaces") is None:
                data["hardware"] = {
                    "interfaces": [
                        interface["id"]
                        for interface in domain["create_dict"]["hardware"]["interfaces"]
                    ]
                }
                viewers_hardware["interfaces"] = [
                    interface["id"]
                    for interface in domain["create_dict"]["hardware"]["interfaces"]
                ]
            elif data.get("hardware", {}).get("interfaces") == []:
                data["hardware"] = {"interfaces": []}
                viewers_hardware["interfaces"] = []
            else:
                viewers_hardware["interfaces"] = data["hardware"]["interfaces"]

            hardware = viewers_hardware
        else:
            hardware = data["hardware"]

        viewers = data["guest_properties"]["viewers"]

        if (
            viewers.get("file_rdpgw")
            or viewers.get("browser_rdp")
            or viewers.get("file_rdpvpn")
        ) and (
            "wireguard" not in hardware["interfaces"]
            or hardware.get("interfaces") == []
        ):
            raise Error(
                "bad_request",
                "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                traceback.format_exc(),
            )

        if "none" in hardware["videos"] and (
            viewers.get("file_spice")
            or viewers.get("browser_vnc")
            or not (
                viewers.get("file_rdpgw")
                or viewers.get("browser_rdp")
                or viewers.get("file_rdpvpn")
            )
        ):
            raise Error(
                "bad_request",
                "'Only GPU' mode only works with RDP viewers. Please remove non-RDP viewers or choose another video option",
                traceback.format_exc(),
                description_code="only_works_rdp",
            )

        return data

    @staticmethod
    def check_new_desktop_viewers(new_data, template):
        """

        Perform validation on the viewers selected for a new desktop.
        Raises an Error if no viewers are selected.
        Raises an Error if the selected viewers are incompatible with the hardware configuration.
            - RDP viewers require the wireguard network.
            - 'Only GPU' video mode only works with RDP viewers.
            - A reservable vgpu must be selected when using 'Only GPU' video mode.

        """
        # Check if at least one viewer is selected
        viewers = new_data.get("guest_properties", {}).get("viewers") or template.get(
            "guest_properties", {}
        ).get("viewers")
        if not viewers:
            raise Error(
                "bad_request",
                "At least one viewer must be selected.",
                traceback.format_exc(),
                description_code="one_viewer_minimum",
            )

        # Check RDP viewers and wireguard network dependency
        interfaces = (new_data.get("hardware") or {}).get("interfaces") or [
            interface["id"]
            for interface in template.get("create_dict", {})
            .get("hardware", {})
            .get("interfaces", [])
        ]
        rdp_viewers = ["file_rdpgw", "browser_rdp", "file_rdpvpn"]
        if any(viewers.get(v) for v in rdp_viewers) and "wireguard" not in interfaces:
            raise Error(
                "bad_request",
                "RDP viewers need the wireguard network. Please add wireguard network to this desktop or remove RDP viewers.",
                traceback.format_exc(),
            )

        # Check 'Only GPU' video mode and RDP viewers compatibility
        hardware = new_data.get("hardware") or template.get("create_dict", {}).get(
            "hardware", {}
        )
        non_rdp_viewers = ["file_spice", "browser_vnc"]
        videos = hardware.get("videos", [])
        if "none" in videos:
            if any(viewers.get(v) for v in non_rdp_viewers):
                raise Error(
                    "bad_request",
                    "'Only GPU' mode only works with RDP viewers. Please remove non-RDP viewers or choose another video option",
                    traceback.format_exc(),
                    description_code="only_works_rdp",
                )
            if (
                template.get("reservables", {}).get("vgpus")
                and not new_data.get("reservables", {}).get("vgpus")
            ) or (new_data.get("reservables", {}).get("vgpus") in [[], None, ""]):
                raise Error(
                    "bad_request",
                    "A reservable vgpu must be selected when using 'Only GPU' video mode.",
                    traceback.format_exc(),
                    description_code="vgpu_must_selected",
                )
