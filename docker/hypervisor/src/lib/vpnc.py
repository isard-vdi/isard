import logging as log
import os
import time
import traceback
from pprint import pprint
from subprocess import DEVNULL, check_call, check_output

from isardvdi_apiv4_client.api.role_admin import admin_hypervisor_vpn
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from pythonping import ping


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

        with build_client("isard-hypervisor", role="hypervisor") as client:
            resp = admin_hypervisor_vpn.sync_detailed(client=client, hyper_id=hyper_id)
            raise_for_status(resp)
            peer = resp.parsed.to_dict() if resp.parsed else {}
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
    except ApiV4Error as e:
        peer = False
        print(f"ApiV4Error fetching wg VPNc config: {e}. Retrying...")
        time.sleep(1)
    except Exception as e:
        peer = False
        print(f"Failed to fetch wg VPNc config: {type(e).__name__}: {e}. Retrying...")
        traceback.print_exc()
        time.sleep(1)

print(check_output(("/usr/bin/wg", "show"), text=True).strip())
print("Hypervisor wg VPNc networking connected.")
