#!/usr/bin/python3

import json
import pprint
import sys

import requests

if len(sys.argv) < 4:
    print("Usage: python3 new_user.py <username> <current_password> <new_user_json>")
    print(
        'Example: python3 new_user.py admin 12345678 \'{"name": "IsardVDI Admin","email": "info@isardvdi.com","role": "admin","category": "default","group": "default-default","password": "12345678","provider": "local","bulk": false,"username": "isardvdi-admin"}\''
    )
    exit(1)

USERNAME = sys.argv[1]
USERNAME_PWD = sys.argv[2]
NEW_USERNAME = json.loads(sys.argv[3])

result = requests.post(
    json=NEW_USERNAME,
    url="https://isard-portal/api/v3/admin/user",
    headers=(
        {
            "Authorization": "Bearer "
            + requests.post(
                "https://isard-portal/authentication/login?provider=form&category_id=default&username="
                + USERNAME,
                files={
                    "username": (None, USERNAME),
                    "password": (None, USERNAME_PWD),
                },
                timeout=5,
                verify=False,
            ).text
        }
    ),
    verify=False,
)
if result.status_code == 200:
    print("User created successfully")
else:
    print(f"{result.status_code}: Error creating user")
    pprint.pprint(result.text)
    exit(1)
