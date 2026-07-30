import os
import socket

from rethinkdb import RethinkDB

r = RethinkDB()
import ipaddress
import logging as log
import subprocess
import threading
import time
import traceback
from subprocess import check_output

from changefeed_models.hypervisors_row import HypervisorsRow
from changefeed_models.users_row import UsersRow
from db import vpn_rethink_conn
from pydantic import BaseModel
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError
from simple_iptools import UserIpTools


def _get_infra_mtu():
    """Get infrastructure MTU with VPN_MTU backward compat."""
    val = os.environ.get("INFRASTRUCTURE_MTU")
    if val:
        return int(val)
    vpn_mtu = os.environ.get("VPN_MTU")
    if vpn_mtu:
        log.warning("VPN_MTU is deprecated, use INFRASTRUCTURE_MTU instead")
        return int(vpn_mtu) + 60
    return 1500  # safe Ethernet default; same for both tunneling modes


class Keys(object):
    def __init__(self, interface="wg0"):
        self.interface = interface
        self.wg = "/usr/bin/wg"
        self.skeys = {"private": False, "public": False}
        self.update_clients = False
        self.check_server_cert()

    def gen_private_key(self):
        return check_output((self.wg, "genkey"), text=True).strip()

    def gen_public_key(self, private_key):
        return check_output((self.wg, "pubkey"), input=private_key, text=True).strip()

    def gen_server_keys(self):
        ## Private goes in wg0.conf [Interface] config
        self.skeys["private"] = self.gen_private_key()
        ## Public goes in all client config [Peer]
        self.skeys["public"] = self.gen_public_key(self.skeys["private"])

    def new_client_keys(self):
        private = self.gen_private_key()
        return {"private": private, "public": self.gen_public_key(private)}

    def gen_presharedkey(self):
        return check_output((self.wg, "genpsk"), text=True).strip()

    def check_server_cert(self):
        # Check old server key with new server key that matches.
        # If new key found then all client keys should be updated!
        update_clients = False

        try:
            with open("/certs/" + self.interface + "_private.key", "r") as f:
                actual_private_key = f.read()
            with open("/certs/" + self.interface + "_public.key", "r") as f:
                actual_public_key = f.read()
        except FileNotFoundError:
            self.gen_server_keys()
            actual_private_key = self.skeys["private"]
            actual_public_key = self.skeys["public"]
            ## Generate new ones
        except Exception as e:
            log.error("Server read keys internal error: \n" + traceback.format_exc())
            exit(1)

        with vpn_rethink_conn() as conn:
            old_key = r.table("config").get(1).pluck("vpn_" + self.interface).run(conn)
            if (
                "vpn_" + self.interface not in old_key.keys()
                or actual_private_key
                != old_key["vpn_" + self.interface]["wireguard"]["keys"]["private"]
            ):
                r.table("config").get(1).update(
                    {
                        "vpn_"
                        + self.interface: {
                            "wireguard": {
                                "keys": {
                                    "private": actual_private_key,
                                    "public": actual_public_key,
                                }
                            }
                        }
                    }
                ).run(conn)
                update_clients = True
                try:
                    with open("/certs/" + self.interface + "_private.key", "w") as f:
                        f.write(actual_private_key)
                    with open("/certs/" + self.interface + "_public.key", "w") as f:
                        f.write(actual_public_key)
                except Exception as e:
                    log.error(
                        "Server write keys internal error: \n" + traceback.format_exc()
                    )
                    exit(1)
        self.skeys = {"private": actual_private_key, "public": actual_public_key}


class Wg(object):
    def _to_model(self, data):
        """Convert a raw dict to the appropriate Row model. Pass models through."""
        if isinstance(data, BaseModel):
            return data
        # Use UsersRow for both 'users' and 'remotevpn' — vpn fields overlap
        if self.table == "hypervisors":
            return HypervisorsRow.model_validate(data)
        return UsersRow.model_validate(data)

    @staticmethod
    def _to_dict(peer):
        if isinstance(peer, BaseModel):
            return peer.model_dump()
        return peer

    def __init__(
        self,
        interface="wg0",
        clients_net="10.0.0.0/24",
        table="users",
        server_port="443",
        allowed_client_nets="0.0.0.0/0",
        reset_client_certs=False,
    ):
        self.interface = interface
        self.table = table
        self.server_port = server_port
        self.allowed_client_nets = allowed_client_nets
        self.clients_net = clients_net

        # Get actual server keys or generate new ones
        self.keys = Keys(interface)

        self.server_mask = clients_net.split("/")[1]
        self.server_net = ipaddress.ip_network(clients_net, strict=False)

        # Get first one from range for us!
        self.server_ip = str(self.server_net[1])

        self.clients_reserved_ips = {self.server_ip}
        # Get existing users wireguard config and generate new one's if not exist.
        self.init_server()
        self.init_peers(reset_client_certs)

        self.uipt = UserIpTools()

        if table == "users":
            self.set_initial_rules()

    def init_server(self):
        ## Server config
        try:
            subprocess.run(["ip", "address", "show", self.interface])
            log.info("Bringing down wireguard " + self.interface + " interface")
            subprocess.run(["/usr/bin/wg-quick", "down", self.interface])
        except:
            log.info("Wireguard interface " + self.interface + " already exists")
        if self.table == "hypervisors":
            # WG interface MTU = INFRASTRUCTURE_MTU - 60 (WireGuard overhead).
            # Same formula in both tunneling modes; in geneve-only the WG
            # interface is unused (wgadmin skips it) but the value is still
            # recorded so the config file is sane if the mode flips.
            mtu = str(_get_infra_mtu() - 60)
            geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
            if geneve_only:
                postup = ""
            else:
                postup = "iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu"
        else:
            # user-WG faces the internet; cap at safe Ethernet MTU regardless of INFRASTRUCTURE_MTU
            mtu = str(min(_get_infra_mtu() - 60, 1420))
            postup = ""
        self.config = self.server_config(mtu, postup)
        # for k,v in self.peers.items():
        #    self.set_iptables(v)
        #    self.config=self.config+self.gen_peer_config(v)
        with open("/etc/wireguard/" + self.interface + ".conf", "w") as f:
            f.write(self.config)
        log.info("Bringing up wireguard " + self.interface + " interface")
        check_output(("/usr/bin/wg-quick", "up", self.interface), text=True).strip()
        ## End server config

    _INIT_PEERS_BATCH = 100

    def _flush_peers_batch(self, table, batch, inserted, total_expected, started_at):
        """Insert one chunk of generated peers into ``table`` and log
        progress + ETA. Called from :meth:`init_peers` whenever
        ``create_peers`` reaches ``_INIT_PEERS_BATCH`` (and once at the
        end with the remainder). No-op if ``batch`` is empty.
        """
        if not batch:
            return
        with vpn_rethink_conn() as conn:
            # update, not insert: a row deleted while the batch was generating
            # configs must not be recreated as an {id, vpn} stub.
            written = (
                r.expr(batch)
                .for_each(lambda peer: r.table(table).get(peer["id"]).update(peer))
                .run(conn)
            )
        if written.get("skipped"):
            # Nothing to undo (these come up later from the drain), but say so:
            # a silently dropped config leaves a user with no vpn and no trace.
            log.warning(
                "init_peers[%s]: %d of %d rows vanished while their config was "
                "generated; their peers were not written",
                table,
                written["skipped"],
                len(batch),
            )
        elapsed = max(time.monotonic() - started_at, 1e-6)
        rate = inserted / elapsed
        remaining = max(total_expected - inserted, 0)
        eta = remaining / rate if rate > 0 else 0.0
        log.info(
            "init_peers[%s]: db-backfill %d/%d (batch=%d, rate=%.0f/s, eta=%.0fs)",
            table,
            inserted,
            total_expected,
            len(batch),
            rate,
            eta,
        )

    def _start_background_up_peers(self, peers, remotevpn_peers):
        """Launch the daemon thread that drains the collected up_peer
        work. No-op if both lists are empty so we don't spawn idle
        threads. Daemon=True so the thread dies with the process; the
        wgadmin retry loop will create a new Wg() and a new thread on
        the next iteration if the previous run crashed.
        """
        if not peers and not remotevpn_peers:
            return
        thread = threading.Thread(
            target=self._run_background_up_peers,
            args=(list(peers), list(remotevpn_peers) if remotevpn_peers else []),
            daemon=True,
            name=f"init_peers_up_{self.table}_{self.interface}",
        )
        thread.start()

    def _run_background_up_peers(self, peers, remotevpn_peers):
        """Body of the background ``up_peer`` thread.

        Walks ``peers`` first (the primary table), then any remotevpn
        peers if this Wg instance owns the users table. Catches all
        exceptions per-iteration so one bad peer doesn't poison the rest
        of the batch.
        """
        try:
            self._drain_up_peer_queue(self.table, peers)
            if remotevpn_peers:
                self._drain_up_peer_queue("remotevpn", remotevpn_peers)
        except Exception:
            log.exception(
                "init_peers[%s]: background up_peer terminated unexpectedly",
                self.table,
            )

    def _drain_up_peer_queue(self, table, peers):
        """Run ``up_peer`` for every entry in ``peers`` and log progress +
        ETA every ``_INIT_PEERS_BATCH`` (and once at the end).
        """
        total = len(peers)
        if total == 0:
            return
        log.info("init_peers[%s]: background up_peer starting (%d peers)", table, total)
        started_at = time.monotonic()
        for i, peer in enumerate(peers, start=1):
            try:
                self.up_peer(self._to_model(peer))
            except Exception:
                log.exception(
                    "init_peers[%s]: up_peer failed for %s",
                    table,
                    peer.get("id", "?") if isinstance(peer, dict) else "?",
                )
            if i % self._INIT_PEERS_BATCH == 0 or i == total:
                elapsed = max(time.monotonic() - started_at, 1e-6)
                rate = i / elapsed
                remaining = total - i
                eta = remaining / rate if rate > 0 else 0.0
                log.info(
                    "init_peers[%s]: up_peer %d/%d (rate=%.1f/s, eta=%.0fs)",
                    table,
                    i,
                    total,
                    rate,
                    eta,
                )
        log.info(
            "init_peers[%s]: background up_peer complete (%d peers in %.0fs)",
            table,
            total,
            time.monotonic() - started_at,
        )

    def init_peers(self, reset=False):
        with vpn_rethink_conn() as conn:
            # This will reset all vpn config on restart.
            if reset == True:
                log.info("Reset %s peer certificates...", self.table)
                r.table(self.table).replace(r.row.without("vpn")).run(conn)
                if self.table == "users":
                    r.table("remotevpn").replace(r.row.without("vpn")).run(conn)

            log.info("Initializing peers...")
            if self.table == "hypervisors":
                # Exclude geneve-only hypervisors from WireGuard initialization
                wglist = list(
                    r.table(self.table)
                    .pluck("id", "vpn")
                    .filter(
                        lambda hyper: r.expr(["wireguard+geneve", None]).contains(
                            hyper["vpn"].get_field("tunneling_mode").default(None)
                        )
                    )
                    .run(conn)
                )
                # wglist = [d for d in wglist if d['id'] != 'isard-hypervisor']
            elif self.table == "users":
                wglist = list(
                    r.table(self.table).pluck("id", "vpn", "active").run(conn)
                )
                wglist_remotevpn = list(
                    r.table("remotevpn").pluck("id", "vpn").run(conn)
                )

        self.clients_reserved_ips.update(
            p["vpn"]["wireguard"]["Address"]
            for p in wglist
            if "vpn" in p.keys()
            and isinstance((p.get("vpn") or {}).get("wireguard"), dict)
            and "Address" in p["vpn"]["wireguard"]
        )

        # Expected total up front so the progress log has an ETA. The lazy-init
        # and key-rotation paths are mutually exclusive per peer.
        lazy_init_expected = sum(
            1
            for p in wglist
            if "vpn" not in p.keys()
            or not isinstance((p.get("vpn") or {}).get("wireguard"), dict)
        )
        rotation_expected = sum(
            1
            for p in wglist
            if "vpn" in p.keys()
            and isinstance((p.get("vpn") or {}).get("wireguard"), dict)
            and (
                self.keys.update_clients == True
                or not p["vpn"]["wireguard"].get("keys")
            )
        )
        total_expected = lazy_init_expected + rotation_expected

        peers_to_up = []
        remotevpn_to_up = []
        create_peers = []
        inserted = 0
        started_at = time.monotonic()
        if self.keys.update_clients == True:
            log.info("Server key changed. Generating new client keys for all users...")
        if total_expected:
            log.info(
                "init_peers[%s]: %d peers to backfill (%d lazy-init, %d key-rotation)",
                self.table,
                total_expected,
                lazy_init_expected,
                rotation_expected,
            )
        for peer in wglist:
            new_peer = False
            # `or {}` (not a {} default) so a null vpn subtree (not just an
            # absent one) is treated as "no config yet" instead of crashing.
            wg = (peer.get("vpn") or {}).get("wireguard")
            wg_is_dict = isinstance(wg, dict)
            if self.keys.update_clients == True and "vpn" in peer.keys() and wg_is_dict:
                new_peer = peer
                new_peer["vpn"]["wireguard"]["keys"] = self.keys.new_client_keys()
                create_peers.append(new_peer)
            if "vpn" not in peer.keys() or not wg_is_dict:
                # No wireguard subtree to keep: there is no Address to preserve.
                new_peer = self.gen_new_peer(peer)
                create_peers.append(new_peer)
            elif new_peer == False and not wg.get("keys"):
                # reset_vpn() sets keys=False to request a rotation: rebuild
                # them here, keeping the assigned Address.
                new_peer = peer
                new_peer["vpn"]["wireguard"]["keys"] = self.keys.new_client_keys()
                create_peers.append(new_peer)
            # Deferred to a background thread, drained after the backfill, so the
            # wgadmin loop starts serving changefeed events immediately.
            target = peer if new_peer == False else new_peer
            if self.table == "users":
                if target.get("active") == True:
                    peers_to_up.append(target)
            else:
                peers_to_up.append(target)
            if len(create_peers) >= self._INIT_PEERS_BATCH:
                inserted += len(create_peers)
                self._flush_peers_batch(
                    self.table, create_peers, inserted, total_expected, started_at
                )
                create_peers = []
        if create_peers:
            inserted += len(create_peers)
            self._flush_peers_batch(
                self.table, create_peers, inserted, total_expected, started_at
            )

        ##### The same for remotevpn table
        if self.table == "users":
            self.clients_reserved_ips.update(
                a
                for a in [
                    ((p.get("vpn") or {}).get("wireguard") or {}).get("Address")
                    for p in wglist_remotevpn
                ]
                if a
            )

            rv_lazy_expected = sum(1 for p in wglist_remotevpn if "vpn" not in p.keys())
            rv_rotation_expected = (
                sum(
                    1 for p in wglist_remotevpn if (p.get("vpn") or {}).get("wireguard")
                )
                if self.keys.update_clients == True
                else 0
            )
            rv_total_expected = rv_lazy_expected + rv_rotation_expected

            create_peers = []
            inserted = 0
            started_at = time.monotonic()
            if self.keys.update_clients == True:
                log.info(
                    "Server key changed. Generating new client keys for all remotevpn..."
                )
            for peer in wglist_remotevpn:
                new_peer = False
                if self.keys.update_clients == True and (peer.get("vpn") or {}).get(
                    "wireguard"
                ):
                    new_peer = peer
                    new_peer["vpn"]["wireguard"]["keys"] = self.keys.new_client_keys()
                    create_peers.append(new_peer)
                if "vpn" not in peer.keys():
                    if "nets" in peer.keys() and peer["nets"] != "":
                        extra_client_nets = peer["nets"]
                    else:
                        extra_client_nets = None
                    new_peer = self.gen_new_peer(
                        peer, extra_client_nets=extra_client_nets
                    )
                    create_peers.append(new_peer)
                remotevpn_to_up.append(peer if new_peer == False else new_peer)
                if len(create_peers) >= self._INIT_PEERS_BATCH:
                    inserted += len(create_peers)
                    self._flush_peers_batch(
                        "remotevpn",
                        create_peers,
                        inserted,
                        rv_total_expected,
                        started_at,
                    )
                    create_peers = []
            if create_peers:
                inserted += len(create_peers)
                self._flush_peers_batch(
                    "remotevpn", create_peers, inserted, rv_total_expected, started_at
                )

        self._start_background_up_peers(peers_to_up, remotevpn_to_up)

    def gen_new_peer(self, peer, extra_client_nets=None):
        peer_dict = peer.model_dump() if isinstance(peer, BaseModel) else peer
        if self.table == "hypervisors":
            extra_client_nets = None
            if (peer_dict.get("vpn") or {}).get("tunneling_mode") == "geneve":
                return {"id": peer_dict["id"]}  # No WG config for geneve-only
        return {
            "id": peer_dict["id"],
            "vpn": {
                "iptables": [],
                "wireguard": {
                    "Address": self.gen_client_ip(),
                    "extra_client_nets": extra_client_nets,  ### What networks this vpn server will see on this client.
                    "keys": self.keys.new_client_keys(),
                    "AllowedIPs": self.allowed_client_nets,
                },
            },
        }  ### What networks the client will see.

    def up_peer(self, peer):
        peer = self._to_dict(peer)
        if peer.get("vpn") is None or "wireguard" not in (peer.get("vpn") or {}):
            # Geneve-only hypervisor - create direct GENEVE port
            if self.table == "hypervisors":
                hostname = peer.get("hostname") or peer["id"]
                try:
                    resolved_ip = socket.gethostbyname(hostname)
                except socket.gaierror:
                    log.error(f"Cannot resolve hostname {hostname} for {peer['id']}")
                    return False
                geneve_port_num = os.environ.get("WG_HYPERS_PORT", "4443")
                if (
                    peer["id"]
                    not in check_output(("ovs-vsctl", "show"), text=True).strip()
                ):
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "add-port",
                            "ovsbr0",
                            peer["id"],
                            "--",
                            "set",
                            "interface",
                            peer["id"],
                            "type=geneve",
                            f"options:remote_ip={resolved_ip}",
                            f"options:dst_port={geneve_port_num}",
                        ]
                    )
                else:
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "set",
                            "interface",
                            peer["id"],
                            f"options:remote_ip={resolved_ip}",
                        ]
                    )
                # BFD + VLAN 4095 flow rules apply in both the new-port and
                # existing-port paths so fresh hypervisors are not left
                # without the security policy.
                # Geneve-only: BFD is the only tunnel-liveness signal (no
                # underlying wg keepalive). Tight 200 ms intervals give
                # sub-second detection; the hypervisor side matches.
                subprocess.run(
                    [
                        "ovs-vsctl",
                        "set",
                        "Interface",
                        peer["id"],
                        "bfd:enable=true",
                        "bfd:min_tx=200",
                        "bfd:min_rx=200",
                    ]
                )
                port = check_output(
                    ("ovs-vsctl", "get", "interface", peer["id"], "ofport"),
                    text=True,
                ).strip()
                vm_mac_match = "52:54:00:00:00:00/ff:ff:ff:00:00:00"
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=451,arp,in_port={port},dl_vlan=4095,dl_src={vm_mac_match},actions=NORMAL",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=451,udp,in_port={port},dl_vlan=4095,dl_src={vm_mac_match},tp_src=68,tp_dst=67,actions=NORMAL",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=450,ip,in_port={port},dl_vlan=4095,dl_src={vm_mac_match},actions=resubmit(,2)",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=449,in_port={port},dl_vlan=4095,actions=drop",
                    ]
                )
            return True

        # Keys are False while a rotation is pending: skip the peer instead of
        # dereferencing them and breaking the whole pass.
        wg_keys = peer["vpn"]["wireguard"].get("keys")
        if not isinstance(wg_keys, dict) or not wg_keys.get("public"):
            log.warning(
                f"Skipping wireguard up_peer for {peer.get('id')}: keys not ready"
            )
            return False

        if peer["vpn"]["wireguard"]["extra_client_nets"] != None:
            address = (
                peer["vpn"]["wireguard"]["Address"]
                + ","
                + peer["vpn"]["wireguard"]["extra_client_nets"]
            )
        else:
            address = peer["vpn"]["wireguard"]["Address"]
        try:
            subprocess.run(
                [
                    "/usr/bin/wg",
                    "set",
                    self.interface,
                    "peer",
                    peer["vpn"]["wireguard"]["keys"]["public"],
                    "allowed-ips",
                    address,
                    "persistent-keepalive",
                    "25",
                ]
            )
            if peer["vpn"]["wireguard"]["extra_client_nets"] != None:
                subprocess.run(
                    [
                        "ip",
                        "route",
                        "add",
                        peer["vpn"]["wireguard"]["extra_client_nets"],
                        "dev",
                        self.interface,
                    ]
                )
            if self.table == "hypervisors":
                wg_address = peer["vpn"]["wireguard"]["Address"]
                if peer["id"] not in (
                    check_output(
                        ("ovs-vsctl", "show"),
                        text=True,
                    ).strip()
                ):
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "add-port",
                            "ovsbr0",
                            peer["id"],
                            "--",
                            "set",
                            "interface",
                            peer["id"],
                            "type=geneve",
                            "options:remote_ip=" + wg_address,
                        ]
                    )
                else:
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "set",
                            "interface",
                            peer["id"],
                            "options:remote_ip=" + wg_address,
                        ]
                    )

                # WireGuard+Geneve: do NOT enable BFD on the OVS geneve port.
                # WireGuard's own persistent-keepalive (25 s) is the tunnel
                # liveness signal we publish into hypervisors.vpn.tunnel_status
                # (derived from wg's latest_handshake). A second OVS-level BFD
                # session here costs CPU, can disagree with the hypervisor side
                # and silently park forwarding=false, and is redundant with the
                # wg health check. The VLAN 4095 flow rules below still apply in
                # both the new-port and existing-port paths so fresh
                # hypervisors are not left without the security policy.
                port = check_output(
                    ("ovs-vsctl", "get", "Interface", peer["id"], "ofport"),
                    text=True,
                ).strip()
                vm_mac_match = "52:54:00:00:00:00/ff:ff:ff:00:00:00"
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=451,arp,in_port={port},dl_vlan=4095,"
                        f"dl_src={vm_mac_match},actions=NORMAL",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=451,udp,in_port={port},dl_vlan=4095,"
                        f"dl_src={vm_mac_match},tp_src=68,tp_dst=67,"
                        f"actions=NORMAL",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=450,ip,in_port={port},dl_vlan=4095,"
                        f"dl_src={vm_mac_match},actions=resubmit(,2)",
                    ]
                )
                subprocess.run(
                    [
                        "ovs-ofctl",
                        "add-flow",
                        "ovsbr0",
                        f"priority=449,in_port={port},dl_vlan=4095,actions=drop",
                    ]
                )

                # There seems to be a bug because the route is not applied so we need to force again...
                # check_output(('/usr/bin/wg-quick','save','hypers'), text=True)
                # check_output(('/usr/bin/wg-quick','down','hypers'), text=True)
                # check_output(('/usr/bin/wg-quick','up','hypers'), text=True)
            return True
        except:
            log.error("New peer up peer error: \n" + traceback.format_exc())
            return False

    def add_peer(self, peer, table=False):
        peer = self._to_dict(peer)
        nets = peer.get("nets", "")
        if nets:
            extra_client_nets = nets
        else:
            extra_client_nets = None
        new_peer = self.gen_new_peer(peer, extra_client_nets=extra_client_nets)
        if self.up_peer(new_peer) == True:
            # if self.table=='users':
            #    self.uipt.add_user(peer["id"],new_peer['vpn']['wireguard']['Address'])
            if table == False:
                table = self.table
            with vpn_rethink_conn() as conn:
                # update, not insert: up_peer() shells out, so the row can be
                # deleted before we get here and an upsert would recreate it.
                written = r.table(table).get(new_peer["id"]).update(new_peer).run(conn)
                if written.get("skipped"):
                    # The row is gone and up_peer() already put the peer on the
                    # interface: leaving it there orphans it until a restart.
                    log.warning(
                        "add_peer: %s no longer exists in %s; removing the peer "
                        "just added to %s instead of resurrecting the row",
                        new_peer["id"],
                        table,
                        self.interface,
                    )
                    try:
                        self.down_peer(new_peer, table)
                    except Exception:
                        log.exception(
                            "add_peer: could not remove the peer for the vanished "
                            "row %s; it is now orphaned on %s",
                            new_peer["id"],
                            self.interface,
                        )
                    return
                if table == "remotevpn":
                    r.table(table).get(new_peer["id"]).replace(
                        r.row.without("nets")
                    ).run(conn)
        else:
            log.error("Error adding peer: " + peer["id"])
            try:
                self.down_peer(peer, table)
            except:
                log.error("Error removing failed peer: " + peer["id"])
        # else:
        #     if table == False:
        #         table = self.table
        #     r.table(table).get(new_peer["id"]).delete().run()

    def down_peer(self, peer, table=False):
        peer = self._to_dict(peer)
        if table == False:
            table = self.table
        if peer.get("vpn") is not None and "wireguard" in (peer.get("vpn") or {}):
            if peer["vpn"]["wireguard"]["extra_client_nets"] != None:
                subprocess.run(
                    [
                        "ip",
                        "route",
                        "del",
                        peer["vpn"]["wireguard"]["extra_client_nets"],
                        "dev",
                        self.interface,
                    ]
                )
            check_output(
                (
                    "/usr/bin/wg",
                    "set",
                    self.interface,
                    "peer",
                    peer["vpn"]["wireguard"]["keys"]["public"],
                    "remove",
                ),
                text=True,
            ).strip()
        self.uipt.remove_matching_rules(peer)
        if table == "hypervisors":
            # Resolve the ofport BEFORE del-port so del-flows uses the numeric id
            # that matches how the rules were installed in up_peer().
            try:
                ofport = check_output(
                    ("ovs-vsctl", "get", "interface", peer["id"], "ofport"),
                    text=True,
                ).strip()
            except subprocess.CalledProcessError as exc:
                log.warning(
                    f"Could not resolve ofport for {peer['id']}: {exc}; "
                    "skipping del-flows"
                )
                ofport = None

            if ofport and ofport not in ("", "[]", "-1"):
                result = subprocess.run(
                    ["ovs-ofctl", "del-flows", "ovsbr0", f"in_port={ofport}"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    log.warning(
                        f"del-flows for port {peer['id']} (ofport={ofport}) failed: "
                        f"{result.stderr.strip()}"
                    )

            # --if-exists guards against a partially-reconciled state where the
            # port is already gone (e.g. ovs_setup.sh stale-cleanup ran since
            # the last add). Without it CalledProcessError crashes the
            # changefeed handler and leaves subsequent ADD events unhandled.
            log.info(
                check_output(
                    ("ovs-vsctl", "--if-exists", "del-port", peer["id"]),
                    text=True,
                ).strip()
            )
        # if self.table=='users':
        #    self.uipt.del_user(peer.id,peer.vpn['wireguard']['Address'])

    def gen_client_ip(self):
        next_ip = str(
            next(
                host
                for host in self.server_net.hosts()
                if str(host) not in self.clients_reserved_ips
            )
        )
        self.clients_reserved_ips.add(next_ip)

        # if self.table == 'hypervisors':
        #    next_ip=next_ip+','+os.environ['WG_HYPER_GUESTNET']
        return next_ip

    def gen_peer_config(self, peer):
        peer = self._to_dict(peer)
        # allowed_ips=','.join(peer.vpn['wireguard']['AllowedIPs'])
        return (
            "[peer]\nPublicKey="
            + peer["vpn"]["wireguard"]["keys"]["public"]
            + "\nAllowedIPs="
            + peer["vpn"]["wireguard"]["Address"]
            + "\n\n"
        )

    def set_iptables(self, peer):
        # A null vpn subtree is a real state for a user row, and raising here is
        # swallowed by the change handler, skipping the rest of the change.
        peer = self._to_dict(peer)
        iptables = (peer.get("vpn") or {}).get("iptables")

    def server_config(self, mtu, postup):
        return """[Interface]
Address = %s/%s
SaveConfig = false
PrivateKey = %s
ListenPort = %s
MTU = %s
PostUp = %s

""" % (
            self.server_ip,
            self.server_mask,
            self.keys.skeys["private"],
            self.server_port,
            mtu,
            postup,
        )

    # WireGuard introduces the concepts of Endpoints, Peers and AllowedIPs.
    # A peer is a remote host and is identified by its public key.
    # Each peer has a list of AllowedIPs.
    # From the server’s point of view, the AllowedIPs are IPs that a peer
    # is allowed to use as source IP addresses. For the client, they work
    # as a sort of routing table, determining which peer a packet should
    # be encrypted for. If a peer sends a packet with a source IP that is
    # not in the list of AllowedIPs on the server, then the packet will be
    # simply dropped on the server’s side, for example. An endpoint is a
    # pair of IP address (or hostname) and port of a peer. It is automatically
    # updated to the most recent source IP address and port of correctly
    # authenticated packets from the peer.
    # This means that a peer that is for example jumping between mobile
    # networks (and whose external IP address changes) will still be able
    # to receive incoming traffic because its endpoint will be updated
    # whenever he sends an authenticated message to the server.
    # This is possible because the peer is identified by its public key.

    #    def set_routing(self,hypervisor):
    #        nparent = ipaddress.ip_network(self.allowed_client_nets, strict=False)
    #        dhcpsubnets=list(nparent.subnets(new_prefix=23))
    #        if hypervisor=0:
    #            route='ip r a '+str(dhcpsubnets[-1])+' via '+str(dhcpsubnets[-1].hosts()[3])
    #        else:
    #        [hypervisor]
    #        [IPv4Network('192.168.128.0/23'), IPv4Network('192.168.130.0/23'), IPv4Network('192.168.132.0/23'), IPv4Network('192.168.134.0/23'), IPv4Network('192.168.136.0/23'), IPv4Network('192.168.138.0/23'), IPv4Network('192.168.140.0/23'), IPv4Network('192.168.142.0/23')]

    # ------------------------------------------------------------------ #
    # Applied-desktop index
    #
    # The rules and the OVS flow are installed from an UPDATE event carrying
    # viewer.guest_ip, and reaped from a later event that has to name the same
    # ip. The changefeed squashes changes to a document inside 0.5 s, so a
    # domain deleted right after its guest ip was written arrives with an
    # old_val from before that write: no viewer, no ip, nothing to reap by.
    # The service knows what it installed; it should not need the event to
    # tell it.
    # ------------------------------------------------------------------ #

    @property
    def _applied_desktops(self):
        index = self.__dict__.get("_applied_desktops_index")
        if index is None:
            index = {}
            self.__dict__["_applied_desktops_index"] = index
        return index

    def _remember_applied_desktop(self, domain_id, user, guest_ip):
        if domain_id and guest_ip:
            self._applied_desktops[domain_id] = {"user": user, "guest_ip": guest_ip}

    def _forget_applied_desktop(self, domain_id):
        self._applied_desktops.pop(domain_id, None)

    def _resolve_applied_desktop(self, old_val):
        """What to reap for a deleted domain, or ``None`` if it had nothing.

        The event wins when it carries the ip -- it is the freshest view. The
        index is the fallback for a squashed delete.
        """
        guest_ip = (old_val.get("viewer") or {}).get("guest_ip")
        if guest_ip:
            return {"user": old_val.get("user"), "guest_ip": guest_ip}
        remembered = self._applied_desktops.get(old_val.get("id"))
        if remembered is not None:
            log.info(
                "desktop_iptables: domain %s was deleted without a viewer in the "
                "event; reaping %s from the applied-desktop index",
                old_val.get("id"),
                remembered["guest_ip"],
            )
        return remembered

    def desktop_iptables(self, data):
        old_val = data.get("old_val")
        new_val = data.get("new_val")
        if old_val is None:
            # New. Do nothing as will not have ip yet.
            return
        elif new_val is None:
            # Deleted. Reap everything desktop_add installed, not just the flow:
            # a desktop deleted while still started never passes through the
            # "viewer cleared" update below, so this is its only cleanup.
            applied = self._resolve_applied_desktop(old_val)
            if applied is None:
                # Overwhelmingly the ordinary case: the domain never started, or
                # it was stopped first and the "viewer cleared" update already
                # reaped it. Debug, not error -- one line per deleted domain
                # would only teach people to ignore this log.
                log.debug(
                    "desktop_iptables: nothing to reap for deleted domain %s",
                    old_val.get("id"),
                )
                return
            self.uipt.desktop_remove(applied["user"], applied["guest_ip"])
            self._remove_table2_flow(applied["guest_ip"])
            self._forget_applied_desktop(old_val.get("id"))
            return
        else:
            # Updated
            new_viewer = new_val.get("viewer", {})
            old_viewer = old_val.get("viewer", {}) if old_val else {}
            nv_status = new_val.get("status")
            nv_user = new_val.get("user")
            ov_user = old_val.get("user") if old_val else None
            if nv_status == "Started" and "guest_ip" in new_viewer:
                # As the changes filters for guest_ip in viewer we won't have viewer field till guest_ip is set.
                self.uipt.desktop_add(nv_user, new_viewer.get("guest_ip"))
                self._remember_applied_desktop(
                    new_val.get("id"), nv_user, new_viewer.get("guest_ip")
                )
            elif not new_viewer and old_viewer.get("guest_ip"):
                guest_ip = old_viewer.get("guest_ip")
                self.uipt.desktop_remove(ov_user, guest_ip)
                self._remove_table2_flow(guest_ip)
                self._forget_applied_desktop(old_val.get("id"))

    def _remove_table2_flow(self, guest_ip):
        """Remove table 2 source IP pinning flow and ARP entry for a stopped domain."""
        subprocess.run(
            ["ovs-ofctl", "del-flows", "ovsbr0", f"table=2,ip,nw_src={guest_ip}"],
            capture_output=True,
        )
        subprocess.run(
            ["arp", "-d", guest_ip, "dev", "vlan-wg"],
            capture_output=True,
        )

    def set_initial_rules(self):
        with vpn_rethink_conn() as conn:
            started_desktops = (
                r.table("domains")
                .get_all(["Started"], index="status")
                .pluck("id", "user", "vpn", "status", {"viewer": "guest_ip"})
                .run(conn)
            )
        for started_desktop in started_desktops:
            self.desktop_iptables(started_desktop)

    def user_desktop_iptables(self, data):
        # Updated
        if data["status"] == "Started" and "guest_ip" in data.get("viewer", {}):
            # As the changes filters for guest_ip in viewer we won't have viewer field till guest_ip is set.
            self.uipt.desktop_add(data["user"], data["viewer"]["guest_ip"])

    def refresh_remotevpn_allowed(self, entry):
        self.uipt.refresh_remotevpn_allowed(entry)

    def set_user_rules(self, user_id):
        with vpn_rethink_conn() as conn:
            started_desktops = (
                r.table("domains")
                .get_all(["Started", user_id], index="status_user")
                .pluck("id", "user", "vpn", "status", {"viewer": "guest_ip"})
                .run(conn)
            )
        for started_desktop in started_desktops:
            self.user_desktop_iptables(started_desktop)
