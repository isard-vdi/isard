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

# Get hostname
hostname=os.environ['HOSTNAME']

ok=False
while not ok:
    data=apic.post('hypervisor',data={'hostname':hostname})
    if not data:
        print('Could not contact api... retrying...')
        sleep(2)
        continue
    if not data['certs']['ca-cert.pem']: 
        print('Certificate not found in main isard host.')
        sleep(2)
    else:
        ok=True

try:
    update=False
    with open('/etc/pki/libvirt-spice/ca-cert.pem','r') as clientcert:
        if clientcert.read() not in data['certs']['ca-cert.pem']: 
            print('ca-cert differs from existing one, needs updating.')
            update=True
        else:
            print('Viewers certificates seem to be ok.')
    with open('/root/.ssh/authorized_keys','r') as hostkey:
        if hostkey.read() not in data['certs']['id_rsa.pub']: 
            print('id_rsa key differs from existing one, needs updating')
            update=True
        else:
            print('Authorized key from engine seem to be ok.')
except:
    print('New certificates found so updating it from main isard...')
    update=True

try:
    if update:
        print('Updating viewer certificates from main isard host...')
        for k,v in data['certs'].items():
            if k == 'id_rsa.pub':
                with open("/root/.ssh/authorized_keys", "w") as f:
                    f.write(v)
            else:
                with open("/etc/pki/libvirt-spice/"+k, "w") as f:
                    f.write(v)
except:
    print(traceback.format_exc())
    exit(1)