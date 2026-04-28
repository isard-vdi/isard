import sys

from isardvdi_apiv4_client.api.role_admin import admin_hypervisor_wg_addr
from isardvdi_apiv4_client.models import AdminHypervisorWgAddrData
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status

# sys.argv 1 - add
# sys.argv 2 - 52:54:00:2c:7a:13
# sys.argv 3 - 192.168.128.76
# sys.argv 4 - slax

try:
    if str(sys.argv[1]) in ["old", "add"]:
        mac = str(sys.argv[2])
        ip = str(sys.argv[3])
        with build_client("isard-hypervisor", role="hypervisor") as client:
            resp = admin_hypervisor_wg_addr.sync_detailed(
                client=client,
                body=AdminHypervisorWgAddrData(mac=mac, ip=ip),
            )
            raise_for_status(resp)
            with open("/tmp/apiresponse", "w") as f:
                f.write(str(resp.parsed))
except ApiV4Error as e:
    with open("/tmp/apicallexception", "w") as f:
        f.write(str(e))
    exit(1)
except Exception as e:
    with open("/tmp/apicallexception", "w") as f:
        f.write(str(e))
    exit(1)
