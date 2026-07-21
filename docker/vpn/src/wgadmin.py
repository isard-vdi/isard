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

import tunnel_monitor
from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from db import vpn_rethink_conn
from isardvdi_common.redis_stream import RedisStreamConsumer
from rethinkdb.errors import ReqlDriverError, ReqlOpFailedError, ReqlTimeoutError
from wg_monitor import start_monitoring_vpn_status
from wgtools import Wg

start_monitoring_vpn_status()
tunnel_monitor.start()

VM_MAC_MATCH = "52:54:00:00:00:00/ff:ff:ff:00:00:00"


def ensure_geneve_port(hyper_id, hostname):
    """Create the hypervisor's geneve port if missing, then (re)apply its BFD
    session and flows.

    BFD and the flows are applied even when the port already exists: BFD is the
    only liveness signal in geneve-only (tunnel_monitor reads bfd_status:state),
    so a port left without it would report the tunnel down forever, and the
    flows live in ovs-vswitchd rather than the OVS db, so a restart loses them.
    """
    if not hyper_id or not hostname:
        return False
    try:
        resolved_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        log.error(f"Cannot resolve hostname {hostname} for {hyper_id}")
        return False

    geneve_port = os.environ.get("WG_HYPERS_PORT", "4443")
    if hyper_id not in check_output(("ovs-vsctl", "show"), text=True).strip():
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
            "bfd:min_tx=200",
            "bfd:min_rx=200",
        ]
    )
    port = check_output(
        ("ovs-vsctl", "get", "interface", hyper_id, "ofport"), text=True
    ).strip()
    for flow in (
        f"priority=451,arp,in_port={port},dl_vlan=4095,dl_src={VM_MAC_MATCH},actions=NORMAL",
        f"priority=451,udp,in_port={port},dl_vlan=4095,dl_src={VM_MAC_MATCH},tp_src=68,tp_dst=67,actions=NORMAL",
        f"priority=450,ip,in_port={port},dl_vlan=4095,dl_src={VM_MAC_MATCH},actions=resubmit(,2)",
        f"priority=449,in_port={port},dl_vlan=4095,actions=drop",
    ):
        subprocess.run(["ovs-ofctl", "add-flow", "ovsbr0", flow])
    log.info(f"Ensured geneve hypervisor {hyper_id} (port {port})")
    return True


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
                # Gate on GENEVE_ONLY_INFRA too: on a fresh registration the
                # record's vpn.tunneling_mode is not set yet (the api writes it
                # in a separate update after the insert), so it defaults to
                # "wireguard+geneve" and this insert event would wrongly take the
                # WireGuard branch -- leaving the hypervisor's geneve tunnel (and
                # its BFD session) never created until a vpn restart.
                if vpn_tunneling_mode == "geneve" or geneve_only_infra:
                    ensure_geneve_port(new_val["id"], new_val.get("hostname"))
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
            if new_val["table"] == "hypervisors":
                # Under geneve-only the tunnel must exist for every hypervisor,
                # whichever event carries it: a re-registration of an existing
                # record arrives here rather than as an insert, and the api stamps
                # tunneling_mode in a separate update after the insert, so this is
                # the only event that fires once the record is complete. Kept above
                # the "vpn not in old_val" return below, which would otherwise skip
                # precisely the update that first adds vpn.
                #
                # Only on a transition: hypervisors stream stats every few seconds,
                # and re-running the OVS setup per tick would spawn a handful of
                # ovs-vsctl/ovs-ofctl calls per hypervisor forever.
                old_mode = (old_val.get("vpn") or {}).get("tunneling_mode")
                new_mode = (new_val.get("vpn") or {}).get("tunneling_mode")
                if (geneve_only_infra or new_mode == "geneve") and (
                    old_mode != new_mode
                    or old_val.get("hostname") != new_val.get("hostname")
                ):
                    ensure_geneve_port(new_val["id"], new_val.get("hostname"))

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
        # App was restarted or db was lost. The shared pool reconnects
        # transparently via its connection factory; this loop re-runs
        # the peer-sync pass each iteration.
        log.info("Connecting to database...")

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
            with vpn_rethink_conn() as _conn:
                # No tunneling_mode filter: this block already runs only under
                # GENEVE_ONLY_INFRA, where every hypervisor is geneve. Filtering
                # on the stored mode raced the api, which writes it in a separate
                # update after the insert -- a hypervisor still reading
                # "wireguard+geneve" was skipped here, and a re-registration
                # arrives as an update (not an insert), so its geneve port and
                # BFD session were never created and the tunnel read as down
                # forever. tunnel_monitor treats the env the same way.
                geneve_hypers = list(
                    r.table("hypervisors").pluck("id", "vpn", "hostname").run(_conn)
                )
            for hyper in geneve_hypers:
                ensure_geneve_port(hyper.get("id"), hyper.get("hostname"))
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
