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

if len(sys.argv) < 2:
    print(sys.argv)
    print("Needs to specify vlan numbers as arguments. Exitting.")
    exit(1)

vlans=[]
for vlan in sys.argv[1:]: vlans.append(vlan)

apic.post('vlans',json.dumps(vlans))


