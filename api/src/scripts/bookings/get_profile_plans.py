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

for gpu in gpus:
    for profile in gpu["profiles"]:
        response = requests.get(
            base + "/reservables_planner/subitem/" + profile,
            json={},
        )

        plans = json.loads(response.text)
        print("\nPLANNING FOR " + profile)
        for plan in plans:
            print(
                profile
                + " ("
                + str(plan["units"])
                + "): "
                + plan["start"]
                + " / "
                + plan["end"]
            )
