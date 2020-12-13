import os, sys, json

from api_client import ApiClient

apic=ApiClient()

#sys.argv 1 - add 
#sys.argv 2 - 52:54:00:2c:7a:13 
#sys.argv 3 - 192.168.128.76 
#sys.argv 4 - slax

try:
  with open('/var/lib/libvirt/dnsmasq/virbr20.macs') as json_file:
    data = json.load(json_file)
    id=[d['domain'] for d in data if sys.argv[2] in d['macs']]
  if len(id) and str(sys.argv[1]) in ['old','add']:
    resp=apic.post('guest_addr',{'id':id[0],'ip':str(sys.argv[3])})
    with open("/tmp/apiresponse", "w") as f:
        f.write(str(resp))
except FileNotFoundError:
  with open("/tmp/macs_file_not_found", "w") as f:
      f.write('')  
  exit(0)
except Exception as e:
  with open("/tmp/apicallexception", "w") as f:
      f.write(str(e))
  exit(1)