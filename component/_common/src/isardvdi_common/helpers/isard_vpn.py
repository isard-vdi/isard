#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Pau Abril Iranzo
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


import os
import traceback
from pydoc import describe

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


class IsardVpn(RethinkSharedConnection):
    """_From api/libv2/isardVpn.py_"""

    @classmethod
    def vpn_data(cls, vpn, kind, op_sys, itemid=False):
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
            with cls._rdb_context():
                wgdata = (
                    r.table("users")
                    .get(itemid)
                    .pluck("id", "vpn")
                    .run(cls._rdb_connection)
                )
            port = os.environ.get("WG_USERS_PORT", "443")
            mtu = "1420"
            # Wireguard Android client doesn't support PostUp
            # removing the line from the config works on Windows and GNU/Linux too
            postup = None
            endpoint = os.environ.get("DOMAIN")

        if vpn == "hypers":
            with cls._rdb_context():
                try:
                    hyper = (
                        r.table("hypervisors")
                        .get(itemid)
                        .pluck("id", "isard_hyper_vpn_host", "vpn")
                        .run(cls._rdb_connection)
                    )
                    if hyper is None:
                        raise Error(
                            "not_found",
                            "Hypervisor not found for id " + str(itemid),
                            description_code="hypervisor_not_found",
                        )
                except Error:
                    raise
                except Exception:
                    raise Error(
                        "not_found",
                        "Hypervisor not found for id " + str(itemid),
                        traceback.format_exc(),
                        description_code="hypervisor_not_found",
                    )
            wgdata = hyper
            port = "4443"
            # WG interface MTU = INFRASTRUCTURE_MTU - 60 (WireGuard overhead).
            # Same formula in both tunneling modes; in geneve-only the WG
            # interface is unused (wgadmin skips it) but the value is still
            # recorded so the config file is sane if the mode flips.
            infra = os.environ.get("INFRASTRUCTURE_MTU")
            vpn_mtu_legacy = os.environ.get("VPN_MTU")
            if infra:
                mtu = str(int(infra) - 60)
            elif vpn_mtu_legacy:
                mtu = vpn_mtu_legacy
            else:
                mtu = "1440"  # 1500 - 60
            postup = "iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu"
            endpoint = hyper.get("isard_hyper_vpn_host", "isard-vpn")

        if vpn == "remotevpn":
            with cls._rdb_context():
                wgdata = (
                    r.table("remotevpn")
                    .get(itemid)
                    .pluck("id", "vpn")
                    .run(cls._rdb_connection)
                )
            port = "443"
            infra = os.environ.get("INFRASTRUCTURE_MTU")
            vpn_mtu_legacy = os.environ.get("VPN_MTU")
            if infra:
                mtu = str(int(infra) - 60)
            elif vpn_mtu_legacy:
                mtu = vpn_mtu_legacy
            else:
                mtu = "1440"
            # Wireguard Android client doesn't support PostUp
            # removing the line from the config works on Windows and GNU/Linux too
            postup = None
            endpoint = os.environ.get("DOMAIN")

        if wgdata == None or "vpn" not in wgdata.keys():
            raise Error(
                "not_found",
                "Vpn data not found for kind " + str(vpn) + " and id " + str(itemid),
                traceback.format_exc(),
                description_code="vpn_data_not_found",
            )

        # Race: isard-vpn writes the server keys (sysconfig) before it writes
        # the per-peer wireguard subtree. Between those two writes the server-keys
        # check below passes but get_wireguard_file would KeyError on
        # peer["vpn"]["wireguard"][...]. Surface a typed 4xx so callers retry.
        # In geneve-only infrastructure the hypervisor has no WireGuard peer
        # subtree by design (isard-vpn skips WireGuard for hypers and sets up
        # a geneve port instead), so this race-guard must not apply to it —
        # otherwise hypervisor registration 428s forever. Mirrors main, which
        # has no such guard on the geneve-only path.
        geneve_only_hyper = (
            vpn == "hypers"
            and os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
        )
        if not geneve_only_hyper:
            peer_wg = (wgdata.get("vpn") or {}).get("wireguard") or {}
            if not all(k in peer_wg for k in ("Address", "keys", "AllowedIPs")):
                raise Error(
                    "precondition_required",
                    "Vpn peer config not yet initialized for kind "
                    + str(vpn)
                    + " and id "
                    + str(itemid)
                    + ". Try again in a few seconds...",
                    traceback.format_exc(),
                    description_code="vpn_peer_not_ready",
                )

        ## First up time the wireguard config keys are missing till isard-vpn populates it.
        # if not getattr(app, "wireguard_server_keys", False):
        if vpn == "hypers":
            vpn_kind_keys = "vpn_hypers"
        else:
            vpn_kind_keys = "vpn_users"
        with cls._rdb_context():
            sysconfig = r.db("isard").table("config").get(1).run(cls._rdb_connection)
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
                "content": cls.get_wireguard_file(*wireguard_data),
            }
        elif kind == "install":
            ext = "sh" if op_sys == "Linux" else "vb"
            return {
                "kind": "file",
                "name": "isard-vpn-setup",
                "ext": ext,
                "mime": "text/plain",
                "content": cls.get_wireguard_install_script(wireguard_data),
            }

        # Unknown kind — translate to a typed bad_request so the
        # webapp/Vue frontend gets a clear 400 instead of a generic
        # 500. Valid kinds are config / install.
        raise Error(
            "bad_request",
            f"Unknown VPN kind {kind!r}; expected one of: config, install",
            traceback.format_exc(),
            description_code="vpn_kind_invalid",
        )

    @classmethod
    def get_wireguard_file(
        cls, endpoint, peer, port, mtu, postup, wireguard_server_keys
    ):
        return f"""[Interface]
Address = {peer["vpn"]["wireguard"]["Address"]}
PrivateKey = {peer["vpn"]["wireguard"]["keys"]["private"]}
MTU = {mtu}
{f"PostUp = {postup}" if postup else ""}

[Peer]
PublicKey = {wireguard_server_keys["public"]}
Endpoint = {endpoint}:{port}
AllowedIPs = {peer["vpn"]["wireguard"]["AllowedIPs"]}
PersistentKeepalive = 25
"""

    @classmethod
    def get_wireguard_install_script(cls, wireguard_data):
        wireguard_file_contents = cls.get_wireguard_file(*wireguard_data)
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
