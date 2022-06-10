# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import os

#!/usr/bin/env python
# coding=utf-8
import sys

import rethinkdb as r

from webapp import app

from ..lib.log import *
from .flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

import base64
import urllib
from http.cookies import SimpleCookie

from ..lib.viewer_exc import *


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


class isardViewer:
    def __init__(self):
        # Offset from base_port == spice
        self.spice = 0
        self.spice_tls = 1
        self.vnc = 2
        self.vnc_tls = 3
        self.vnc_ws = -198  # 5900-200????
        pass

    def viewer_data(
        self,
        id,
        get_viewer="spice-client",
        current_user=False,
        default_viewer=False,
        get_cookie=True,
    ):
        try:
            with app.app_context():
                domain = (
                    r.table("domains")
                    .get(id)
                    .pluck("id", "name", "status", "viewer", "options", "user", "tag")
                    .run(db.conn)
                )
        except DomainNotFound:
            raise
        if not domain["status"] in ["Started", "Shutting-down", "Stopping"]:
            raise DomainNotStarted
        if current_user != False:
            # if not owner and not his tag
            if domain["user"] != current_user.id:
                with app.app_context():
                    deployment = r.table("deployments").get(domain["tag"]).run(db.conn)
                if deployment is None or deployment["user"] != current_user.id:
                    return False

        if (
            "preferred" not in domain["options"]["viewers"].keys()
            or not domain["options"]["viewers"]["preferred"] == default_viewer
        ):
            with app.app_context():
                r.table("domains").get(id).update(
                    {"options": {"viewers": {"preferred": default_viewer}}}
                ).run(db.conn)

        if get_viewer == "rdp-client":
            return {
                "kind": "file",
                "name": "isard-rdp",
                "ext": "rdp",
                "mime": "application/x-rdp",
                "content": self.get_rdp_file(domain["viewer"]["guest_ip"]),
            }

        if get_viewer == "spice-html5":
            port = domain["viewer"]["base_port"]
            if get_cookie:
                cookie = base64.b64encode(
                    json.dumps(
                        {
                            "web_viewer": {
                                "vmName": domain["name"],
                                "vmHost": domain["viewer"]["proxy_hyper_host"],
                                "vmPort": str(domain["viewer"]["base_port"]),
                                "host": domain["viewer"]["proxy_video"],
                                "port": "443",
                                "token": domain["viewer"]["passwd"],
                            }
                        }
                    ).encode("utf-8")
                ).decode("utf-8")
                uri = (
                    "https://"
                    + domain["viewer"]["static"]
                    + "/viewer/spice-web-client/",
                )
                return {"kind": "url", "viewer": uri, "cookie": cookie}
            else:
                return (
                    "https://"
                    + domain["viewer"]["static"]
                    + "/viewer/spice-web-client/?vmName="
                    + urllib.parse.quote_plus(domain["name"])
                    + "&vmHost="
                    + domain["viewer"]["proxy_hyper_host"]
                    + "&host="
                    + domain["viewer"]["proxy_video"]
                    + "&port="
                    + str(port)
                    + "&passwd="
                    + domain["viewer"]["passwd"]
                )

        if get_viewer == "vnc-html5":
            vmPort = str(domain["viewer"]["base_port"] + self.vnc)
            port = (
                str(domain["viewer"]["html5_ext_port"])
                if "html5_ext_port" in domain["viewer"].keys()
                else "443"
            )
            if get_cookie:
                cookie = base64.b64encode(
                    json.dumps(
                        {
                            "web_viewer": {
                                "vmName": domain["name"],
                                "vmHost": domain["viewer"]["proxy_hyper_host"],
                                "vmPort": vmPort,
                                "host": domain["viewer"]["proxy_video"],
                                "port": port,
                                "token": domain["viewer"]["passwd"],
                            }
                        }
                    ).encode("utf-8")
                ).decode("utf-8")
                uri = ("https://" + domain["viewer"]["static"] + "/viewer/noVNC/",)
                return {"kind": "url", "viewer": uri, "cookie": cookie}
            else:
                return (
                    "https://"
                    + domain["viewer"]["static"]
                    + "/viewer/noVNC/?vmName="
                    + urllib.parse.quote_plus(domain["name"])
                    + "&vmHost="
                    + domain["viewer"]["proxy_hyper_host"]
                    + "&host="
                    + domain["viewer"]["proxy_video"]
                    + "&port="
                    + port
                    + "&vmPort="
                    + vmPort
                    + "&passwd="
                    + domain["viewer"]["passwd"]
                )

        if get_viewer == "rdp-html5":
            vmPort = str(domain["viewer"]["base_port"] + self.vnc)
            port = (
                str(domain["viewer"]["html5_ext_port"])
                if "html5_ext_port" in domain["viewer"].keys()
                else "443"
            )
            if get_cookie:
                cookie = base64.b64encode(
                    json.dumps(
                        {
                            "web_viewer": {
                                "vmName": domain["name"],
                                "vmHost": domain["viewer"]["guest_ip"],
                                "vmUsername": domain["options"]["credentials"][
                                    "username"
                                ]
                                if "credentials" in domain["options"]
                                else "",
                                "vmPassword": domain["options"]["credentials"][
                                    "password"
                                ]
                                if "credentials" in domain["options"]
                                else "",
                                "host": domain["viewer"]["proxy_video"],
                                "port": port,
                            }
                        }
                    ).encode("utf-8")
                ).decode("utf-8")
                uri = (f"https://{domain['viewer']['static']}/Rdp",)
                return {"kind": "url", "viewer": uri, "cookie": cookie}
            else:
                return "https://" + domain["viewer"]["static"] + "/notavailable"

        if get_viewer == "spice-client":
            port = domain["viewer"]["base_port"] + self.spice_tls
            vmPort = (
                domain["viewer"]["spice_ext_port"]
                if "spice_ext_port" in domain["viewer"].keys()
                else "80"
            )
            consola = self.get_spice_file(domain, vmPort, port)
            if get_cookie:
                return {
                    "kind": "file",
                    "ext": consola[0],
                    "mime": consola[1],
                    "content": consola[2],
                }
            else:
                return consola[2]

        if get_viewer == "vnc-client":
            return False
        if get_viewer == "vnc-client-macos":
            return False
        return False

    def get_rdp_file(self, ip):
        ## This are the default values dumped from a windows rdp client connection to IsardVDI
        # connection type:i:7
        # networkautodetect:i:1
        # bandwidthautodetect:i:1
        # displayconnectionbar:i:1
        # username:s:
        # enableworkspacereconnect:i:0
        # disable wallpaper:i:0
        # allow font smoothing:i:0
        # allow desktop composition:i:0
        # disable full window drag:i:1
        # disable menu anims:i:1
        # disable themes:i:0
        # disable cursor setting:i:0
        # bitmapcachepersistenable:i:1
        # audiomode:i:0
        # redirectprinters:i:1
        # redirectcomports:i:0
        # redirectsmartcards:i:1
        # redirectclipboard:i:1
        # redirectposdevices:i:0
        # drivestoredirect:s:
        # autoreconnection enabled:i:1
        # authentication level:i:2
        # prompt for credentials:i:0
        # negotiate security layer:i:1
        # remoteapplicationmode:i:0
        # alternate shell:s:
        # shell working directory:s:
        # gatewayhostname:s:
        # gatewayusagemethod:i:4
        # gatewaycredentialssource:i:4
        # gatewayprofileusagemethod:i:0
        # promptcredentialonce:i:0
        # gatewaybrokeringtype:i:0
        # use redirection server name:i:0
        # rdgiskdcproxy:i:0
        # kdcproxyname:s:
        return """full address:s:%s
""" % (
            ip
        )

    def get_spice_file(self, domain, port, vmPort):
        op_fscr = int(
            domain.get("options", {})
            .get("viewers", {})
            .get("spice", {})
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
        title=%s:%sd - Prem SHIFT+F12 per sortir
        enable-smartcard=0
        enable-usb-autoshare=1
        delete-this-file=1
        usb-filter=-1,-1,-1,-1,0
        tls-ciphers=DEFAULT
        """ % (
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

        consola = (
            consola
            + """%shost-subject=%s
        %sca=%r
        toggle-fullscreen=shift+f11
        release-cursor=shift+f12
        secure-attention=ctrl+alt+end
        secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard"""
            % (
                "" if domain["viewer"]["tls"]["host-subject"] != False else ";",
                domain["viewer"]["tls"]["host-subject"],
                "" if domain["viewer"]["tls"]["certificate"] != False else ";",
                domain["viewer"]["tls"]["certificate"],
            )
        )

        consola = consola.replace("'", "")
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
                "uri": "https://" + hostnames["proxy"] + "/viewer/noVNC",
                "cookie": cookie,
            }

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
            log.error("Viewer for domain " + domain["name"] + " exception:" + str(e))
            return False

    # ~ def get_domain_vnc_data(self, domain, hostnames, viewer, port, tlsport, selfsigned, remote_addr=False):
    # ~ try:
    # ~ ''' VNC does not have ssl. Only in websockets is available '''
    # ~ if viewer['defaultMode'] == "Secure" and domain['viewer']['port_spice_ssl'] != False:
    # ~ return {'host':hostname,
    # ~ 'name': domain['name'],
    # ~ 'port': port,
    # ~ 'wsport': str(int(port)+500),
    # ~ 'ca':viewer['certificate'],
    # ~ 'domain':viewer['domain'],
    # ~ 'host-subject':viewer['host-subject'],
    # ~ 'passwd': domain['viewer']['passwd'],
    # ~ 'uri': 'https://<domain>/wsviewer/novnclite'+selfsigned+'/?host='+hostname+'&port='+str(int(port))+'&password='+domain['viewer']['passwd'],
    # ~ 'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}
    # ~ if viewer['defaultMode'] == "Insecure" and domain['viewer']['port_spice'] != False:
    # ~ return {'host':hostname,
    # ~ 'name': domain['name'],
    # ~ 'port': port,
    # ~ 'wsport': str(int(port)+500),
    # ~ 'ca':viewer['certificate'],
    # ~ 'domain':viewer['domain'],
    # ~ 'host-subject':viewer['host-subject'],
    # ~ 'passwd': domain['viewer']['passwd'],
    # ~ 'uri': 'http://<domain>/wsviewer/novnclite/?host='+hostname+'&port='+str(int(port))+'&password='+domain['viewer']['passwd'],
    # ~ 'options': domain['options']['viewers']['vnc'] if 'vnc' in domain['options']['viewers'].keys() else False}
    # ~ log.error('No available VNC Viewer for domain '+domain['name']+' exception:'+str(e))
    # ~ return False
    # ~ except Exception as e:
    # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
    # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    # ~ log.error(exc_type, fname, exc_tb.tb_lineno)
    # ~ log.error('Viewer for domain '+domain['name']+' exception:'+str(e))
    # ~ return False

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
