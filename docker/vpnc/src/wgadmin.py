import os, time
from pprint import pprint
import traceback

from pythonping import ping

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlDriverError, ReqlTimeoutError, ReqlOpFailedError

import logging as log

from subprocess import check_call, check_output

conn = False

def dbConnect():
    global conn
    try:
        conn.close()
    except:
        None
    try:
        conn = r.connect(host=os.environ['STATS_RETHINKDB_HOST'], port=os.environ['STATS_RETHINKDB_PORT'],db=os.environ['RETHINKDB_DB']).repl()
    except:
        conn = False
        raise

def get_wireguard_file(peer):
    endpoint=os.environ['STATS_RETHINKDB_HOST']
    try:
        server_public_key=r.db('isard').table('config').get(1).pluck({'vpn_hypers':{'wireguard':{'keys':{'public'}}}}).run()['vpn_hypers']['wireguard']['keys']['public']
    except:
        raise
    return """[Interface]
Address = %s
PrivateKey = %s

[Peer]
PublicKey = %s
Endpoint = %s:%s
AllowedIPs = %s
PersistentKeepalive = 21
""" % (peer['vpn']['wireguard']['Address'],peer['vpn']['wireguard']['keys']['private'],server_public_key,endpoint,os.environ['WG_HYPERS_PORT'],peer['vpn']['wireguard']['AllowedIPs'])

def init_client(peer):
    ## Server config
    try:
        check_output(('/usr/bin/wg-quick', 'down', 'wg0'), text=True).strip()
    except:
        None
    with open("/etc/wireguard/wg0.conf", "w") as f:
        f.write(get_wireguard_file(peer))
    check_output(('/usr/bin/wg-quick', 'up', 'wg0'), text=True).strip()


def reacheable(hostname, waittime=1000):
    res = ping(hostname, count=1, timeout=1)
    if res.success(): return True
    return False

while True:
    if conn == False:
        try:
            print('Try DB connection...')
            dbConnect()
            print('   -> DB connection stablished.')
        except:
            print('  DB connection failed. Retrying...')
            time.sleep(5)
            continue

    if reacheable("10.0.0.1") == True:
        print('   GW reached...') 
        connection = True
        time.sleep(5)
        continue
    else:
        print('   GW failed!')
        time.sleep(5)
    try:
        print('Try to get hostname data from DB...')
        peer = r.table('hypervisors').get(os.environ['HOSTNAME']).run()
        if peer != None:
            init_client(peer)
        if reacheable("10.0.0.1"):
            ## Gateway reached
            connection = True
            time.sleep(10)
            continue
        else:
            print('   GW failed! Try db connection again...')
            time.sleep(5)
            conn = False
    except:
        print('   Failed to get data from DB')
        conn = False
        continue

print('Thread ENDED!!!!!!!')
log.error('Thread ENDED!!!!!!!')  