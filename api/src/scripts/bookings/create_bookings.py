# from datetime import strptime
import itertools
import json
import random
import time
from datetime import datetime, timedelta
from pprint import pprint

import portion as P
import pytz
import requests
import responses
from helpers import _parseString, date_generator, header_auth
from resources import base, desktop_id, gpus, new_desktop, usbs
from rethinkdb import r

start = "2022-04-10T22:00%2B00:00"
end = "2022-04-17T21:59%2B00:00"
user_base = "http://localhost:5000/api/v3"


def get_resource_plans():
    response = requests.get(
        user_base
        + "/bookings/user/"
        + desktop_id
        + "/desktop?startDate="
        + start
        + "&endDate="
        + end
        + "&returnType=all",
        json={},
        headers=header_auth(),
    )

    plans = json.loads(response.text)
    return plans


plans = get_resource_plans()
pprint(plans)
exit(1)


def get_desktops():
    response = requests.get(
        base + "/domains", json={"kind": "desktop"}, headers=header_auth()
    )
    return json.loads(response.text)


def set_desktop_reservables(desktop):
    # Add profile to one domain

    r.db("isard").table("domains").get(desktop["id"]).update(
        {"create_dict": {"reservables": new_desktop["reservables"]}}
    ).run()


def new_booking(start=None, end=None):
    desktops = get_desktops()
    desktop = desktops[random.randrange(0, len(desktops))]
    set_desktop_reservables(desktop)

    payload = {"user_id": "admin"}
    if not start and not end:
        start_new = list(itertools.islice(date_generator(), 1))[0]
        start = start_new.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        end = (
            list(itertools.islice(date_generator(start_new), 2))[1]
            .astimezone(pytz.UTC)
            .strftime("%Y-%m-%dT%H:%M%z")
        )
    # else:
    # start = datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
    # end = datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
    booking = {
        "element_id": desktop["id"],
        "element_type": "desktop",
        "title": desktop["name"],
        "start": start,
        "end": end,
    }
    pprint(booking)

    response = requests.post(
        user_base + "/booking/event", json=booking, headers=header_auth()
    )
    return json.loads(response.text)


new_booking(start, end)
