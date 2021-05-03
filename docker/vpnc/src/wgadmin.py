import os, time
from pprint import pprint
import traceback

from pythonping import ping

# from rethinkdb import RethinkDB; r = RethinkDB()
# from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError, ReqlOpFailedError

import logging as log

from subprocess import check_call, check_output

from api_client import ApiClient
apic=ApiClient()

conn = False

# def dbConnect():
#     global conn
#     try:
#         conn.close()
#     except:
#         None
#     try:
#         conn = r.connect(host=os.environ['WEBAPP_HOST'], port=os.environ['STATS_RETHINKDB_PORT'],db=os.environ['RETHINKDB_DB']).repl()
#     except:
#         conn = False
#         raise

# def get_wireguard_file(peer):
#     endpoint=os.environ['WEBAPP_HOST']
#     try:
#         server_public_key=r.db('isard').table('config').get(1).pluck({'vpn_hypers':{'wireguard':{'keys':{'public'}}}}).run()['vpn_hypers']['wireguard']['keys']['public']
#     except:
#         raise
#     return """[Interface]
# Address = %s
# PrivateKey = %s

# [Peer]
# PublicKey = %s
# Endpoint = %s:%s
# AllowedIPs = %s
# PersistentKeepalive = 21
# """ % (peer['vpn']['wireguard']['Address'],peer['vpn']['wireguard']['keys']['private'],server_public_key,endpoint,os.environ['WG_HYPERS_PORT'],peer['vpn']['wireguard']['AllowedIPs'])

# def init_client(peer):
#     ## Server config

#     connect(get_wireguard_file(peer))

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
        peer=apic.get('hypervisor_vpn/'+os.environ['HOSTNAME'])
        if peer.get('content'):
            connect(peer['content'])
            ok=True
        else:
            print('Can not get hypervisor '+os.environ['HOSTNAME']+' VPN config. Retrying...')
            time.sleep(4)
    except:
        peer=False
        print('Could not contact api at '+os.environ['HOSTNAME']+' to get vpn config. Retrying...')
        time.sleep(4)

print(check_output(('/usr/bin/wg', 'show'), text=True).strip())
print('Hypervisor conected to '+os.environ['HOSTNAME'])
 