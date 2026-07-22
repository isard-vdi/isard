import os

from rethinkdb import RethinkDB

r = RethinkDB()
import ipaddress
import logging as log
import shlex
import traceback
from subprocess import check_output

from db import vpn_rethink_conn
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError

IPTABLES = "/sbin/iptables"


def _forward_rule_specs():
    """Token lists for every ``-A FORWARD ...`` rule, from ``iptables -S FORWARD``.

    ``-S`` prints each rule as its append-equivalent command, so swapping the
    leading ``-A`` for ``-D`` reproduces an exact delete. Non-append lines
    (e.g. the ``-P FORWARD DROP`` policy) are skipped.
    """
    out = check_output((IPTABLES, "-S", "FORWARD"), text=True)
    specs = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("-A FORWARD"):
            specs.append(shlex.split(line))
    return specs


def _rule_addr(tokens, flag):
    """Mask-stripped address passed to ``flag`` (``-s``/``-d``), or None."""
    try:
        return tokens[tokens.index(flag) + 1].split("/")[0]
    except (ValueError, IndexError):
        return None


class UserIpTools(object):
    def __init__(self):
        self.flush_chains()
        self.set_default_policy()
        self.init_domains_started()

    def init_domains_started(self):
        with vpn_rethink_conn() as conn:
            domains_started = (
                r.table("domains")
                .get_all("Started", index="status")
                .pluck("id", "user", "vpn", "status", {"viewer": "guest_ip"})
                .run(conn)
            )
        for ds in domains_started:
            if ds.get("viewer") and "guest_ip" in ds["viewer"].keys():
                self.desktop_add(ds["user"], ds["viewer"]["guest_ip"])

    def desktop_add(self, user_id, desktop_ip):
        try:
            with vpn_rethink_conn() as conn:
                user = r.table("users").get(user_id).run(conn)
            user_addr = user["vpn"]["wireguard"]["Address"]
        except Exception as e:
            log.debug("EXCEPTION READING USERS: " + str(e))
            return

        log.debug(
            "Desktop added: [ DESKTOP "
            + desktop_ip
            + " ] <-> [ "
            + user_addr
            + " USER ]"
        )

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
            with vpn_rethink_conn() as conn:
                user = r.table("users").get(user_id).run(conn)
            user_addr = user["vpn"]["wireguard"]["Address"]
        except Exception as e:
            log.error("EXCEPTION READING USERS: " + e)
            return

        log.debug(
            "Desktop remove: [ DESKTOP "
            + desktop_ip
            + " ] <-> [ "
            + user_addr
            + " USER ]"
        )

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

    def set_default_policy(self):
        guests_net = ipaddress.ip_network(
            os.environ.get("WG_GUESTS_NETS", "10.2.0.0/16"), strict=False
        )
        infra_cidr = str(
            ipaddress.ip_network(f"{guests_net.network_address}/28", strict=False)
        )
        check_output(("/sbin/iptables", "-P", "FORWARD", "DROP"), text=True).strip()
        # Block user-to-user traffic (users <-> users on the WireGuard iface)
        check_output(
            (
                "/sbin/iptables",
                "-I",
                "FORWARD",
                "-i",
                "users",
                "-o",
                "users",
                "-j",
                "REJECT",
                "--reject-with",
                "icmp-host-prohibited",
            ),
            text=True,
        ).strip()
        # Block user access to infrastructure services
        check_output(
            (
                "/sbin/iptables",
                "-I",
                "FORWARD",
                "-i",
                "users",
                "-d",
                infra_cidr,
                "-j",
                "REJECT",
                "--reject-with",
                "icmp-host-prohibited",
            ),
            text=True,
        ).strip()

    def flush_chains(self):
        check_output(("/sbin/iptables", "-F", "FORWARD"), text=True).strip()

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
        with vpn_rethink_conn() as conn:
            data = list(r.table(table).run(conn))
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
            wg = ((peer or {}).get("vpn") or {}).get("wireguard") or {}
            address = wg.get("Address")
            if not address:
                # Peer never completed wireguard setup (no Address yet);
                # there's no rule pinned to its IP to remove.
                return
            targets = {address.split("/")[0]}
            extra = wg.get("extra_client_nets")
            if extra:
                targets |= {a.split("/")[0] for a in extra.split(",")}

            for tokens in _forward_rule_specs():
                # Only the per-peer ACCEPT pairs are reaped; the REJECT
                # isolation rules and the DROP policy are never deleted.
                try:
                    target = tokens[tokens.index("-j") + 1]
                except (ValueError, IndexError):
                    continue
                if target != "ACCEPT":
                    continue
                if (
                    _rule_addr(tokens, "-s") in targets
                    or _rule_addr(tokens, "-d") in targets
                ):
                    try:
                        # tokens[2:] is everything after "-A FORWARD".
                        check_output(
                            (IPTABLES, "-D", "FORWARD", *tokens[2:]), text=True
                        )
                    except Exception:
                        # already gone / lost a race
                        pass
        except Exception:
            log.error("Removing matched rule except: \n" + traceback.format_exc())
