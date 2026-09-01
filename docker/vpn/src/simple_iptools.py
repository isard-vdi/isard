import os

from rethinkdb import RethinkDB

r = RethinkDB()
import ipaddress
import logging as log
import shlex
import traceback
from subprocess import DEVNULL, check_output

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


IPTABLES = "/sbin/iptables"


def _append_forward(rule):
    """Append a FORWARD rule unless the chain already carries it.

    Any write to a running desktop's row replays the add, so an unconditional
    append grows one copy per event and a single delete cannot undo them.
    """
    try:
        check_output((IPTABLES, "-C", "FORWARD", *rule), stderr=DEVNULL)
        return
    except Exception:
        pass
    check_output((IPTABLES, "-A", "FORWARD", *rule), text=True)


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
            # The value, not the key: a desktop between Started and its address
            # arriving carries an explicit null, which used to reach desktop_add
            # and take the whole service down on startup.
            guest_ip = (ds.get("viewer") or {}).get("guest_ip")
            if guest_ip:
                self.desktop_add(ds["user"], guest_ip)

    def desktop_add(self, user_id, desktop_ip):
        if not desktop_ip:
            return
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

        _append_forward(("-s", user_addr, "-d", desktop_ip, "-j", "ACCEPT"))
        _append_forward(("-d", user_addr, "-s", desktop_ip, "-j", "ACCEPT"))
        self.apply_remote_vpn(user, desktop_ip)
        return

    def desktop_remove(self, user_id, desktop_ip):
        try:
            with vpn_rethink_conn() as conn:
                user = r.table("users").get(user_id).run(conn)
            user_addr = user["vpn"]["wireguard"]["Address"]
        except Exception as e:
            # str(e): concatenating the exception itself raised a TypeError
            # from inside the handler, replacing the real cause with its own.
            log.error("EXCEPTION READING USERS: " + str(e))
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
        self._add_remotevpn_rules(self.get_extra_alloweds(user), desktop_ip)

    def remove_remote_vpn(self, user, desktop_ip):
        # Every entry, not only the ones the user may still reach: a permission
        # revoked while the desktop ran leaves a rule nothing else ever removes.
        self._remove_remotevpn_rules(self.get_all_remotevpn(), desktop_ip)

    @staticmethod
    def _remotevpn_addrs(entry):
        """Every address a remotevpn entry reaches: its own plus extra_client_nets."""
        wireguard = ((entry or {}).get("vpn") or {}).get("wireguard") or {}
        address = wireguard.get("Address")
        if not address:
            return []
        addrs = [address]
        extra = wireguard.get("extra_client_nets")
        if extra:
            addrs += extra.split(",")
        return addrs

    def _add_remotevpn_rules(self, entries, desktop_ip):
        for entry in entries:
            for addr in self._remotevpn_addrs(entry):
                _append_forward(("-s", desktop_ip, "-d", addr, "-j", "ACCEPT"))
                _append_forward(("-d", desktop_ip, "-s", addr, "-j", "ACCEPT"))

    def _remove_remotevpn_rules(self, entries, desktop_ip):
        for entry in entries:
            for addr in self._remotevpn_addrs(entry):
                for direction in (
                    ("-s", desktop_ip, "-d", addr),
                    ("-d", desktop_ip, "-s", addr),
                ):
                    try:
                        check_output(
                            ("/sbin/iptables", "-D", "FORWARD")
                            + direction
                            + ("-j", "ACCEPT")
                        )
                    except Exception:
                        pass

    @staticmethod
    def is_allowed_remotevpn(user, entry):
        """Whether ``user`` may reach one remotevpn entry.

        Per level, False means "do not check this one" and an empty list means
        "everybody". Roles are checked first and users last; a level that does
        not match falls through to the next.

        A level that is absent, null or not a list is NOT "everybody": only a
        real empty list means that. Reading a malformed row as open would hand
        every user an entry that names somebody else, so it is skipped like
        False and the remaining levels decide.
        """
        allowed = entry.get("allowed")
        if not isinstance(allowed, dict):
            return False
        levels = (
            ("roles", [user.get("role")]),
            ("categories", [user.get("category")]),
            ("groups", [user.get("group")] + list(user.get("secondary_groups") or [])),
            ("users", [user.get("id")]),
        )
        for level, held in levels:
            configured = allowed.get(level)
            if not isinstance(configured, (list, tuple)):
                continue
            if not configured:
                return True
            if any(value in configured for value in held if value is not None):
                return True
        return False

    def get_all_remotevpn(self, table="remotevpn"):
        with vpn_rethink_conn() as conn:
            return list(r.table(table).run(conn))

    def get_extra_alloweds(self, user, table="remotevpn"):
        return [
            entry
            for entry in self.get_all_remotevpn(table)
            if self.is_allowed_remotevpn(user, entry)
        ]

    def refresh_remotevpn_allowed(self, entry):
        """Re-apply one remotevpn entry's rules over every running desktop.

        Nothing reacted to ``allowed`` changing, so a withdrawn permission kept
        working until the desktop stopped. Removing before adding makes it
        idempotent whichever way the permission moved.

        Each desktop is isolated: this runs on the revocation path, and letting
        one iptables failure abort the pass would leave every desktop after it
        still reaching a host its user may no longer use -- the exact leak this
        is here to close. A failure is counted and named instead, loudly,
        because the caller swallows what reaches it.
        """
        entry_id = (entry or {}).get("id")
        with vpn_rethink_conn() as conn:
            desktops = list(
                r.table("domains")
                .get_all("Started", index="status")
                .pluck("id", "user", {"viewer": "guest_ip"})
                .run(conn)
            )
            users = {}
            for desktop in desktops:
                user_id = desktop.get("user")
                if not user_id or user_id in users:
                    continue
                try:
                    users[user_id] = r.table("users").get(user_id).run(conn)
                except Exception:
                    users[user_id] = None
                    log.error(
                        "remotevpn %s: cannot read user %s, its desktops are skipped",
                        entry_id,
                        user_id,
                        exc_info=True,
                    )

        failed = []
        for desktop in desktops:
            guest_ip = (desktop.get("viewer") or {}).get("guest_ip")
            user = users.get(desktop.get("user"))
            if not guest_ip or not user:
                continue
            try:
                self._remove_remotevpn_rules([entry], guest_ip)
                if self.is_allowed_remotevpn(user, entry):
                    self._add_remotevpn_rules([entry], guest_ip)
            except Exception:
                failed.append(desktop.get("id"))
                log.error(
                    "remotevpn %s: desktop %s (%s) not refreshed",
                    entry_id,
                    desktop.get("id"),
                    guest_ip,
                    exc_info=True,
                )

        if failed:
            log.error(
                "remotevpn %s: %s of %s desktops left unrefreshed: %s",
                entry_id,
                len(failed),
                len(desktops),
                ", ".join(str(d) for d in failed),
            )
        return failed

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
