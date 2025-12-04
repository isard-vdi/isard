#!/usr/bin/env python3
"""OVS security stats for VLAN 4095 in JSON format - runs every 60s"""

import json
import os
import re
import subprocess
from datetime import datetime

FLOWS_DIR = "/var/run/openvswitch/libvirt-flows"


def run_cmd(cmd):
    """Run command and return stdout"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=5
        )
        return result.stdout
    except Exception:
        return ""


def get_rstp_stats():
    """Get RSTP status"""
    output = run_cmd("ovs-appctl rstp/show ovsbr0 2>/dev/null")
    ports = len(re.findall(r"(Designated|Root|Alternate)", output))
    blocked = len(re.findall(r"(Blocking|Discarding)", output, re.IGNORECASE))
    return {"ports": ports, "blocked": blocked}


def get_arp_ratelimit_stats():
    """Get ARP rate limiting meter stats"""
    output = run_cmd("ovs-ofctl -O OpenFlow13 meter-stats ovsbr0 2>/dev/null")

    arp_in = 0
    arp_dropped = 0

    m = re.search(r"packet_in_count=(\d+)", output)
    if m:
        arp_in = int(m.group(1))

    m = re.search(r"0: packet_count=(\d+)", output)
    if m:
        arp_dropped = int(m.group(1))

    return {"in": arp_in, "dropped": arp_dropped}


def get_blocked_stats():
    """Get VLAN 4095 blocked broadcast/multicast stats"""
    output = run_cmd("ovs-ofctl dump-flows ovsbr0 2>/dev/null")

    bcast = 0
    mcast = 0

    for line in output.splitlines():
        if "priority=205" not in line:
            continue

        m = re.search(r"n_packets=(\d+)", line)
        if not m:
            continue
        pkts = int(m.group(1))

        if "dl_dst=ff:ff:ff:ff:ff:ff" in line:
            bcast += pkts
        elif "dl_dst=01:00:00:00:00:00" in line:
            mcast += pkts

    return bcast, mcast


def get_vm_count():
    """Count VMs with VLAN 4095 flows"""
    try:
        return len(os.listdir(FLOWS_DIR))
    except Exception:
        return 0


def main():
    bcast, mcast = get_blocked_stats()

    stats = {
        "type": "ovs_security_vlan4095",
        "sysid": os.environ.get("HYPER_ID", "unknown"),
        "time": datetime.now().astimezone().isoformat(),
        "vms": get_vm_count(),
        "rstp": get_rstp_stats(),
        "arp_ratelimit": get_arp_ratelimit_stats(),
        "broadcast_blocked": bcast,
        "multicast_blocked": mcast,
    }
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
