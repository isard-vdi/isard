import ipaddress
import os
import time
import traceback

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
while True:
    try:
        # App was restarted or db was lost. Just sync peers before get into changes.
        log.info("Connecting to database...")
        dbConnect()

        wg_hypers = Wg(
            interface="hypers",
            clients_net=os.environ["WG_HYPERS_NET"],
            table="hypervisors",
            server_port=os.environ["WG_HYPERS_PORT"],
            allowed_client_nets="10.1.0.1/32",
            reset_client_certs=False,
        )
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
                .pluck("id", "vpn")
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
                        wg_hypers.down_peer(data["old_val"])
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
                        wg_hypers.add_peer(data["new_val"])
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
