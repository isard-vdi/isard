import os, time
from pprint import pprint
import traceback

from pythonping import ping
import logging as log

from subprocess import check_call, check_output

from api_client import ApiClient
apic=ApiClient()

def connect(peer):
    try:
        check_output(('/usr/bin/wg-quick', 'down', 'wg0'), text=True).strip()
    except:
        None
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(peer)
    check_output(('/usr/bin/wg-quick', 'up', 'wg0'), text=True).strip()

def reacheable(hostname, waittime=1000):
    res = ping(hostname, count=1, timeout=1)
    if res.success(): return True
    return False


########### GET VPN CONFIG

### API CONFIG
ok=False
while not ok:
    try:
        if os.environ.get('API_DOMAIN',False):
            hypervisor = os.environ['DOMAIN']
        else:
            hypervisor = 'isard-hypervisor'

        peer=apic.get('hypervisor_vpn/'+hypervisor)
        if not peer:
            print('Api unable to connect to this host:port through ssh-keyscan.')
            time.sleep(4)
        if peer.get('content'):
            connect(peer['content'])
            ok=True
        else:
            print('Can not get hypervisor wg VPNc config from api. Retrying...')
            time.sleep(4)
    except:
        peer=False
        print('Could not contact api to get wg VPNc config. Retrying...')
        time.sleep(4)

print(check_output(('/usr/bin/wg', 'show'), text=True).strip())
print('Hypervisor wg VPNc networking connected.')
 