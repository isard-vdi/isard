#!/usr/bin/python3

import sys

import requests

# If no arguments are provided, print usage
if len(sys.argv) < 3:
    print("Usage: python3 user_exists.py <username> <current_password>")
    print("Example: python3 user_exists.py admin 12345678")
    exit(1)

USERNAME = sys.argv[1]
USERNAME_PWD = sys.argv[2]

result = requests.post(
    "https://isard-portal/authentication/login?provider=form&category_id=default&username="
    + USERNAME,
    files={
        "username": (None, USERNAME),
        "password": (None, USERNAME_PWD),
    },
    timeout=5,
    verify=False,
)
if result.status_code == 200:
    print("User exists")
else:
    print("User does not exist or incorrect pwd.")
    print(f"{result.status_code}: {result.text}")
    exit(1)
