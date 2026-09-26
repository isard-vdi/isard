# SPDX-License-Identifier: AGPL-3.0-or-later
"""Report the dhcp hook's leases to the API from one warm process, newest and new first."""
import logging as log
import os
import threading
import time

QUEUE = os.environ.get("DHCP_REPORTS_DIR", "/run/isard-dhcp-reports")
LEASES = "/var/lib/misc/vlan-wg.leases"
WG_ADDR = "/api/v4/admin/item/hypervisor/vm/wg_addr"
RETRY_SECONDS = 2


def parse(name):
    """``<prio>.<stamp>.<pid>.<action>.<mac with dashes>.<ip>`` or None."""
    if name.startswith("."):
        return None
    parts = name.split(".", 5)
    if len(parts) != 6 or parts[3] not in ("add", "old"):
        return None
    prio, stamp, _pid, action, mac, ip = parts
    if not (prio.isdigit() and stamp.isdigit()):
        return None
    return {
        "name": name,
        "prio": int(prio),
        "stamp": int(stamp),
        "action": action,
        "mac": mac.replace("-", ":"),
        "ip": ip,
    }


def lease_expiries(path=LEASES):
    expiries = {}
    try:
        with open(path) as leases:
            for line in leases:
                fields = line.split()
                if len(fields) >= 3 and fields[0].isdigit():
                    expiries[fields[1].lower()] = int(fields[0])
    except OSError:
        pass
    return expiries


def plan(names, expiries):
    """The latest event of each mac, new leases first and then the newest lease."""
    latest = {}
    superseded = {}
    for event in filter(None, map(parse, names)):
        mac = event["mac"]
        superseded.setdefault(mac, []).append(event["name"])
        if mac not in latest or event["stamp"] > latest[mac]["stamp"]:
            latest[mac] = event
    ordered = sorted(
        latest.values(),
        key=lambda e: (e["prio"], -expiries.get(e["mac"].lower(), 0), e["stamp"]),
    )
    for event in ordered:
        event["files"] = [
            n for n in superseded[event["mac"]] if parse(n)["stamp"] <= event["stamp"]
        ]
    return ordered


def post_wg_address(mac, ip):
    from isardvdi_apiv4_client_auth import build_client

    with build_client("isard-vpn", role="hypervisor") as client:
        return (
            client.get_httpx_client()
            .post(WG_ADDR, json={"mac": mac, "ip": ip})
            .status_code
        )


def step(queue=QUEUE, leases=LEASES, post=post_wg_address):
    """Report one lease; False when there was nothing to report."""
    try:
        names = os.listdir(queue)
    except FileNotFoundError:
        return False
    events = plan(names, lease_expiries(leases))
    if not events:
        return False
    event = events[0]
    try:
        status = post(event["mac"], event["ip"])
    except Exception as error:
        log.warning("dhcp report %s %s: %s", event["mac"], event["ip"], error)
        time.sleep(RETRY_SECONDS)
        return True
    if status >= 500 or status in (401, 403, 429):
        log.warning("dhcp report %s %s: api %s", event["mac"], event["ip"], status)
        time.sleep(RETRY_SECONDS)
        return True
    if status >= 300 and status != 404:
        log.warning(
            "dhcp report %s %s dropped: api %s", event["mac"], event["ip"], status
        )
    for name in event["files"]:
        try:
            os.unlink(os.path.join(queue, name))
        except FileNotFoundError:
            pass
    return True


def _run():
    os.makedirs(QUEUE, exist_ok=True)
    while True:
        try:
            if not step():
                time.sleep(0.2)
        except Exception:
            log.exception("dhcp reports")
            time.sleep(RETRY_SECONDS)


def start():
    threading.Thread(target=_run, name="dhcp_reports", daemon=True).start()
