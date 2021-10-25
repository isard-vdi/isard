import json
import os
import sys

from api_client import ApiClient

apic = ApiClient()

# sys.argv 1 - add
# sys.argv 2 - 52:54:00:2c:7a:13
# sys.argv 3 - 192.168.128.76
# sys.argv 4 - slax

try:
    if str(sys.argv[1]) in ["old", "add"]:
        resp = apic.post(
            "hypervisor/vm/wg_addr", {"mac": str(sys.argv[2]), "ip": str(sys.argv[3])}
        )
        with open("/tmp/apiresponse", "w") as f:
            f.write(str(resp))
except Exception as e:
    with open("/tmp/apicallexception", "w") as f:
        f.write(str(e))
    exit(1)
