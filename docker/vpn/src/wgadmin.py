import ipaddress
import os
import socket
import subprocess
import threading
import time
import traceback
from subprocess import check_output

from rethinkdb import RethinkDB

r = RethinkDB()
import logging as log

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
log.basicConfig(
    level=LOG_LEVEL_NUM, format="%(asctime)s - %(levelname)-8s - %(message)s"
)

from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from isardvdi_common.redis_stream import RedisStreamConsumer
from rethinkdb.errors import ReqlDriverError, ReqlOpFailedError, ReqlTimeoutError
from wg_monitor import start_monitoring_vpn_status
from wgtools import Wg

start_monitoring_vpn_status()


def dbConnect():
    r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=os.environ.get("RETHINKDB_PORT", "28015"),
        db=os.environ.get("RETHINKDB_DB", "isard"),
    ).repl()


def _process_vpn_change(change, wg_users, wg_hypers):
    try:
        new_val = change.new_val.model_dump() if change.new_val is not None else None
        old_val = change.old_val.model_dump() if change.old_val is not None else None

        if new_val is None:
            ### Was deleted
            log.info(
                f"Removed {old_val['table']} item {old_val['id']}, removing wg client connection..."
            )
            if old_val["table"] in ["users", "remotevpn"]:
                wg_users.down_peer(old_val)
            elif old_val["table"] == "hypervisors":
                if wg_hypers is not None:
                    wg_hypers.down_peer(old_val)
                else:
                    hyper_id = old_val["id"]
                    subprocess.run(
                        ["ovs-ofctl", "del-flows", "ovsbr0", f"in_port={hyper_id}"],
                        capture_output=True,
                    )
                    subprocess.run(
                        ["ovs-vsctl", "--if-exists", "del-port", hyper_id],
                        capture_output=True,
                    )
            elif old_val["table"] == "domains":
                wg_users.desktop_iptables({"old_val": old_val, "new_val": new_val})

        elif old_val is None:
            ### New
            log.info(
                f"Added {new_val['table']} item {new_val['id']}, generating new vpn config..."
            )
            if new_val["table"] in ["users", "remotevpn"]:
                wg_users.add_peer(new_val, table=new_val["table"])
            elif new_val["table"] == "hypervisors":
                vpn_tunneling_mode = (new_val.get("vpn") or {}).get(
                    "tunneling_mode", "wireguard+geneve"
                )
                if vpn_tunneling_mode == "geneve":
                    hostname = new_val.get("hostname")
                    if hostname:
                        try:
                            resolved_ip = socket.gethostbyname(hostname)
                        except socket.gaierror:
                            log.error(f"Cannot resolve {hostname}")
                            return
                        hyper_id = new_val["id"]
                        geneve_port = os.environ.get("WG_HYPERS_PORT", "4443")
                        subprocess.run(
                            [
                                "ovs-vsctl",
                                "add-port",
                                "ovsbr0",
                                hyper_id,
                                "--",
                                "set",
                                "interface",
                                hyper_id,
                                "type=geneve",
                                f"options:remote_ip={resolved_ip}",
                                f"options:dst_port={geneve_port}",
                            ]
                        )
                        subprocess.run(
                            [
                                "ovs-vsctl",
                                "set",
                                "Interface",
                                hyper_id,
                                "bfd:enable=true",
                                "bfd:min_tx=1000",
                                "bfd:min_rx=1000",
                            ]
                        )
                        port = check_output(
                            ("ovs-vsctl", "get", "interface", hyper_id, "ofport"),
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
                        log.info(f"Added geneve-only hypervisor {hyper_id}")
                elif wg_hypers is not None:
                    wg_hypers.add_peer(new_val)
                else:
                    log.error(
                        "Cannot add WireGuard peer - WireGuard disabled (GENEVE_ONLY_INFRA=true)"
                    )
            elif new_val["table"] == "domains":
                wg_users.desktop_iptables({"old_val": old_val, "new_val": new_val})

        else:
            ### Update
            if old_val["table"] in ["users", "remotevpn", "hypervisors"]:
                if "vpn" not in old_val:
                    return
                old_vpn = old_val.get("vpn")
                new_vpn = new_val.get("vpn")
                if old_val["table"] == "users":
                    if (new_vpn or {}).get("wireguard", {}).get("keys") is False:
                        log.info(
                            f"Reset {new_val['table']} item {new_val['id']}, generating new vpn config..."
                        )
                        if old_vpn:
                            wg_users.down_peer(old_val)
                        wg_users.add_peer(new_val, table=new_val["table"])
                        wg_users.set_user_rules(new_val["id"])

                    old_active = old_val.get("active")
                    new_active = new_val.get("active")
                    if old_active is True and new_active is False:
                        log.info(
                            f"Disabled {old_val['table']} item {old_val['id']}, removing wg client connection..."
                        )
                        wg_users.down_peer(old_val)
                    elif old_active is False and new_active is True:
                        log.info(
                            f"Enabled {new_val['table']} item {new_val['id']}, adding wg client connection..."
                        )
                        wg_users.up_peer(new_val)

                if (old_vpn or {}).get("iptables") != (new_vpn or {}).get("iptables"):
                    log.info("Modified iptables")
                    if old_val["table"] in ["users", "remotevpn"]:
                        wg_users.set_iptables(new_val)

            elif old_val["table"] == "domains":
                wg_users.desktop_iptables({"old_val": old_val, "new_val": new_val})

    except Exception:
        log.error("VPN change processing error: \n" + traceback.format_exc())


log.info("Starting isard-vpn...")

# Check infrastructure mode - when GENEVE_ONLY_INFRA=true, skip WireGuard for hypers
geneve_only_infra = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"

while True:
    try:
        # App was restarted or db was lost. Just sync peers before get into changes.
        log.info("Connecting to database...")
        dbConnect()

        # WireGuard for hypervisors - only when not in geneve-only infrastructure mode
        hypers_net = ipaddress.ip_network(os.environ["WG_HYPERS_NET"], strict=False)
        if geneve_only_infra:
            log.info("GENEVE_ONLY_INFRA=true - skipping WireGuard for hypervisors")
            wg_hypers = None
        else:
            wg_hypers = Wg(
                interface="hypers",
                clients_net=os.environ["WG_HYPERS_NET"],
                table="hypervisors",
                server_port=os.environ["WG_HYPERS_PORT"],
                allowed_client_nets=str(hypers_net[1]) + "/32",
                reset_client_certs=False,
            )

        # Initialize OVS ports for geneve-only hypervisors
        if geneve_only_infra:
            geneve_hypers = list(
                r.table("hypervisors")
                .pluck("id", "vpn", "hostname")
                .filter(
                    lambda h: h["vpn"]
                    .get_field("tunneling_mode")
                    .default(None)
                    .eq("geneve")
                )
                .run()
            )
            for hyper in geneve_hypers:
                hostname = hyper.get("hostname")
                hyper_id = hyper.get("id")
                if not hostname or not hyper_id:
                    continue
                try:
                    resolved_ip = socket.gethostbyname(hostname)
                except socket.gaierror:
                    log.error(f"Cannot resolve hostname {hostname} for {hyper_id}")
                    continue
                geneve_port = os.environ.get("WG_HYPERS_PORT", "4443")
                if (
                    hyper_id
                    not in check_output(("ovs-vsctl", "show"), text=True).strip()
                ):
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "add-port",
                            "ovsbr0",
                            hyper_id,
                            "--",
                            "set",
                            "interface",
                            hyper_id,
                            "type=geneve",
                            f"options:remote_ip={resolved_ip}",
                            f"options:dst_port={geneve_port}",
                        ]
                    )
                    subprocess.run(
                        [
                            "ovs-vsctl",
                            "set",
                            "Interface",
                            hyper_id,
                            "bfd:enable=true",
                            "bfd:min_tx=1000",
                            "bfd:min_rx=1000",
                        ]
                    )
                    port = check_output(
                        ("ovs-vsctl", "get", "interface", hyper_id, "ofport"), text=True
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
                    log.info(
                        f"Initialized geneve-only hypervisor {hyper_id} (port {port})"
                    )
            log.info(f"Initialized {len(geneve_hypers)} geneve-only hypervisors")

        wg_users = Wg(
            interface="users",
            clients_net=os.environ["WG_USERS_NET"],
            table="users",
            server_port=os.environ["WG_USERS_PORT"],
            allowed_client_nets=os.environ["WG_GUESTS_NETS"],
            reset_client_certs=False,
        )

        log.info(
            "Config regenerated from database...\nStarting to monitor changes via Redis Streams..."
        )

        consumer = RedisStreamConsumer(
            streams=[
                "stream:users",
                "stream:hypervisors",
                "stream:remotevpn",
                "stream:domains",
            ],
            group="vpn-wireguard",
        )

        def handle_change(msg):
            table = msg.get("table")
            subscriber = TABLE_TO_SUBSCRIBER.get(table)
            if subscriber is None:
                return
            envelope = subscriber.parse_dict(msg)
            _process_vpn_change(envelope.change, wg_users, wg_hypers)

        consumer.run(handle_change)

    except Exception as e:
        log.error("START: internal error: \n" + traceback.format_exc())
        time.sleep(2)
