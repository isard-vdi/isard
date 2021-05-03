import os, sys, json
from time import sleep
from pprint import pprint
import traceback
from api_client import ApiClient

# Instantiate connection
try:
    apic=ApiClient()
except:
    print(traceback.format_exc())
    exit(1)

    


import os,sys
from rethinkdb import r, ReqlTimeoutError
import pprint

r.connect(os.environ['STATS_RETHINKDB_HOST'], os.environ['STATS_RETHINKDB_PORT']).repl()

if len(sys.argv) < 2:
    print(sys.argv)
    print("Needs to specify vlan numbers as arguments. Exitting.")
    exit(1)

for vlan in sys.argv[1:]:
    new_vlan = {'id': 'v'+vlan,
                    'name': 'Vlan '+vlan,
                    'description': 'Infrastructure vlan',
                    'ifname': 'br-'+vlan,
                    'kind': 'bridge',
                    'model': 'virtio',
                    'net': 'br-'+vlan,
                    'qos_id': False,
                    'allowed': {
                        'roles': ['admin'],
                        'categories': False,
                        'groups': False,
                        'users': False}
                    }
    r.db('isard').table('interfaces').insert(new_vlan).run()
