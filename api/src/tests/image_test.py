import base64
import json
from datetime import datetime, timedelta
from pprint import pprint

import requests
from jose import jwt
from rethinkdb import r

base = "http://localhost:5000/api/v3/"
image_file = "sample_image.png"

r.connect("isard-db", 28015).repl()


def get_admin_jwt():
    admin_secret_data = r.db("isard").table("secrets").get("isardvdi").run()
    admin_jwt = jwt.encode(
        {
            "exp": datetime.utcnow() + timedelta(hours=4),
            "kid": admin_secret_data["id"],
            "data": {
                "role_id": admin_secret_data["role_id"],
                "category_id": admin_secret_data["category_id"],
            },
        },
        admin_secret_data["secret"],
        algorithm="HS256",
    )

    return {
        "secret": admin_secret_data,
        "jwt": admin_jwt,
        "header": {"Authorization": "Bearer " + admin_jwt},
    }


def get_users():
    return list(r.db("isard").table("users").run())


def get_user_jwt(header, user_id):
    response = requests.get(
        base + "/admin/jwt/" + user_id,
        headers=header,
        verify=False,
    )
    return json.loads(response.text)


admin_header = get_admin_jwt()["header"]
users = get_users()

for user in users:
    print("ACTUAL USER: " + user["id"])
    pprint(get_user_jwt(admin_header, user["id"]))
exit(1)

with open(image_file, "rb") as f:
    im_bytes = f.read()
im_b64 = base64.b64encode(im_bytes).decode("utf8")

headers = {"Content-type": "application/json", "Accept": "text/plain"}

payload = json.dumps({"image": im_b64, "other_key": "value"})
response = requests.post(api, data=payload, headers=headers)
try:
    data = response.json()
    print(data)
except requests.exceptions.RequestException:
    print(response.text)
