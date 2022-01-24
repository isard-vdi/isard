import random

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
from resources import base, gpus, usbs


def create_usbs(usbs):
    print("CREATING USB RESERVABLE ITEMS")
    try:
        for usb in usbs:
            usb_selected = r.table("usb_profiles").get(usb["item_profile_id"]).run()
            profiles_enabled = []
            for profile in usb["profiles"]:
                new_profile = [
                    p for p in usb_selected["profiles"] if p["id"] == profile
                ][0]
                profiles_enabled.append(profile)

                new_reservable_usb = {
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": ["admin"],
                        "users": False,
                    },
                    "brand": usb_selected["brand"],
                    "description": usb_selected["brand"]
                    + " USB "
                    + usb_selected["model"]
                    + " with profile "
                    + new_profile["profile"]
                    + " with maximum "
                    + str(new_profile["units"])
                    + " USB per device",
                    "id": usb_selected["brand"]
                    + "-"
                    + usb_selected["model"]
                    + "-"
                    + new_profile["profile"],
                    "model": usb_selected["model"],
                    "name": "USB "
                    + usb_selected["brand"]
                    + " "
                    + usb_selected["model"],
                    "profile": new_profile["profile"],
                    "units": new_profile["units"],
                }
                r.table("reservables_usbs").insert(
                    new_reservable_usb, conflict="update"
                ).run()
                print(" - " + usb["id"] + " / " + new_reservable_usb["id"])
            new_usb = {
                "id": usb["id"],
                "name": usb["id"],
                "description": usb_selected["description"],
                "brand": usb_selected["brand"],
                "model": usb_selected["model"],
                "profiles_enabled": profiles_enabled,
            }
            r.table("usbs").insert(new_usb, conflict="update").run()

    except Exception as e:
        print(traceback.format_exc())


def create_gpus(gpus):
    print("CREATING GPU RESERVABLE ITEMS")
    try:
        for gpu in gpus:
            gpu_selected = r.table("gpu_profiles").get(gpu["item_profile_id"]).run()
            profiles_enabled = []
            for profile in gpu["profiles"]:
                new_profile = [
                    p for p in gpu_selected["profiles"] if p["id"] == profile
                ][0]
                profiles_enabled.append(profile)

                new_reservable_vgpu = {
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": ["admin"],
                        "users": False,
                    },
                    "brand": gpu_selected["brand"],
                    "description": gpu_selected["brand"]
                    + " vGPU "
                    + gpu_selected["model"]
                    + " with profile "
                    + new_profile["profile"]
                    + " with "
                    + str(new_profile["memory"])
                    + " vRAM with maximum "
                    + str(new_profile["units"])
                    + " vGPUs per device",
                    "heads": 1,
                    "id": gpu_selected["brand"]
                    + "-"
                    + gpu_selected["model"]
                    + "-"
                    + new_profile["profile"],
                    "model": gpu_selected["model"],
                    "name": "GPU "
                    + gpu_selected["brand"]
                    + " "
                    + gpu_selected["model"]
                    + " "
                    + str(new_profile["memory"]),
                    "profile": new_profile["profile"],
                    "ram": new_profile["memory"],
                    "vram": new_profile["memory"],
                    "units": new_profile["units"],
                    "priority_id": "default",
                }
                r.table("reservables_vgpus").insert(
                    new_reservable_vgpu, conflict="update"
                ).run()
                print(" - " + gpu["id"] + " / " + new_reservable_vgpu["id"])
            new_gpu = {
                "id": gpu["id"],
                "name": gpu["id"],
                "description": gpu_selected["description"],
                "architecture": gpu_selected["architecture"],
                "memory": gpu_selected["memory"],
                "brand": gpu_selected["brand"],
                "model": gpu_selected["model"],
                "profiles_enabled": profiles_enabled,
            }
            r.table("gpus").insert(new_gpu, conflict="update").run()

    except Exception as e:
        print(traceback.format_exc())


create_gpus(gpus)
create_usbs(usbs)

## Check endpoint created resources
print("\n CHECKING CREATED RESOURCES THROUGH ENDPOINTS")
response = requests.get(
    base + "/reservables",
    json={},
)
reservables = json.loads(response.text)
# print(" - /reservables -> " + str(reservables))

for reservable in reservables:
    response = requests.get(
        base + "/reservables/" + reservable,
        json={},
    )

    items = json.loads(response.text)
    for item in items:
        # print(" - "+reservable+" item found "+item["brand"]+"/"+item["model"]+" (/reservables/"+reservable+"): "+item["id"])

        response = requests.get(
            base + "/reservables/enabled/" + reservable + "/" + item["id"],
            json={},
        )

        profiles = json.loads(response.text)
        for profile in profiles:
            print(" - " + reservable + " / " + item["id"] + " / " + profile["id"])
            # print(" - Profile found for "+reservable+"  "+item["brand"]+"/"+item["model"]+" (/reservables/"+reservable+"/"+item["id"]+"): "+profile["id"])
