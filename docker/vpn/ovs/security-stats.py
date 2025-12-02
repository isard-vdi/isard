#!/usr/bin/env python3
"""OVS security stats for VLAN 4095 (VPN) in JSON format - runs every 60s"""

import json
import subprocess
import re
import os
from datetime import datetime


def run_cmd(cmd):
    """Run command and return stdout"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
        return result.stdout
    except Exception:
        return ""


def get_rstp_stats():
    """Get RSTP status"""
    output = run_cmd("ovs-appctl rstp/show ovsbr0 2>/dev/null")
    ports = len(re.findall(r"(Designated|Root|Alternate)", output))
    blocked = len(re.findall(r"(Blocking|Discarding)", output, re.IGNORECASE))
    return {"ports": ports, "blocked": blocked}


def get_hypervisor_count():
    """Count connected hypervisors (OVS ports excluding infrastructure)"""
    output = run_cmd("ovs-vsctl list-ports ovsbr0 2>/dev/null")
    infra_ports = {"vlan-wg", "bastion", "samba", "guacamole"}
    count = 0
    for port in output.strip().splitlines():
        if port and port not in infra_ports:
            count += 1
    return count


def get_vlan4095_packets():
    """Get total VLAN 4095 traffic packets"""
    output = run_cmd("ovs-ofctl dump-flows ovsbr0 2>/dev/null")
    total = 0
    for line in output.splitlines():
        if "dl_vlan=4095" not in line:
            continue
        m = re.search(r"n_packets=(\d+)", line)
        if m:
            total += int(m.group(1))
    return total


def get_dhcp_leases():
    """Count DHCP leases"""
    lease_file = "/var/lib/misc/vlan-wg.leases"
    try:
        if os.path.isfile(lease_file):
            with open(lease_file) as f:
                return len(f.readlines())
    except Exception:
        pass
    return 0


def main():
    stats = {
        "type": "ovs_security_vlan4095",
        "sysid": "isard-vpn",
        "time": datetime.now().astimezone().isoformat(),
        "hypervisors": get_hypervisor_count(),
        "rstp": get_rstp_stats(),
        "vlan4095_packets": get_vlan4095_packets(),
        "dhcp_leases": get_dhcp_leases(),
    }
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
