#!/bin/python3
import json
import pprint
import sys
from pprint import pprint

import requests

if len(sys.argv) < 4:
    print(
        'Usage: python3 create_desktop.py <username> <current_password> <category_id> "<URL_BASE>"'
    )
    print('Example: python3 create_desktop.py admin 12345678 "https://localhost"')
    print(
        "NOTE: If running against localhost, you may need to disable SSL verification"
    )
    exit(1)

USERNAME = sys.argv[1]
USERNAME_PWD = sys.argv[2]
CATEGORY = sys.argv[3]
URL_BASE = sys.argv[4]


def get_jwt(username, password, category):
    resp = {}
    resp = requests.post(
        URL_BASE + f"/authentication/login",
        params={"provider": "form", "category_id": category},
        files={
            "username": (None, username),
            "password": (None, password),
        },
        timeout=10,
        verify=True,
    )
    return resp.text


def get_templates(jwt):
    return requests.get(
        url=URL_BASE + "/api/v3/user/templates/allowed/all",
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


def get_domain_info(jwt, domain_id):
    return requests.get(
        url=URL_BASE + "/api/v3/domain/info/" + domain_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


def get_groups(jwt, term):
    return requests.post(
        url=URL_BASE + "/api/v3/admin/allowed/term/groups",
        json={"term": term},
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


def new_deployment(
    jwt,
    name,
    template_id,
    allowed,
    hardware,
    guest_properties,
    desktop_name=None,
    visible=None,
    image=None,
    description=None,
):
    return requests.post(
        url=URL_BASE + "/api/v3/deployments",
        json={
            "name": name,
            "template_id": template_id,
            "allowed": allowed,
            "desktop_name": desktop_name,
            "hardware": hardware,
            "guest_properties": guest_properties,
            "image": image,
        },
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


def get_deployment(jwt, deployment_id):
    return requests.get(
        url=URL_BASE + "/api/v3/deployment/" + deployment_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


def group_users_count(
    jwt,
    groups,
):
    # groups = list of group ids
    return requests.put(
        url=URL_BASE + "/api/v3/groups_users/count",
        json={"groups": groups},
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=True,
    ).json()


jwt = get_jwt(USERNAME, USERNAME_PWD, CATEGORY)
template = get_templates(jwt)[0]
template_info = get_domain_info(jwt, template["id"])
groups = [get_groups(jwt, term="default")[0]]
groups_ids = [group["id"] for group in groups]
desktops_to_be_created = group_users_count(jwt, groups_ids)["quantity"]

print(
    f"Creating {desktops_to_be_created} desktops from template {template_info['name']}, groups: {[group['name'] for group in groups]}"
)

hardware = template_info["hardware"]
hardware["reservables"] = template_info.get("reservables", {"vgpus": ["None"]})
hardware["interfaces"] = [
    i["id"] for i in template_info["hardware"].get("interfaces", ["default"])
]
deployment_id = new_deployment(
    jwt,
    name="Test deployment",
    template_id=template["id"],
    desktop_name="Test desktop",
    allowed={"users": False, "groups": groups_ids},
    hardware=hardware,
    guest_properties=template_info["guest_properties"],
    image={"type": "stock"},
)["id"]

print(deployment_id)

print(f"Deployment created with id {deployment_id}")

pprint(get_deployment(jwt, deployment_id))
