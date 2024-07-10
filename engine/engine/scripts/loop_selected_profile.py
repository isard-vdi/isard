import json
from datetime import datetime
from pprint import pformat, pprint
from time import sleep

import requests

old1 = {}
old2 = {}
while True:
    res = json.loads(
        requests.get(
            "http://localhost:5000/profile/gpu/isard-hypervisor-pci_0000_41_00_0",
            timeout=10,
        ).text
    )
    if old1 != res:
        old1 = res
        pprint(datetime.now().strftime("%H:%M:%S"))
        pprint(old1)

    res = json.loads(
        requests.get(
            "http://localhost:5000/profile/gpu/isard-hypervisor-pci_0000_61_00_0",
            timeout=10,
        ).text
    )
    if old2 != res:
        old2 = res
        pprint(datetime.now().strftime("%H:%M:%S"))
        pprint(old2)

    sleep(5)
