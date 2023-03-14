import json
import time
from datetime import datetime, timedelta
from pprint import pprint

import requests
from jose import jwt
from rethinkdb import r

domain = "localhost"
verifycert = False
## End set global vars


auths = {}
dbconn = None
base = "http://isard-api:5000/api/v3"
dbconn = r.connect("isard-db", 28015, "isard").repl()

admin_secret_data = r.db("isard").table("secrets").get("isardvdi").run()
raw_jwt_data = {
    "exp": datetime.utcnow() + timedelta(minutes=5),
    "kid": admin_secret_data["id"],
    "data": {
        "role_id": admin_secret_data["role_id"],
        "category_id": admin_secret_data["category_id"],
        "user_id": "local-default-admin-admin",
        "group_id": "default-default",
    },
}
admin_jwt = jwt.encode(raw_jwt_data, admin_secret_data["secret"], algorithm="HS256")
auths["isardvdi"] = {
    "secret": admin_secret_data,
    "jwt": admin_jwt,
    "header": {"Authorization": "Bearer " + admin_jwt},
}

### GET USERS
response = requests.get(
    base + "/admin/users",
    json={},
    headers=auths["isardvdi"]["header"],
    verify=False,
)
if response.status_code == 200:
    pprint([d["id"] for d in json.loads(response.text)])


### GET DOMAINS
response = requests.get(
    base + "/admin/table/domains",
    json={},
    headers=auths["isardvdi"]["header"],
    verify=False,
)
print("Domains in system status code:" + str(response.status_code))
if response.status_code == 200:
    pprint([d["id"] for d in json.loads(response.text)])

### GET DOWNLOADS
response = requests.get(
    base + "/admin/downloads/domains",
    json={},
    headers=auths["isardvdi"]["header"],
    verify=False,
)
print("Domains in downloads status code:" + str(response.status_code))
if response.status_code == 200:
    pprint([d["id"] for d in json.loads(response.text)])

### GET DOWNLOAD FOR TETROS
response = requests.post(
    base
    + "/admin/downloads/download/domains/_local-default-admin-admin_downloaded_tetros",
    json={},
    headers=auths["isardvdi"]["header"],
    verify=False,
)
print(
    "Downloading _local-default-admin-admin_downloaded_tetros status code:"
    + str(response.status_code)
)
if response.status_code == 200:
    pprint([d["id"] for d in json.loads(response.text)])
