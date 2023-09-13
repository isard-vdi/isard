# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import os
import traceback
from pydoc import describe

from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error
from ..libv2.log import *

r = RethinkDB()

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)


class isardVpn:
    def __init__(self):
        pass

    def vpn_data(self, vpn, kind, op_sys, itemid=False):
        if vpn not in ["users", "hypers", "remotevpn"]:
            raise Error(
                "bad_request",
                "Vpn kind " + str(vpn) + " does not exist",
                traceback.format_exc(),
                description_code="vpn_kind_not_found",
            )
        if not itemid:
            raise Error(
                "bad_request",
                "Vpn " + str(vpn) + " missing itemid",
                traceback.format_exc(),
                description_code="vpn_missing_itemid",
            )

        if vpn == "users":
            with app.app_context():
                wgdata = r.table("users").get(itemid).pluck("id", "vpn").run(db.conn)
            port = os.environ.get("WG_USERS_PORT", "443")
            mtu = "1420"
            # Wireguard Windows client doesn't support PostUp empty value
            # colon command does nothing on Windows and GNU/Linux
            postup = ":"
            endpoint = os.environ["DOMAIN"]

        if vpn == "hypers":
            with app.app_context():
                hyper = (
                    r.table("hypervisors")
                    .get(itemid)
                    .pluck("id", "isard_hyper_vpn_host", "vpn")
                    .run(db.conn)
                )
            wgdata = hyper
            port = "4443"
            mtu = os.environ.get("VPN_MTU", "1600")
            postup = "iptables -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu"
            endpoint = hyper.get("isard_hyper_vpn_host", "isard-vpn")

        if vpn == "remotevpn":
            with app.app_context():
                wgdata = (
                    r.table("remotevpn").get(itemid).pluck("id", "vpn").run(db.conn)
                )
            port = "443"
            mtu = os.environ.get("VPN_MTU", "1600")
            # Windows client doesn't support PostUp empty value
            # colon command does nothing on Windows and GNU/Linux
            postup = ":"
            endpoint = os.environ["DOMAIN"]

        if wgdata == None or "vpn" not in wgdata.keys():
            raise Error(
                "not_found",
                "Vpn data not found for kind " + str(vpn) + " and id " + str(itemid),
                traceback.format_exc(),
                description_code="vpn_data_not_found",
            )

        ## First up time the wireguard config keys are missing till isard-vpn populates it.
        if not getattr(app, "wireguard_server_keys", False):
            if vpn == "hypers":
                vpn_kind_keys = "vpn_hypers"
            else:
                vpn_kind_keys = "vpn_users"
            sysconfig = r.db("isard").table("config").get(1).run(db.conn)
            wireguard_server_keys = (
                sysconfig.get(vpn_kind_keys, {}).get("wireguard", {}).get("keys", False)
            )
        if not wireguard_server_keys:
            raise Error(
                "precondition_required",
                "There are no wireguard keys in db config yet. Try again in a few seconds...",
                traceback.format_exc(),
                description_code="no_wireguard_keys",
            )

        wireguard_data = [endpoint, wgdata, port, mtu, postup, wireguard_server_keys]
        if kind == "config":
            return {
                "kind": "file",
                "name": "isard-vpn",
                "ext": "conf",
                "mime": "text/plain",
                "content": self.get_wireguard_file(*wireguard_data),
            }
        elif kind == "install":
            ext = "sh" if op_sys == "Linux" else "vb"
            return {
                "kind": "file",
                "name": "isard-vpn-setup",
                "ext": ext,
                "mime": "text/plain",
                "content": self.get_wireguard_install_script(wireguard_data),
            }

        raise Error(
            "internal_server",
            "Unable to process vpn file",
            traceback.format_exc(),
            description_code="unable_to_process_vpnfile",
        )

    def get_wireguard_file(
        self, endpoint, peer, port, mtu, postup, wireguard_server_keys
    ):
        return """[Interface]
Address = %s
PrivateKey = %s
MTU = %s
PostUp = %s

[Peer]
PublicKey = %s
Endpoint = %s:%s
AllowedIPs = %s
PersistentKeepalive = 25
""" % (
            peer["vpn"]["wireguard"]["Address"],
            peer["vpn"]["wireguard"]["keys"]["private"],
            mtu,
            postup,
            wireguard_server_keys["public"],
            endpoint,
            port,
            peer["vpn"]["wireguard"]["AllowedIPs"],
        )

    def get_wireguard_install_script(self, wireguard_data):
        wireguard_file_contents = self.get_wireguard_file(*wireguard_data)
        return f"""#!/bin/bash
echo "Installing wireguard. Ubuntu/Debian script."
apt install -y wireguard git dh-autoreconf libglib2.0-dev intltool build-essential libgtk-3-dev libnma-dev libsecret-1-dev network-manager-dev resolvconf
git clone https://github.com/max-moser/network-manager-wireguard
cd network-manager-wireguard
./autogen.sh --without-libnm-glib
./configure --without-libnm-glib --prefix=/usr --sysconfdir=/etc --libdir=/usr/lib/x86_64-linux-gnu --libexecdir=/usr/lib/NetworkManager --localstatedir=/var
make   
sudo make install
cd ..
echo "{wireguard_file_contents}" > isard-vpn.conf
echo "You have your user vpn configuration to use it with NetworkManager: isard-vpn.conf"""
