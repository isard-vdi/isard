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
from resources import base, priorities


def create_priorities():
    r.table("bookings_priority").insert(priorities, conflict="update").run()


create_priorities()
