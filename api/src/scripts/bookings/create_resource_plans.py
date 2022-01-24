import datetime
import itertools
import json
import random
import time
from datetime import timedelta
from pprint import pprint

import portion as P
import pytz
import requests
import responses
from helpers import _parseString, date_generator
from resources import base, gpus, usbs
from rethinkdb import r


def add_random(gpus, usbs, number=16):
    date = list(itertools.islice(date_generator(), 1))[0]
    for i in range(1, number):
        gpu_selected = gpus[random.randrange(0, len(gpus))]
        print("Selected GPU: " + gpu_selected["id"] + " MODEL: " + gpu_selected["id"])

        response = requests.get(
            base + "/reservables/enabled/gpus/" + gpu_selected["id"],
            json={},
        )

        profiles = json.loads(response.text)
        pprint(profiles)
        profile_selected = profiles[random.randrange(0, len(profiles))]
        nextdate = list(itertools.islice(date_generator(date), 2))[1]

        plan = {
            "end": nextdate.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z"),
            "subitem_id": profile_selected["id"],
            "item_id": gpu_selected["id"],
            "item_type": "gpus",
            "start": date.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%MZ"),
            "user_id": "local-default-admin-admin",
        }
        # pprint(plan)
        response = requests.post(
            base + "/reservables_planner",
            json=plan,
        )
        # print(json.loads(response.text))
        date = nextdate

    response = requests.get(
        base + "/reservables_planner/check_integrity",
    )


add_random(gpus, usbs)

exit(1)
response = requests.get(
    base + "/reservables",
    json={},
)
reservables = json.loads(response.text)
pprint("Reservables: " + str(reservables))


response = requests.get(
    base + "/reservables/" + reservables[0],
    json={},
)

gpus = json.loads(response.text)
gpus = [gpu for gpu in gpus if gpu["model"] == "A40"]

pprint([g["id"] for g in gpus])
response = requests.get(
    base + "/reservables/enabled/" + reservables[0] + "/" + gpus[0]["id"],
    json={},
)
profiles = json.loads(response.text)

exit(1)


def get_subitem_planning(subitem_id, start=None, end=None):
    if not start:
        start = datetime.now(pytz.utc)

    query = (
        r.db("isard")
        .table("resource_planner")
        .order_by(index="default_order")
        .filter({"subitem_id": subitem_id})
    )
    if end:
        query = query.filter(
            r.row["start"].during(
                start,
                end,
            )
        )
    else:
        query = query.filter(lambda plan: plan["start"] > start)

    #     # with app.app_context():
    plans = list(query.run())
    print("FOUND " + str(len(plans)) + " FOR PROFILE " + str(subitem_id))
    return plans


base = "http://localhost:5000/api/v3/admin"

response = requests.get(
    base + "/reservables",
    json={},
)
reservables = json.loads(response.text)
pprint("Reservables: " + str(reservables))


response = requests.get(
    base + "/reservables/" + reservables[0],
    json={},
)

gpus = json.loads(response.text)
gpus = [gpu for gpu in gpus if gpu["model"] == "A40"]

pprint([g["id"] for g in gpus])
response = requests.get(
    base + "/reservables/enabled/" + reservables[0] + "/" + gpus[0]["id"],
    json={},
)
profiles = json.loads(response.text)
# pprint(profiles)
# exit(1)
profile_selected = [p for p in profiles if p["id"] == "NVIDIA-A40-1Q"][0]
print("Selected PROFILE: " + profile_selected["id"])

date = list(itertools.islice(date_generator(), 1))[0]

for i in range(1, 16):
    gpu_selected = gpus[random.randrange(0, len(gpus))]
    pprint("Selected GPU: " + gpu_selected["id"] + " MODEL: " + gpu_selected["id"])

    nextdate = list(itertools.islice(date_generator(date), 2))[1]

    plan = {
        "end": nextdate.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z"),
        "subitem_id": profile_selected["id"],
        "item_id": gpu_selected["id"],
        "item_type": "gpus",
        "start": date.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z"),
        "user_id": "local-default-admin-admin",
    }
    # pprint(plan)
    response = requests.post(
        base + "/reservables_planner",
        json=plan,
    )
    # print(json.loads(response.text))
    date = nextdate

response = requests.get(
    base + "/reservables_planner/check_integrity",
)
