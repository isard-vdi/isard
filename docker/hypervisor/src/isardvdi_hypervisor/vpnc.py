import logging as log
import os
import sys
import time
import traceback
from pprint import pprint
from subprocess import DEVNULL, check_call, check_output

from isardvdi_apiv4_client.api.role_admin import admin_hypervisor_vpn
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from pythonping import ping

# Not /usr/bin/wg-quick: the host AppArmor profile attaches to that path.
WG_QUICK = "/isard/bin/wg-quick"


def connect(peer):
    try:
        check_output((WG_QUICK, "down", "wg0"), stderr=DEVNULL).strip()
    except:
        None
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(peer)
    check_output((WG_QUICK, "up", "wg0"), text=True).strip()


def reacheable(hostname, waittime=1000):
    res = ping(hostname, count=1, timeout=1)
    if res.success():
        return True
    return False


########### GET VPN CONFIG


def _fetch_peer_content():
    """One API attempt; the wg config content, or None if the api gave none."""
    hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")
    with build_client("isard-hypervisor", role="hypervisor") as client:
        resp = admin_hypervisor_vpn.sync_detailed(client=client, hyper_id=hyper_id)
        raise_for_status(resp)
        peer = resp.parsed.to_dict() if resp.parsed else {}
    return peer.get("content")


def run_once():
    """Watchdog recovery: reconnect if the config changed, bounce wg0 if same, 1 if api down."""
    try:
        content = _fetch_peer_content()
    except Exception as e:
        print(f"vpnc --once: could not fetch wg VPNc config: {type(e).__name__}: {e}")
        return 1
    if not content:
        print("vpnc --once: api returned no wg VPNc config")
        return 1
    try:
        with open("/etc/wireguard/wg0.conf") as f:
            current = f.read()
    except OSError:
        current = None
    if content != current:
        connect(content)
        print("vpnc --once: config changed, reconnected wg0")
    else:
        check_call((WG_QUICK, "down", "wg0"))
        check_call((WG_QUICK, "up", "wg0"))
        print("vpnc --once: config unchanged, bounced wg0")
    return 0


def main():
    if "--once" in sys.argv:
        return run_once()
    ### API CONFIG
    ok = False
    while not ok:
        try:
            hyper_id = os.environ.get("HYPER_ID", "isard-hypervisor")

            with build_client("isard-hypervisor", role="hypervisor") as client:
                resp = admin_hypervisor_vpn.sync_detailed(
                    client=client, hyper_id=hyper_id
                )
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
            print(
                f"Failed to fetch wg VPNc config: {type(e).__name__}: {e}. Retrying..."
            )
            traceback.print_exc()
            time.sleep(1)

    print(check_output(("/usr/bin/wg", "show"), text=True).strip())
    print("Hypervisor wg VPNc networking connected.")


if __name__ == "__main__":
    sys.exit(main())
