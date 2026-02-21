import ipaddress
import os
import socket
import subprocess
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

        print(
            "Config regenerated from database...\nStarting to monitor users changes..."
        )
        # for user in r.table('users').pluck('id','vpn').changes(include_initial=False).run():

        for data in (
            r.table("users")
            .pluck("id", "vpn", "active")
            .without({"vpn": {"wireguard": "connected"}})
            .merge({"table": "users"})
            .changes(include_initial=False)
            .union(
                r.table("hypervisors")
                .pluck("id", "vpn", "hostname")
                .without({"vpn": {"wireguard": "connected"}})
                .merge({"table": "hypers"})
                .changes(include_initial=False)
            )
            .union(
                r.table("remotevpn")
                .pluck("id", "vpn", "nets")
                .without({"vpn": {"wireguard": "connected"}})
                .merge({"table": "remotevpn"})
                .changes(include_initial=False)
            )
            .union(
                r.table("domains")
                .pluck("id", "user", "vpn", "status", {"viewer": "guest_ip"})
                .merge({"table": "domains"})
                .changes(include_initial=False)
            )
            .run()
        ):

            try:
                if data["new_val"] == None:
                    ### Was deleted
                    log.info(
                        f'Removed {data["old_val"]["table"]} item {data["old_val"]["id"]}, removing wg client connection...'
                    )
                    if data["old_val"]["table"] in ["users", "remotevpn"]:
                        wg_users.down_peer(data["old_val"])
                    elif data["old_val"]["table"] == "hypers":
                        if wg_hypers is not None:
                            wg_hypers.down_peer(data["old_val"])
                        else:
                            # Geneve-only: remove OVS port directly
                            hyper_id = data["old_val"]["id"]
                            subprocess.run(
                                [
                                    "ovs-ofctl",
                                    "del-flows",
                                    "ovsbr0",
                                    f"in_port={hyper_id}",
                                ],
                                capture_output=True,
                            )
                            subprocess.run(
                                ["ovs-vsctl", "--if-exists", "del-port", hyper_id],
                                capture_output=True,
                            )
                    elif data["old_val"]["table"] == "domains":
                        wg_users.desktop_iptables(data)
                elif data["old_val"] is None:
                    ### New
                    log.info(
                        f'Added {data["new_val"]["table"]} item {data["new_val"]["id"]}, generating new vpn config...'
                    )
                    if data["new_val"]["table"] in ["users", "remotevpn"]:
                        wg_users.add_peer(
                            data["new_val"], table=data["new_val"]["table"]
                        )
                    elif data["new_val"]["table"] == "hypers":
                        vpn_tunneling_mode = (
                            data["new_val"]
                            .get("vpn", {})
                            .get("tunneling_mode", "wireguard+geneve")
                        )
                        if vpn_tunneling_mode == "geneve":
                            # Geneve-only: add OVS port directly
                            hostname = data["new_val"].get("hostname")
                            if hostname:
                                try:
                                    resolved_ip = socket.gethostbyname(hostname)
                                except socket.gaierror:
                                    log.error(f"Cannot resolve {hostname}")
                                    continue
                                hyper_id = data["new_val"]["id"]
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
                                    (
                                        "ovs-vsctl",
                                        "get",
                                        "interface",
                                        hyper_id,
                                        "ofport",
                                    ),
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
                            wg_hypers.add_peer(data["new_val"])
                        else:
                            log.error(
                                f"Cannot add WireGuard peer - WireGuard disabled (GENEVE_ONLY_INFRA=true)"
                            )
                    elif data["new_val"]["table"] == "domains":
                        wg_users.desktop_iptables(data)
                else:
                    ### Update
                    if data["old_val"]["table"] in ["users", "remotevpn", "hypers"]:
                        if "vpn" not in data["old_val"]:
                            continue  # Was just added
                        if data["old_val"]["table"] == "users":
                            # User vpn reset. Should generate new keys and update iptables
                            if (
                                data["new_val"]
                                .get("vpn", {})
                                .get("wireguard", {})
                                .get("keys")
                                == False
                            ):
                                log.info(
                                    f'Reset {data["new_val"]["table"]} item {data["new_val"]["id"]}, generating new vpn config...'
                                )
                                if data["old_val"].get("vpn"):
                                    wg_users.down_peer(data["old_val"])
                                # This will overwrite vpn data in database for it's id
                                wg_users.add_peer(
                                    data["new_val"], table=data["new_val"]["table"]
                                )
                                wg_users.set_user_rules(data["new_val"]["id"])

                            ## Enabled/Disabled user
                            if (
                                data["old_val"].get("active") == True
                                and data["new_val"].get("active") == False
                            ):
                                log.info(
                                    f'Disabled {data["old_val"]["table"]} item {data["old_val"]["id"]}, removing wg client connection...'
                                )
                                wg_users.down_peer(data["old_val"])
                            elif (
                                data["old_val"].get("active") == False
                                and data["new_val"].get("active") == True
                            ):
                                log.info(
                                    f'Enabled {data["new_val"]["table"]} item {data["new_val"]["id"]}, adding wg client connection...'
                                )
                                wg_users.up_peer(data["new_val"])

                        if (
                            data["old_val"]["vpn"]["iptables"]
                            != data["new_val"]["vpn"]["iptables"]
                        ):
                            print("Modified iptables")
                            if data["old_val"]["table"] in ["users", "remotevpn"]:
                                wg_users.set_iptables(data["new_val"])
                            else:
                                ## Maybe just avoid rules on hypers table?????
                                ## I THINK THIS IS NOT NEEDED
                                # wg_hypers.set_iptables(data['new_val'])
                                pass
                        else:
                            continue
                            print("Modified wireguard config")
                            # who else could modify the wireguard config??
                            # if data['old_val']['table'] in ['users','remotevpn']:
                            #     wg_users.update_peer(data['new_val'])
                            # else:
                            #     wg_hypers.update_peer(data['new_val'])
                    elif data["old_val"]["table"] == "domains":
                        wg_users.desktop_iptables(data)
            except (ReqlDriverError, ReqlOpFailedError, ReqlTimeoutError):
                raise
            except:
                log.error("internal error: \n" + traceback.format_exc())
                continue
    except (ReqlDriverError, ReqlOpFailedError):
        log.error("START: Rethink db connection missing!")
        time.sleep(0.5)
    except Exception as e:
        log.error("START: internal error: \n" + traceback.format_exc())
        # exit(1)

print("Thread ENDED!!!!!!!")
log.error("Thread ENDED!!!!!!!")
