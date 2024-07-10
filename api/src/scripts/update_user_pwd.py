#!/usr/bin/python3
import pprint
import sys

import requests

# If no arguments are provided, print usage
if len(sys.argv) < 4:
    print(
        'Usage: python3 update_user_pwd.py <username> <current_password> <new_password> "<URL_BASE>"'
    )
    print(
        'Example: python3 update_user_pwd.py admin 12345678 87654321 "https://localhost"'
    )
    print(
        "NOTE: If running against localhost, you may need to disable SSL verification"
    )
    exit(1)

USERNAME = sys.argv[1]
USERNAME_PWD = sys.argv[2]
USERNAME_PWD_NEW = sys.argv[3]
URL_BASE = sys.argv[4]

result = requests.put(
    json={"current_password": USERNAME_PWD, "password": USERNAME_PWD_NEW},
    url=URL_BASE + f"/api/v3/user",
    headers=(
        {
            "Authorization": "Bearer "
            + requests.post(
                URL_BASE
                + f"/authentication/login?provider=form&category_id=default&username="
                + USERNAME,
                files={
                    "username": (None, USERNAME),
                    "password": (None, USERNAME_PWD),
                },
                timeout=5,
                verify=True,
            ).text
        }
    ),
    timeout=10,
    verify=True,
)
if result.status_code == 200:
    print("Password changed successfully")
else:
    print(f"{result.status_code}: Error changing password")
    pprint.pprint(result.text)
    exit(1)
