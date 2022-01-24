import random
import secrets

from rethinkdb import r

domain = "localhost"
verifycert = False
## End set global vars

import datetime
import itertools
import json
import time
import traceback
from datetime import datetime, timedelta
from pprint import pprint

import portion as P
import pytz
import requests
import responses
from helpers import _parseString
from resources import base

gpus = ["A40", "T4"]


def create_engine_vgpu(hyp_id="isard-hypervisor"):
    id = hyp_id + "-pci_0000_" + secrets.token_hex(2) + "_00_0"
    brand = "NVIDIA"
    model = gpus[random.randrange(0, len(gpus))]
    vgpu = {
        "id": id,
        "model": model,
        "brand": "NVIDIA",
        "name": id,
        "description": id,
        "info": {
            "types": {
                "12Q": {"available": 4, "id": "nvidia-563", "max": 4, "memory": 12288},
                "16Q": {"available": 3, "id": "nvidia-564", "max": 3, "memory": 16384},
                "1Q": {"available": 32, "id": "nvidia-557", "max": 32, "memory": 1024},
                "24Q": {"available": 2, "id": "nvidia-565", "max": 2, "memory": 24576},
                "2Q": {"available": 24, "id": "nvidia-558", "max": 24, "memory": 2048},
                "3Q": {"available": 16, "id": "nvidia-559", "max": 16, "memory": 3072},
                "48Q": {"available": 1, "id": "nvidia-566", "max": 1, "memory": 49152},
                "4Q": {"available": 12, "id": "nvidia-560", "max": 12, "memory": 4096},
                "6Q": {"available": 8, "id": "nvidia-561", "max": 8, "memory": 6144},
                "8Q": {"available": 6, "id": "nvidia-562", "max": 6, "memory": 8192},
            },
        },
    }

    r.db("isard").table("vgpus").insert(vgpu, conflict="update").run()


def map_vgpu2gpu():
    r.db("isard").table("gpus").update({"physical_device": None}).run()
    gpus = list(r.db("isard").table("gpus").run())
    vgpus = list(r.db("isard").table("vgpus").run())
    for vgpu in vgpus:
        for gpu in gpus:
            if (
                not gpu["physical_device"]
                and gpu["brand"] == vgpu["brand"]
                and gpu["model"] == vgpu["model"]
            ):
                r.db("isard").table("gpus").update(
                    {"physical_device": vgpu["id"]}
                ).run()


if not r.table_list().contains("vgpus").run():
    r.table_create("vgpus", primary_key="id").run()

for i in range(0, 4):
    create_engine_vgpu()

map_vgpu2gpu()
