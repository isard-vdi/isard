import json
import os
import secrets
import time
import traceback
from datetime import datetime, timedelta
from pprint import pprint

from jose import jwt
from rethinkdb import r

domain = "localhost"
verifycert = False
## End set global vars

import unittest

import requests
import responses

auths = {}
dbconn = None
base = "http://isard-scheduler:5000"
dbconn = r.connect("isard-db", 28015).repl()

admin_secret_data = r.db("isard").table("secrets").get("isardvdi").run()
raw_jwt_data = {
    "exp": datetime.utcnow() + timedelta(minutes=5),
    "kid": admin_secret_data["id"],
    "data": {
        "role_id": admin_secret_data["role_id"],
        "category_id": admin_secret_data["category_id"],
    },
}
admin_jwt = jwt.encode(raw_jwt_data, admin_secret_data["secret"], algorithm="HS256")
auths["isardvdi"] = {
    "secret": admin_secret_data,
    "jwt": admin_jwt,
    "header": {"Authorization": "Bearer " + admin_jwt},
}

pprint(raw_jwt_data)

data = {"name": "My new desktop", "disk_user": True, "virt_install_id": "win10Virtio"}
## Warning, second time will throw DesktopExists exception as the name has been used already

data = {"forced_hyp": "fhy", "sample_data": 1}
print(data)
response = requests.get(
    base + "/scheduler/actions",
    json=data,
    headers=auths["isardvdi"]["header"],
    verify=False,
)
pprint(response.status_code)
pprint(response.text)
response = requests.post(
    base + "/scheduler/interval/resource_planner/0/1",
    json=data,
    headers=auths["isardvdi"]["header"],
    verify=False,
)

pprint(response.status_code)
pprint(response.text)

## virt_installs ids
# print([vi["id"] for vi in list(r.db("isard").table("virt_install").run())])
