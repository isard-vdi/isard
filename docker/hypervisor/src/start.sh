#!/bin/sh -i

export DOMAIN
export HYPER_ID
export VIEWER_BROWSER
export VIEWER_SPICE
export BLACKLIST_IPTABLES
export WHITELIST_IPTABLES

BOOT_TOTAL=9

# Report boot progress to the API. Fire-and-forget AND backgrounded: each call
# cold-starts python and imports the apiv4 client (~1.5 s), so run inline it
# stalls boot ~1.5 s per step across 10 steps; progress is advisory and its
# errors were already ignored, so boot must never block on it.
report_step() {
  python3 -c "
import sys; sys.path.insert(0, '/src/lib')
from progress import report_progress
report_progress($1, $BOOT_TOTAL, '$2', $3)
" >/dev/null 2>&1 &
}

# Graceful hypervisor shutdown. Runs in parallel: API unregister +
# ACPI to all running guests, then drains up to GUEST_SHUTDOWN_TIMEOUT
# (default 15s), hard-destroys leftovers, and wipes all sysfs mdevs.
# See lib/shutdown.py. Container must have matching stop_grace_period
# in docker-compose-parts/hypervisor.yml.
shutdown_hyper()
{
  python3 /src/lib/shutdown.py || true
  exit 0
}
trap shutdown_hyper SIGTERM SIGINT SIGQUIT

echo "---> Cleaning old libvirt info dirs..."
rm -rf /run/libvirt/*
rm -r /var/lib/libvirt/dnsmasq

echo "---> Setting ssh password to API_HYPERVISORS_SECRET"
echo "root:$API_HYPERVISORS_SECRET" |chpasswd

echo "---> Starting sshd server..."
ssh-keygen -A
/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config >/dev/null 2>&1 &
sleep 1

# Do NOT progress the startup until the API is reachable. A hypervisor that runs
# its (slow) GPU discovery and registers against a not-yet-ready API ends up
# Online-but-incomplete -- registration half-persists (no vgpus / no gpu_targets
# back), so no GPU profile is applied and the card looks empty. This bites on a
# full-stack `docker compose up -d` where every container (db/engine/api/hyp)
# restarts at once and the fast hypervisor races ahead. Block here until the API
# answers (any HTTP status = the API is serving; only a connection failure means
# down), then register against a ready stack.
echo "---> Waiting for the API to be reachable before registering..."
api_wait=0
until python3 -c "
import os, sys, ssl, urllib.request, urllib.error
# Resolve the API base URL the SAME way the generated isardvdi_apiv4_client
# does (isardvdi_apiv4_client_auth._url.resolve_base_url): no API_DOMAIN /
# legacy sentinels mean the in-cluster isard-apiv4 service (all-in-one);
# anything else is a remote API on a standalone hypervisor. On an
# all-in-one this gate solves the boot race against the co-located
# db/engine/apiv4; on a standalone hypervisor it waits for the already-up
# remote API instead of a non-existent local service.
api_domain = os.environ.get('API_DOMAIN', '').strip()
if not api_domain or api_domain == 'isard-api' or api_domain == 'localhost' or api_domain.startswith('isard-'):
    base = 'http://isard-apiv4:5000/api/v4/'
else:
    base = 'https://%s/api/v4/' % api_domain
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
try:
    urllib.request.urlopen(base, timeout=3, context=ctx)
except urllib.error.HTTPError:
    pass  # 4xx/5xx still means the API process is up and serving
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  api_wait=$((api_wait + 3))
  echo "     API not reachable yet (${api_wait}s elapsed); waiting 3s..."
  sleep 3
done
echo "---> API reachable; proceeding with registration."

# Release the GPUs BEFORE any discovery/apply. A privileged container runs qemu
# in the HOST PID namespace, so qemu from the previous container life survives a
# restart and still holds VFs/mdevs. Both of the next steps are unsafe while a
# stale qemu holds a card: discovery cycles SR-IOV VFs (`sriov-manage -d` wedges
# the PF in D-state if a VF is in use), and the registration apply is
# non-deliberate, so a busy card makes it skip the carve entirely. So kill any
# leftover qemu and wipe sysfs mdevs FIRST -- then `setup` discovers and carves a
# clean card, and the pool it creates is the final one. (This block used to run
# AFTER `setup`, which destroyed the freshly-applied vGPU pool and left the DB
# advertising phantom mdevs.)
echo "---> Cleaning up leftover qemu processes and mdevs (before GPU discovery)..."
STALE_QEMU=$(pgrep -f 'qemu-system' 2>/dev/null || true)
if [ -n "$STALE_QEMU" ]; then
    echo "    Killing $(echo "$STALE_QEMU" | wc -w) leftover qemu process(es)..."
    echo "$STALE_QEMU" | xargs kill -TERM 2>/dev/null || true
    # Wait up to 10s for graceful exit, then force
    for i in $(seq 1 20); do
        pgrep -f 'qemu-system' >/dev/null 2>&1 || break
        sleep 0.5
    done
    pgrep -f 'qemu-system' >/dev/null 2>&1 && {
        echo "    Force-killing remaining qemu processes..."
        pkill -9 -f 'qemu-system' 2>/dev/null || true
        sleep 1
    }
fi
# Wipe all sysfs mdevs now that no qemu holds them, so discovery+apply start clean
for uuid in $(ls /sys/bus/mdev/devices/ 2>/dev/null); do
    echo 1 > /sys/bus/mdev/devices/$uuid/remove 2>/dev/null || true
done
echo "    qemu cleanup done (remaining mdevs: $(ls /sys/bus/mdev/devices/ 2>/dev/null | wc -l))"

echo "---> Registering hypervisor with API (certificates + SR-IOV/GPU discovery)..."
echo "     GPU/vGPU discovery can take a while on vGPU hosts;"
echo "     see 'docker logs isard-hypervisor' for per-GPU progress and failures."
report_step 0 "GPU/hardware discovery" None
python3 /src/lib/hypervisor.py setup
chmod 440 /etc/pki/libvirt-spice/*
chown qemu:root /etc/pki/libvirt-spice/*

# Hypervisor record now exists in DB — start reporting progress
report_step 1 "API registration" None

# Read VPN tunneling mode from API response (saved by hypervisor.py setup)
if [ -f /tmp/vpn_tunneling_mode ]; then
  HYPERVISOR_VPN_TUNNELING_MODE=$(cat /tmp/vpn_tunneling_mode)
else
  HYPERVISOR_VPN_TUNNELING_MODE="wireguard+geneve"
fi
export HYPERVISOR_VPN_TUNNELING_MODE
echo "---> VPN tunneling mode: $HYPERVISOR_VPN_TUNNELING_MODE"

if [ "$HYPERVISOR_VPN_TUNNELING_MODE" = "wireguard+geneve" ]; then
  echo "---> Setting up hypervisor wg VPNc from api..."
  python3 /src/lib/vpnc.py
else
  echo "---> Skipping WireGuard VPNc (tunneling mode: $HYPERVISOR_VPN_TUNNELING_MODE)"
fi
report_step 2 "VPN setup" None

echo "---> Setting up OpenVswitch over wg..."
sh -c "/src/ovs/setup.sh"

# Read WG hypers gateway IP computed by setup.sh
if [ -f /tmp/wg_hypers_gw ]; then
  WG_HYPERS_GW=$(cat /tmp/wg_hypers_gw)
else
  WG_HYPERS_GW=$(python3 -c "
import ipaddress, os
n = ipaddress.ip_network(os.environ.get('WG_HYPERS_NET', '10.1.0.0/24'), strict=False)
print(n[1])
" 2>/dev/null || echo "10.1.0.1")
fi

echo "---> Starting OVS worker daemon..."
# Worker uses Unix socket at /var/run/openvswitch/ovs-worker.sock
python3 /src/ovs/ovs-worker.py &
OVS_WORKER_PID=$!
echo "OVS worker daemon started (PID: $OVS_WORKER_PID)"
# Wait a moment for socket to be ready
sleep 1
report_step 3 "OVS setup" None

env > /tmp/env # This is needed by the dnsmasq-hook to get the envvars
# This is the route needed, should be added from above python script
#ip r a $WG_USERS_NET via ${WG_HYPER_NET_WG_PEER}

echo "---> Configuring hugepages support..."
if awk '$2 == "/dev/hugepages" && $3 == "hugetlbfs" { found = 1 } END { exit !found }' /proc/mounts 2>/dev/null; then
  if ! grep -q '^hugetlbfs_mount' /etc/libvirt/qemu.conf 2>/dev/null; then
    echo 'hugetlbfs_mount = "/dev/hugepages"' >> /etc/libvirt/qemu.conf
    echo "    hugetlbfs_mount added to qemu.conf"
  else
    echo "    hugetlbfs_mount already configured"
  fi
else
  echo "    /dev/hugepages is not a hugetlbfs mount, skipping"
fi

echo "---> Starting libvirt daemon..."
chown root:kvm /dev/kvm
/usr/sbin/virtlogd -d
sleep 2
/usr/sbin/libvirtd -d
false
while [ $? -ne 0 ]; do
  sleep 1
  echo "Waiting for libvirt to start..."
  virsh list >/dev/null 2>&1
done
echo "Libvirt started!"
report_step 4 "Libvirt startup" None

#echo "---> Setting vlans..."
#sh -c "/src/vlans/vlans-discover.sh"

echo "---> Setting up networks..."
cp /opt/default_networks/*.xml /etc/libvirt/qemu/networks/
FILES=/etc/libvirt/qemu/networks/*
for f in $FILES
do
  filename=$(basename -- "$f")
  filename="${filename%.*}"
  if [ $filename != "autostart" ]; then
    /usr/bin/virsh net-destroy $filename >/dev/null 2>&1
    /usr/bin/virsh net-undefine $filename >/dev/null 2>&1
  fi
done

cp /opt/default_networks/*.xml /etc/libvirt/qemu/networks/
cp /opt/custom_networks/*.xml /etc/libvirt/qemu/networks/
FILES=/etc/libvirt/qemu/networks/*
for f in $FILES
do
  filename=$(basename -- "$f")
  filename="${filename%.*}"
  if [ $filename != "autostart" ]; then
    echo "Activating network: $filename"
    /usr/bin/virsh net-define $f
    /usr/bin/virsh net-start $filename
    /usr/bin/virsh net-autostart $filename
  fi
done
report_step 5 "Network setup" None

# GPUs were discovered AND carved at registration (step 0) on a clean card (the
# qemu/mdev cleanup now runs BEFORE registration, above). The destructive second
# discovery that used to live here ran another `sriov-manage` VF cycle, which
# wiped the freshly-applied vGPU pool and left the DB advertising phantom mdevs.
# It is gone; only report hugepages here (read-only).
echo "---> Reporting hugepages..."
export LD_LIBRARY_PATH=/usr/lib:${LD_LIBRARY_PATH:-}
python3 -c "
from lib.gpu_discovery import discover_hugepages
import json
hp = discover_hugepages()
if hp.get('1G', {}).get('total') or hp.get('2M', {}).get('total'):
    print(json.dumps(hp, indent=2))
else:
    print('No hugepages configured')
"
report_step 6 "Hugepages report" None

echo "---> Checking hypervisor by creating/destroying test domain..."
virsh create /src/checks/domain.xml
virsh destroy domain
report_step 7 "Domain test" None

echo "---> Applying custom BLACKLIST_IPTABLES rules"
BLACKLIST_IPTABLES=$(echo $BLACKLIST_IPTABLES | tr "," " ")
for BLACKLIST_IPTABLES in $BLACKLIST_IPTABLES
do
   echo "$BLACKLIST_IPTABLES"
   iptables -I FORWARD -d "$BLACKLIST_IPTABLES" -o eth0 -j REJECT --reject-with icmp-port-unreachable
done

echo "---> Securing network connections from guests to dockers..."
# Block traffic from guests to other dockers
iptables -I FORWARD -o eth0 -d $(ip -o -4 addr show dev eth0 | awk '{print $4}') -j REJECT
# Block traffic from guests default isolated network to hypervisor itself
iptables -A INPUT -s 192.168.120.0/22  -d $DOCKER_NET.17 -j REJECT --reject-with icmp-port-unreachable
# Block traffic from guests shared network to hypervisor itself
iptables -A INPUT -s 192.168.124.0/22  -d $DOCKER_NET.17 -j REJECT --reject-with icmp-port-unreachable

echo "---> Applying custom WHITELIST_IPTABLES rules"
WHITELIST_IPTABLES=$(echo $WHITELIST_IPTABLES | tr "," " ")
for WHITELIST_IPTABLES in $WHITELIST_IPTABLES
do
   echo "$WHITELIST_IPTABLES"
   iptables -I FORWARD -s "$WHITELIST_IPTABLES" -o eth0 -j ACCEPT
   iptables -I FORWARD -d "$WHITELIST_IPTABLES" -o eth0 -j ACCEPT
done
report_step 8 "Firewall rules" None

echo "---> Applying NOTRACK rules for tunnel traffic (reduces conntrack overhead)..."
# In both modes the on-the-wire tunnel port is WG_HYPERS_PORT:
#   wireguard+geneve: WireGuard UDP on WG_HYPERS_PORT (Geneve 6081 runs inside the tunnel)
#   geneve:           plain Geneve UDP on WG_HYPERS_PORT
_tunnel_port=${WG_HYPERS_PORT:-4443}
iptables -t raw -C PREROUTING -p udp --dport "$_tunnel_port" -j NOTRACK 2>/dev/null || \
    iptables -t raw -I PREROUTING 1 -p udp --dport "$_tunnel_port" -j NOTRACK
iptables -t raw -C OUTPUT -p udp --sport "$_tunnel_port" -j NOTRACK 2>/dev/null || \
    iptables -t raw -I OUTPUT 1 -p udp --sport "$_tunnel_port" -j NOTRACK
echo "  Tunnel traffic (UDP $_tunnel_port): NOTRACK applied"

echo "---> Applying Video Traffic Prioritization..."
/src/tc/tc_video.sh

python3 /src/lib/check-cert.py &

if [ -z "$HYPER_ENABLED" ] || [ "$HYPER_ENABLED" == "true" ]
then
  echo "---> Enabling hypervisor..."
  python3 /src/lib/hypervisor.py enable
  report_step 9 "Ready" None
else
  echo "---> NOT enabling hypervisor because HYPER_ENABLED envvar missing or not true."
fi

echo "---> Setting process priorities..."
chmod +x /src/lib/set-priorities.sh
/src/lib/set-priorities.sh

echo "---> HYPERVISOR READY <---"
touch /tmp/qemu-hook.log
tail -f /tmp/qemu-hook.log &
while true
do
    if [ "$HYPERVISOR_VPN_TUNNELING_MODE" = "wireguard+geneve" ]; then
        ping -c 1 $WG_HYPERS_GW >/dev/null 2>&1
        if [[ $? -ne 0 ]]; then
            wg-quick down wg0  >/dev/null 2>&1
            wg-quick up wg0  >/dev/null 2>&1
        fi
    fi

    sleep 60 &
    wait $!
done

