import os,sys
from rethinkdb import r, ReqlTimeoutError
import pprint

r.connect(os.environ['STATS_RETHINKDB_HOST'], os.environ['STATS_RETHINKDB_PORT']).repl()

if len(sys.argv) < 2:
    print("Needs to specify vlan numbers as arguments. Exitting.")
    exit(1)

new_vlans = [] 
for vlan in sys.argv[1:]:
    new_vlans.append({'id': 'v'+vlan,
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
                    })

r.db('isard').table('interfaces').insert(new_vlans, conflict='update').run()

