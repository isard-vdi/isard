import sys
import traceback

from isardvdi_apiv4_client.api.role_admin import admin_register_vlans
from isardvdi_apiv4_client.models import AdminRegisterVlansRequest
from isardvdi_apiv4_client_auth import build_client, raise_for_status

if len(sys.argv) < 2:
    print(sys.argv)
    print("Needs to specify vlan numbers as arguments. Exitting.")
    exit(1)

vlans = [vlan for vlan in sys.argv[1:]]

try:
    with build_client("isard-hypervisor", role="hypervisor") as client:
        resp = admin_register_vlans.sync_detailed(
            client=client,
            body=AdminRegisterVlansRequest(vlans=vlans),
        )
        raise_for_status(resp)
except Exception:
    print(traceback.format_exc())
    exit(1)
