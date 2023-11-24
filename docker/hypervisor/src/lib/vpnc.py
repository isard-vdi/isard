import logging as log
import os
import time
import traceback
from pprint import pprint
from subprocess import DEVNULL, check_call, check_output

from api_client import ApiClient
from pythonping import ping

apic = ApiClient()


def connect(peer):
    try:
        check_output(("/usr/bin/wg-quick", "down", "wg0"), stderr=DEVNULL).strip()
    except:
        None
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(peer)
    check_output(("/usr/bin/wg-quick", "up", "wg0"), text=True).strip()


def reacheable(hostname, waittime=1000):
    res = ping(hostname, count=1, timeout=1)
    if res.success():
        return True
    return False


########### GET VPN CONFIG

### API CONFIG
ok = False
while not ok:
    try:
        hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")

        peer = apic.get("hypervisor_vpn/" + hyper_id)
        if not peer:
            print("Api unable to connect to this host:port through ssh-keyscan.")
            time.sleep(1)
        if peer.get("content"):
            connect(peer["content"])
            gw = peer["content"].split("AllowedIPs = ")[1].split("/")[0]
            if not reacheable(gw):
                print("Could not connect to vpn internal gw: " + gw)
            ok = True
        else:
            print("Can not get hypervisor wg VPNc config from api. Retrying...")
            time.sleep(4)
    except:
        peer = False
        print("Could not contact api to get wg VPNc config. Retrying...")
        time.sleep(1)

print(check_output(("/usr/bin/wg", "show"), text=True).strip())
print("Hypervisor wg VPNc networking connected.")
