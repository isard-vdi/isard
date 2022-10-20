import os

from rethinkdb import RethinkDB

r = RethinkDB()
import ipaddress
import logging as log
import traceback
from subprocess import check_call, check_output

import iptc
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

REJECT = {"target": {"REJECT": {"reject-with": "icmp-host-prohibited"}}}


class UserIpTools(object):
    def __init__(self):
        self.flush_chains()
        self.set_default_policy()
        self.init_domains_started()

    def init_domains_started(self):
        domains_started = (
            r.table("domains")
            .get_all("Started", index="status")
            .pluck("id", "user", "vpn", "status", {"viewer": "guest_ip"})
            .run()
        )
        for ds in domains_started:
            if ds.get("viewer") and "guest_ip" in ds["viewer"].keys():
                self.desktop_add(ds["user"], ds["viewer"]["guest_ip"])

    def desktop_add(self, user_id, desktop_ip):
        try:
            user = r.table("users").get(user_id).run()
            user_addr = user["vpn"]["wireguard"]["Address"]
        except Exception as e:
            print("EXCEPTION READING USERS: " + str(e))
            return

        check_output(
            (
                "/sbin/iptables",
                "-A",
                "FORWARD",
                "-s",
                user_addr,
                "-d",
                desktop_ip,
                "-j",
                "ACCEPT",
            ),
            text=True,
        ).strip()
        check_output(
            (
                "/sbin/iptables",
                "-A",
                "FORWARD",
                "-d",
                user_addr,
                "-s",
                desktop_ip,
                "-j",
                "ACCEPT",
            ),
            text=True,
        ).strip()
        self.apply_remote_vpn(user, desktop_ip)
        return

    def desktop_remove(self, user_id, desktop_ip):
        try:
            user = r.table("users").get(user_id).run()
            user_addr = user["vpn"]["wireguard"]["Address"]
        except Exception as e:
            print("EXCEPTION READING USERS: " + e)
            return

        try:
            check_output(
                (
                    "/sbin/iptables",
                    "-D",
                    "FORWARD",
                    "-s",
                    user_addr,
                    "-d",
                    desktop_ip,
                    "-j",
                    "ACCEPT",
                ),
                text=True,
            ).strip()
        except:
            log.debug(
                "REMOVE DESKTOP FROM USER TO DESKTOP: Desktop ip "
                + str(desktop_ip)
                + " for client addr "
                + str(user_addr)
                + " not found in iptables."
            )
        try:
            check_output(
                (
                    "/sbin/iptables",
                    "-D",
                    "FORWARD",
                    "-d",
                    user_addr,
                    "-s",
                    desktop_ip,
                    "-j",
                    "ACCEPT",
                ),
                text=True,
            ).strip()
        except:
            log.debug(
                "REMOVE DESKTOP FROM DESKTOP TO USER: Desktop ip "
                + str(desktop_ip)
                + " for client addr "
                + str(user_addr)
                + " not found in iptables."
            )
        self.remove_remote_vpn(user, desktop_ip)
        return

    def add_rule(self, rule, table=iptc.Table.FILTER, chain="FORWARD"):
        table = iptc.Table(table)
        chain = iptc.Chain(table, chain)
        rule = iptc.easy.encode_iptc_rule(rule)
        chain.insert_rule(rule)

    def set_default_policy(self):
        check_output(("/sbin/iptables", "-P", "FORWARD", "DROP"), text=True).strip()

    def flush_chains(self):
        check_output(("/sbin/iptables", "-F", "FORWARD"), text=True).strip()

    def wireguard_default_postup(self):
        str = "iptables -I FORWARD -i wg0 -o wg0 -j REJECT --reject-with icmp-host-prohibited"

    ## Remote vpn host (for external server access to desktops)
    def apply_remote_vpn(self, user, desktop_ip):
        for extra_alloweds in self.get_extra_alloweds(user):
            remotevpn_addr = extra_alloweds["vpn"]["wireguard"]["Address"]

            check_output(
                (
                    "/sbin/iptables",
                    "-A",
                    "FORWARD",
                    "-s",
                    desktop_ip,
                    "-d",
                    remotevpn_addr,
                    "-j",
                    "ACCEPT",
                )
            )
            check_output(
                (
                    "/sbin/iptables",
                    "-A",
                    "FORWARD",
                    "-d",
                    desktop_ip,
                    "-s",
                    remotevpn_addr,
                    "-j",
                    "ACCEPT",
                )
            )

            if extra_alloweds["vpn"]["wireguard"]["extra_client_nets"]:
                for extra_addr in extra_alloweds["vpn"]["wireguard"][
                    "extra_client_nets"
                ].split(","):
                    check_output(
                        (
                            "/sbin/iptables",
                            "-A",
                            "FORWARD",
                            "-s",
                            desktop_ip,
                            "-d",
                            extra_addr,
                            "-j",
                            "ACCEPT",
                        )
                    )
                    check_output(
                        (
                            "/sbin/iptables",
                            "-A",
                            "FORWARD",
                            "-d",
                            desktop_ip,
                            "-s",
                            extra_addr,
                            "-j",
                            "ACCEPT",
                        )
                    )

    def remove_remote_vpn(self, user, desktop_ip):
        for extra_alloweds in self.get_extra_alloweds(user):
            remotevpn_addr = extra_alloweds["vpn"]["wireguard"]["Address"]
            try:
                check_output(
                    (
                        "/sbin/iptables",
                        "-D",
                        "FORWARD",
                        "-s",
                        desktop_ip,
                        "-d",
                        remotevpn_addr,
                        "-j",
                        "ACCEPT",
                    )
                )
                check_output(
                    (
                        "/sbin/iptables",
                        "-D",
                        "FORWARD",
                        "-d",
                        desktop_ip,
                        "-s",
                        remotevpn_addr,
                        "-j",
                        "ACCEPT",
                    )
                )
            except:
                pass
                # It does not exist
            if extra_alloweds["vpn"]["wireguard"]["extra_client_nets"]:
                for extra_addr in extra_alloweds["vpn"]["wireguard"][
                    "extra_client_nets"
                ].split(","):
                    try:
                        check_output(
                            (
                                "/sbin/iptables",
                                "-D",
                                "FORWARD",
                                "-s",
                                desktop_ip,
                                "-d",
                                extra_addr,
                                "-j",
                                "ACCEPT",
                            )
                        )
                        check_output(
                            (
                                "/sbin/iptables",
                                "-D",
                                "FORWARD",
                                "-d",
                                desktop_ip,
                                "-s",
                                extra_addr,
                                "-j",
                                "ACCEPT",
                            )
                        )
                    except:
                        pass

    def get_extra_alloweds(self, user, table="remotevpn"):
        data = r.table(table).run()
        allowed_data = []
        for d in data:
            # False doesn't check, [] means all allowed
            # Role is the master and user the least. If allowed in roles,
            #   won't check categories, groups, users
            allowed = d["allowed"]
            if d["allowed"]["roles"] != False:
                if not d["allowed"]["roles"]:  # Len != 0
                    allowed_data.append(d)
                    continue
                if user["role"] in d["allowed"]["roles"]:
                    allowed_data.append(d)
                    continue
            if d["allowed"]["categories"] != False:
                if not d["allowed"]["categories"]:
                    allowed_data.append(d)
                    continue
                if user["category"] in d["allowed"]["categories"]:
                    allowed_data.append(d)
                    continue
            if d["allowed"]["groups"] != False:
                if not d["allowed"]["groups"]:
                    allowed_data.append(d)
                    continue
                if user["group"] in d["allowed"]["groups"]:
                    allowed_data.append(d)
                    continue
            if d["allowed"]["users"] != False:
                if not d["allowed"]["users"]:
                    allowed_data.append(d)
                    continue
                if user["id"] in d["allowed"]["users"]:
                    allowed_data.append(d)
        return allowed_data

    def remove_matching_rules(self, peer):
        try:
            if peer["vpn"]["wireguard"]["extra_client_nets"]:
                ips = peer["vpn"]["wireguard"]["extra_client_nets"].split(",") + [
                    peer["vpn"]["wireguard"]["Address"]
                ]
            else:
                ips = [peer["vpn"]["wireguard"]["Address"]]
            rules = iptc.easy.dump_table("filter")["FORWARD"]
            for rule in rules:
                for ip in ips:
                    if (
                        rule["dst"].split("/")[0] in ip
                        or rule["src"].split("/")[0] in ips
                    ):
                        try:
                            check_output(
                                (
                                    "/sbin/iptables",
                                    "-D",
                                    "FORWARD",
                                    "-s",
                                    rule["src"],
                                    "-d",
                                    rule["dst"],
                                    "-j",
                                    "ACCEPT",
                                )
                            )
                            check_output(
                                (
                                    "/sbin/iptables",
                                    "-D",
                                    "FORWARD",
                                    "-s",
                                    rule["dst"],
                                    "-d",
                                    rule["src"],
                                    "-j",
                                    "ACCEPT",
                                )
                            )
                        except:
                            pass
                            # It doesn't exist
        except Exception as e:
            log.error("Removing matched rule except: \n" + traceback.format_exc())
