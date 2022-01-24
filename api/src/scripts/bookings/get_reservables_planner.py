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
from resources import base, gpus, new_desktop, usbs
from rethinkdb import r

data = {
    "subitems": new_desktop["reservables"],
    "units": new_desktop["units"],
    "priority": new_desktop["priority"],
    "block_interval": new_desktop["block_interval_hours"],
}
response = requests.post(
    base + "/reservables_planner/booking_provisioning",
    json=data,
)

plans = json.loads(response.text)
pprint(plans)
# print("\nPLANNING FOR "+profile)
# for plan in plans:
#     print(profile+" ("+str(plan["units"])+"): "+plan["start"]+" / "+plan["end"])
