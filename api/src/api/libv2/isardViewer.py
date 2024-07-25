#
#   Copyright © 2017-2024 Josep Maria Viñolas
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
import os
import traceback

import pytz
from rethinkdb import RethinkDB

from api import app

from .api_viewers_config import rdp_file_viewer, rdpgw_file_viewer, spice_file_viewer

r = RethinkDB()
import urllib

from isardvdi_common.api_exceptions import Error
from rethinkdb.errors import ReqlNonExistenceError

from ..libv2.caches import get_document
from ..libv2.flask_rethink import RDB
from ..libv2.utils import parse_delta

db = RDB(app)
db.init_app(app)

from datetime import datetime, timedelta

import jwt


def default_guest_properties():
    return {
        "credentials": {
            "username": "isard",
            "password": "pirineus",
        },
        "fullscreen": False,
        "viewers": {
            "file_spice": {"options": None},
            "browser_vnc": {"options": None},
            "file_rdpgw": {"options": None},
            "file_rdpvpn": {"options": None},
            "browser_rdp": {"options": None},
        },
    }


def viewer_jwt(category_id, desktop_id, minutes=240, admin_role=False):
    return jwt.encode(
        {
            "exp": datetime.utcnow() + timedelta(minutes=minutes),
            "kid": "isardvdi-viewer",
            "data": (
                {"category_id": category_id, "desktop_id": desktop_id}
                if not admin_role
                else {"desktop_id": desktop_id, "role_id": "admin"}
            ),
        },
        os.environ.get("API_ISARDVDI_SECRET"),
        algorithm="HS256",
    )


class isardViewer:
    def __init__(self):
        # Offset from base_port == spice
        self.spice = 0
        self.spice_tls = 1
        self.vnc = 2
        self.vnc_tls = 3
        self.vnc_ws = -198  # 5900-200????
        self.rdpgw_port = os.environ.get("VIEWER_RDPGW", 9999)
        pass

    def viewer_data(
        self,
        desktop_id,
        protocol="browser-vnc",
        admin_role=False,
    ):
        domain = get_document(
            "domains",
            desktop_id,
            [
                "id",
                "name",
                "viewer",
                "status",
                "viewer",
                "guest_properties",
                "category",
            ],
        )
        if domain is None:
            raise Error(
                "not_found",
                f"Unable to get viewer for inexistent desktop {id}",
                description_code="unable_to_get_viewer_inexistent",
            )

        if not domain.get("viewer", {}).get("base_port"):
            raise Error(
                "bad_request",
                f"Desktop {id} does not have a viewer (base_port). Is it really started? Actual status: {domain.get('status')}",
                description_code="unable_to_get_viewer",
            )
        if not protocol in ["file-spice", "browser-vnc"] and not domain["status"] in [
            "Started",
            "Shutting-down",
        ]:
            raise Error(
                "precondition_required",
                f"Unable to get {protocol} viewer for non started desktop {id}",
                description_code="unable_to_get_viewer",
            )

        ### File viewers
        if protocol == "file-spice":
            port = domain["viewer"]["base_port"] + self.spice_tls
            vmPort = domain["viewer"].get("spice_ext_port", "80")
            consola = self.get_spice_file(domain, vmPort, port)
            return {
                "kind": "file",
                "protocol": "spice",
                "name": "isard-spice",
                "ext": consola[0],
                "mime": consola[1],
                "content": consola[2],
            }

        if protocol == "file-vnc":
            raise Error(
                "not_found",
                "Viewer protocol file-vnc not implemented",
                description_code="viewer_protocol_not_implemented",
            )

        if protocol == "file-rdpvpn":
            if not domain.get("viewer", {}).get("guest_ip"):
                raise Error(
                    "not_found",
                    f"Viewer file-rdpvpn not ready for desktop {id} as it does not have a guest ip",
                    description_code="unable_to_get_viewer_inexistent",
                )
            return {
                "kind": "file",
                "protocol": "rdpvpn",
                "name": "isard-rdp-vpn",
                "ext": "rdp",
                "mime": "application/x-rdp",
                "content": self.get_rdp_file(
                    domain["viewer"]["guest_ip"],
                    domain["guest_properties"]["credentials"]["username"],
                    domain["guest_properties"]["credentials"]["password"],
                ),
            }

        if protocol == "file-rdpgw":
            if not domain.get("viewer", {}).get("guest_ip"):
                raise Error(
                    "not_found",
                    f"Viewer file-rdpgw not ready for desktop {id} as it does not have a guest ip",
                    description_code="unable_to_get_viewer_inexistent",
                )
            return {
                "kind": "file",
                "protocol": "rdpgw",
                "name": "isard-rdp-gw",
                "ext": "rdp",
                "mime": "application/x-rdp",
                "content": self.get_rdp_gw_file(
                    domain["viewer"]["guest_ip"],
                    domain["viewer"]["static"].split(":")[0],
                    self.rdpgw_port,
                    viewer_jwt(
                        domain["category"],
                        domain["id"],
                        int(
                            parse_delta(
                                os.environ.get(
                                    "AUTHENTICATION_AUTHENTICATION_TOKEN_DURATION", "4h"
                                )
                            ).total_seconds()
                            / 60
                        ),
                        admin_role,
                    ),
                    domain["guest_properties"]["credentials"]["username"],
                    domain["guest_properties"]["credentials"]["password"],
                ),
            }

        ## Browser viewers
        viewer_url = "https://" + domain["viewer"]["static"]
        if protocol == "browser-spice":
            data = {
                "vmName": domain["name"],
                "vmHost": domain["viewer"]["proxy_hyper_host"],
                "vmPort": str(domain["viewer"]["base_port"] + self.spice),
                "host": domain["viewer"]["proxy_video"],
                "port": domain["viewer"].get("html5_ext_port", "443"),
                "token": domain["viewer"]["passwd"],
            }
            cookie = base64.b64encode(
                json.dumps({"web_viewer": data}).encode("utf-8")
            ).decode("utf-8")

            uri = viewer_url + "/viewer/spice-web-client/"
            urlp = (
                viewer_url
                + "/viewer/spice-web-client/?vmName="
                + urllib.parse.quote_plus(domain["name"])
                + "&vmHost="
                + domain["viewer"]["proxy_hyper_host"]
                + "&host="
                + domain["viewer"]["proxy_video"]
                + "&vmPort="
                + data["port"]
                + "&passwd="
                + domain["viewer"]["passwd"]
            )
            return {
                "kind": "browser",
                "protocol": "spice",
                "viewer": uri,
                "urlp": urlp,
                "cookie": cookie,
                "values": data,
            }

        if protocol == "browser-vnc":
            data = {
                "vmName": domain["name"],
                "vmHost": domain["viewer"]["proxy_hyper_host"],
                "vmPort": str(domain["viewer"]["base_port"] + self.vnc),
                "host": domain["viewer"]["proxy_video"],
                "port": domain["viewer"].get("html5_ext_port", "443"),
                "token": domain["viewer"].get("passwd", ""),
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
                + urllib.parse.quote_plus(domain["name"])
                + "&vmHost="
                + domain["viewer"]["proxy_hyper_host"]
                + "&host="
                + domain["viewer"]["proxy_video"]
                + "&port="
                + data["port"]
                + "&vmPort="
                + data["vmPort"]
                + "&passwd="
                + domain["viewer"].get("passwd", "")
            )
            return {
                "kind": "browser",
                "protocol": "vnc",
                "viewer": viewer,
                "urlp": urlp,
                "cookie": cookie,
                "values": data,
            }

        if protocol == "browser-rdp":
            if not domain.get("viewer", {}).get("guest_ip"):
                raise Error(
                    "not_found",
                    f"Viewer browser-rdp not ready for desktop {id} as it does not have a guest ip",
                    description_code="unable_to_get_viewer_inexistent",
                )
            data = {
                "vmName": domain["name"],
                "vmHost": domain["viewer"]["guest_ip"],
                "vmUsername": domain["guest_properties"]["credentials"]["username"],
                "vmPassword": domain["guest_properties"]["credentials"]["password"],
                "host": domain["viewer"]["static"],
                "port": domain["viewer"].get("html5_ext_port", "443"),
                "exp": (datetime.now(pytz.utc) + timedelta(minutes=240)).timestamp(),
            }
            cookie = jwt.encode(
                {
                    "exp": datetime.utcnow() + timedelta(minutes=240),
                    "kid": "isardvdi-viewer",
                    "type": "viewer",
                    "web_viewer": data,
                },
                os.environ.get("API_ISARDVDI_SECRET"),
                algorithm="HS256",
            )
            if os.environ.get("DIRECTVIEWER_MODE") == "url":
                viewer = (
                    viewer_url
                    + "/Rdp?cookie="
                    + cookie
                    + "&jwt="
                    + viewer_jwt(
                        domain["category"],
                        domain["id"],
                        int(
                            parse_delta(
                                os.environ.get(
                                    "AUTHENTICATION_AUTHENTICATION_TOKEN_DURATION", "4h"
                                )
                            ).total_seconds()
                            / 60
                        ),
                        admin_role,
                    )
                )
            else:
                viewer = viewer_url + "/Rdp"
            urlp = "Not implemented"
            return {
                "kind": "browser",
                "protocol": "rdp",
                "viewer": viewer,
                "urlp": urlp,
                "cookie": cookie,
                "values": data,
            }

        if protocol == "vnc-client-macos":
            raise Error(
                "not_found",
                "Viewer protocol vnc-client-macos not implemented",
                description_code="viewer_protocol_not_implemented",
            )

        raise Error(
            "not_found",
            f"Viewer protocol {protocol} not found",
            description_code="not_found",
        )

    def get_rdp_file(self, ip, username, password):
        fixed = rdp_file_viewer()["fixed"] % (ip, username, password)
        custom = rdp_file_viewer()["custom"]
        consola = fixed + "\n" + custom
        consola = "\n".join([line.strip() for line in consola.splitlines()])
        return consola

    def get_rdp_gw_file(
        self, ip, proxy_video, proxy_port, jwt_token, username, password
    ):
        fixed = rdpgw_file_viewer()["fixed"] % (
            ip,
            proxy_video,
            proxy_port,
            jwt_token,
            username,
            password,
        )
        custom = rdpgw_file_viewer()["custom"]

        consola = fixed + "\n" + custom
        consola = "\n".join([line.strip() for line in consola.splitlines()])
        return consola

    def get_spice_file(self, domain, port, vmPort):
        op_fscr = int(
            domain.get("guest_properties", {})
            .get("viewers", {})
            .get("fullscreen", False)
        )
        c = "%"
        consola = """[virt-viewer]
        type=%s
        proxy=http://%s:%s
        host=%s
        password=%s
        tls-port=%s
        fullscreen=%s
        title=%s:%sd - Prem SHIFT+F12 per sortir""" % (
            "spice",
            domain["viewer"]["proxy_video"],
            port,
            domain["viewer"]["proxy_hyper_host"],
            domain["viewer"]["passwd"],
            vmPort,
            op_fscr,
            domain["name"] + " (TLS)",
            c,
        )

        custom = spice_file_viewer()["custom"]

        consola = (
            consola
            + "\n"
            + """%shost-subject=%s
                %sca=%r"""
            % (
                "" if domain["viewer"]["tls"]["host-subject"] is not False else ";",
                domain["viewer"]["tls"]["host-subject"],
                "" if domain["viewer"]["tls"]["certificate"] is not False else ";",
                domain["viewer"]["tls"]["certificate"],
            )
            + "\n"
            + custom
        )

        consola = consola.replace("'", "")
        consola = "\n".join([line.strip() for line in consola.splitlines()])
        return "vv", "application/x-virt-viewer", consola

    ##### VNC NOT DONE

    def get_domain_vnc_data(self, domain, hostnames, viewer, port):
        try:
            cookie = base64.b64encode(
                json.dumps(
                    {
                        "web_viewer": {
                            "host": hostnames["host"],
                            "port": str(int(port)),
                            "token": domain["viewer"]["passwd"],
                        }
                    }
                ).encode("utf-8")
            ).decode("utf-8")

            return {
                "uri": "https://" + hostnames["proxy"] + "/static/noVNC",
                "cookie": cookie,
            }

        except:
            raise Error(
                "internal_server",
                "Get vnc viewer data internal error.",
                traceback.format_exc(),
                description_code="get_vnc_viewer_data_error",
            )

    ##### VNC FILE VIEWER

    def get_vnc_file(self, dict, id, clientos, remote_addr=False):
        ## Should check if ssl in use: dict['tlsport']:
        hostname = dict["host"]
        # ~ if dict['tlsport']:
        # ~ return False
        # ~ os='MacOS'
        if clientos in ["iOS", "Windows", "Android", "Linux", "generic", None]:
            consola = """[Connection]
            Host=%s
            Port=%s
            Password=%s

            [Options]
            UseLocalCursor=1
            UseDesktopResize=1
            FullScreen=1
            FullColour=0
            LowColourLevel=0
            PreferredEncoding=ZRLE
            AutoSelect=1
            Shared=0
            SendPtrEvents=1
            SendKeyEvents=1
            SendCutText=1
            AcceptCutText=1
            Emulate3=1
            PointerEventInterval=0
            Monitor=
            MenuKey=F8
            """ % (
                hostname,
                dict["port"],
                dict["passwd"],
            )
            consola = consola.replace("'", "")
            return "vnc", "text/plain", consola

        if clientos in ["MacOS"]:
            vnc = (
                "vnc://"
                + hostname
                + ":"
                + dict["passwd"]
                + "@"
                + hostname
                + ":"
                + dict["port"]
            )
            consola = """<?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
            <dict>
                <key>URL</key>
                <string>%s</string>
                <key>restorationAttributes</key>
                <dict>
                    <key>autoClipboard</key>
                    <false/>
                    <key>controlMode</key>
                    <integer>1</integer>
                    <key>isFullScreen</key>
                    <false/>
                    <key>quality</key>
                    <integer>3</integer>
                    <key>scalingMode</key>
                    <true/>
                    <key>screenConfiguration</key>
                    <dict>
                        <key>GlobalIsMixedMode</key>
                        <false/>
                        <key>GlobalScreen</key>
                        <dict>
                            <key>Flags</key>
                            <integer>0</integer>
                            <key>Frame</key>
                            <string>{{0, 0}, {1920, 1080}}</string>
                            <key>Identifier</key>
                            <integer>0</integer>
                            <key>Index</key>
                            <integer>0</integer>
                        </dict>
                        <key>IsDisplayInfo2</key>
                        <false/>
                        <key>IsVNC</key>
                        <true/>
                        <key>ScaledSelectedScreenRect</key>
                        <string>(0, 0, 1920, 1080)</string>
                        <key>Screens</key>
                        <array>
                            <dict>
                                <key>Flags</key>
                                <integer>0</integer>
                                <key>Frame</key>
                                <string>{{0, 0}, {1920, 1080}}</string>
                                <key>Identifier</key>
                                <integer>0</integer>
                                <key>Index</key>
                                <integer>0</integer>
                            </dict>
                        </array>
                    </dict>
                    <key>selectedScreen</key>
                    <dict>
                        <key>Flags</key>
                        <integer>0</integer>
                        <key>Frame</key>
                        <string>{{0, 0}, {1920, 1080}}</string>
                        <key>Identifier</key>
                        <integer>0</integer>
                        <key>Index</key>
                        <integer>0</integer>
                    </dict>
                    <key>targetAddress</key>
                    <string>%s</string>
                    <key>viewerScaleFactor</key>
                    <real>1</real>
                    <key>windowContentFrame</key>
                    <string>{{0, 0}, {1829, 1029}}</string>
                    <key>windowFrame</key>
                    <string>{{45, 80}, {1829, 1097}}</string>
                </dict>
            </dict>
            </plist>""" % (
                vnc,
                vnc,
            )
            consola = consola.replace("'", "")
            return "vncloc", "text/plain", consola
