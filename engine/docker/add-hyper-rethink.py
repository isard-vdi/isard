import optparse
from rethinkdb import r

parser = optparse.OptionParser()

parser.add_option('-u', '--user',
    action="store", dest="user",
    help="Username to connect to hypervisor. Default=root", default="root")
parser.add_option('-a', '--address',
    action="store", dest="hostname",
    help="Hostname/IP to connect to hypervisor. Required.")
parser.add_option('-i', '--id',
    action="store", dest="id",
    help="Name to identify hypervisor. Default=HOSTNAME")
parser.add_option('-p', '--port',
    action="store", dest="port",
    help="SSH port to hypervisor. Default=2022", default=2022)
parser.add_option('-o', '--pool',
    action="store", dest="hpool",
    help="Pool for hypervisor. Default=default", default="default")
parser.add_option('-d', '--disk-capability',
    action="store", dest="diskcap",
    help="Disk capabilities. Default=False", default=True)
parser.add_option('-v', '--virtual-capability',
    action="store", dest="hypercap",
    help="Hypervisor capabilities. Default=True", default=True)    
parser.add_option('-m', '--viewer-hostname',
    action="store", dest="vhostname",
    help="Hostname accessible for viewers internally. Default=HOSTNAME") 
parser.add_option('-n', '--viewer-nat-hostname',
    action="store", dest="vnathostname",
    help="Hostname accessible for viewers externally. Default=HOSTNAME") 
parser.add_option('-f', '--viewer-nat-offset',
    action="store", dest="vnatoffset",
    help="Offset added to default viewers port externally. Default=0") 
options, args = parser.parse_args()

if not options.hostname:
    print('Hostname/IP is required. Add -a or --address')
    exit(1)

USER=options.user
HOSTNAME=options.hostname
ID=options.id if options.id else options.hostname
PORT=str(options.port)
HPOOL=options.hpool
DISKCAP=options.diskcap
HYPERCAP=options.hypercap
VHOSTNAME=options.vhostname if options.vhostname else options.hostname
VNATHOSTNAME=options.vnathostname if options.vnathostname else options.hostname
VNATOFFSET=str(options.vnatoffset) if options.vnatoffset else 0

hdict={'capabilities': {'disk_operations': DISKCAP, 'hypervisor': HYPERCAP},
             'description': '',
             'detail': '',
             'enabled': True,
             'hostname': HOSTNAME,
             'hypervisors_pools': [str(HPOOL)],
             'id': str(ID),
             'port': str(PORT),
             'uri': 'qemu+ssh://'+USER+'@'+HOSTNAME+':'+PORT+'/system',
             'user': USER,
             'viewer_hostname': VHOSTNAME,
             'viewer_nat_hostname': VNATHOSTNAME,
             'viewer_nat_offset': str(VNATOFFSET)}

try:
    r.connect('isard-database', 28015).repl()
    r.db('isard').table('hypervisors').insert(hdict, conflict="error").run()
except Exception as e:
    print('Error adding hypervisor to database. Add it through Isard admin web.')
    print('Err:'+str(e))

