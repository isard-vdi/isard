# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin every live dnsmasq lease on table 2 in one batch, before dnsmasq starts."""
import re
import subprocess
import sys
import tempfile
import time

LEASES = "/var/lib/misc/vlan-wg.leases"
BRIDGE = "ovsbr0"
INTERFACE = "vlan-wg"

_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def _is_ipv4(ip):
    match = _IPV4.match(ip)
    return bool(match) and all(int(octet) <= 255 for octet in match.groups())


def live_leases(text, now):
    """(mac, ip) of every unexpired IPv4 lease, in file order, without repeats."""
    pairs = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 3 or not fields[0].isdigit():
            continue
        expiry, mac, ip = int(fields[0]), fields[1].lower(), fields[2]
        # dnsmasq writes 0 for an infinite lease
        if expiry and expiry <= now:
            continue
        if not _MAC.match(mac) or not _is_ipv4(ip):
            continue
        if (mac, ip) not in pairs:
            pairs.append((mac, ip))
    return pairs


def gateway_mac(run=subprocess.run):
    try:
        out = run(
            ["ip", "-o", "link", "show", INTERFACE], capture_output=True, text=True
        ).stdout
    except OSError:
        return None
    match = re.search(r"link/ether ([0-9a-f:]{17})", out or "")
    return match.group(1) if match else None


def pin_flows(mac, ip, gateway=None):
    """The table 2 flows the dhcp hook writes for one lease."""
    flows = [f"table=2,priority=100,ip,dl_src={mac},nw_src={ip},actions=NORMAL"]
    if gateway:
        flows.append(
            f"table=2,priority=110,ip,dl_src={mac},nw_src={ip},dl_dst={gateway},"
            f"actions=strip_vlan,output:{INTERFACE}"
        )
    return flows


def pin(pairs, gateway=None, run=subprocess.run):
    if not pairs:
        return
    with tempfile.NamedTemporaryFile("w", suffix=".flows") as flows:
        flows.write(
            "".join(
                flow + "\n" for mac, ip in pairs for flow in pin_flows(mac, ip, gateway)
            )
        )
        flows.flush()
        run(["ovs-ofctl", "add-flows", BRIDGE, flows.name], check=True)
    with tempfile.NamedTemporaryFile("w", suffix=".neigh") as neigh:
        neigh.write(
            "".join(
                f"neigh replace {ip} lladdr {mac} dev {INTERFACE} nud permanent\n"
                for mac, ip in pairs
            )
        )
        neigh.flush()
        run(["ip", "-batch", neigh.name], check=True)


def main(argv=None, run=subprocess.run, now=None):
    path = (argv or sys.argv[1:] or [LEASES])[0]
    try:
        with open(path) as leases:
            pairs = live_leases(leases.read(), now or time.time())
        pin(pairs, gateway=gateway_mac(run), run=run)
    except (OSError, subprocess.CalledProcessError) as error:
        # dnsmasq pins every lease again as it walks them, so a failure here
        # only costs the head start; it must not keep the vpn from starting
        print(f"lease pins: skipped, {error}", file=sys.stderr)
        return 0
    print(f"lease pins: {len(pairs)} leases pinned from {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
