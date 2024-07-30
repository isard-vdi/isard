#!/bin/python3

# Copyright 2024 - Josep Maria Viñolas Auquer
# License: AGPLv3

# This script is a simple API client to interact with Isard-vdi API.
# python3 -m venv venv
# source venv/bin/activate
# pip install requests==2.32.3
# python api.py


import sys
import time

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


def get_categories():
    categories = requests.get(
        url=URL + "/api/v3/categories",
        timeout=10,
        verify=VERIFY_SSL,
    )
    if categories.status_code != 200:
        print(categories.text)
        exit(1)
    return categories.json()


def get_jwt():
    resp = {}
    resp = requests.post(
        URL + f"/authentication/login",
        params={"provider": "form", "category_id": CATEGORY_ID},
        files={
            "username": (None, USERNAME),
            "password": (None, PASSWORD),
        },
        timeout=10,
        verify=VERIFY_SSL,
    )
    return resp.text


def get_templates(jwt):
    return requests.get(
        url=URL + "/api/v3/user/templates/allowed/all",
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def get_user_desktops(jwt):
    return requests.get(
        url=URL + "/api/v3/user/desktops",
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def get_domain_info(jwt, domain_id):
    return requests.get(
        url=URL + "/api/v3/domain/info/" + domain_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def get_groups(jwt, term):
    return requests.post(
        url=URL + "/api/v3/admin/allowed/term/groups",
        json={"term": term},
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def get_deployment(jwt, deployment_id):
    return requests.get(
        url=URL + "/api/v3/deployment/" + deployment_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def group_users_count(
    jwt,
    groups,
):
    # groups = list of group ids
    return requests.put(
        url=URL + "/api/v3/groups_users/count",
        json={"groups": groups},
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def show_categories():
    categories = get_categories()
    print("\nCategories:")
    print("ID\tName")
    print("----\t----")
    for category in categories:
        print(f"{category['id']}\t{category['name']}")


def show_user_items():
    jwt = get_jwt()

    templates = get_templates(jwt)
    print("\nTemplates:")
    print("ID\tName\tStatus\tDescription")
    print("----\t----\t------\t-----------")
    for template in templates:
        print(
            f"{template['id']}\t{template['name']}\t{template['status']}\t{template['description']}"
        )

    desktops = get_user_desktops(jwt)
    print("\nDesktops:")
    print("ID\tName\tStatus\tDescription")
    print("----\t----\t------\t-----------")
    for desktop in desktops:
        print(
            f"{desktop['id']}\t{desktop['name']}\t{desktop['state']}\t{desktop['description']}"
        )


def new_desktop_from_template(
    jwt,
    name,
    template_id,
    description="",
    hardware=None,
    guest_properties=None,
    image=None,
):
    template_info = get_domain_info(jwt, template_id)
    hardware = hardware or template_info["hardware"]
    hardware["reservables"] = template_info.get("reservables", {"vgpus": ["None"]})
    hardware["interfaces"] = [
        i["id"] for i in template_info["hardware"].get("interfaces", ["default"])
    ]
    guest_properties = guest_properties or template_info["guest_properties"]
    # image = image or {"type": "stock"}

    desktop = requests.post(
        url=URL + "/api/v3/persistent_desktop",
        json={
            "name": name,
            "description": description,
            "template_id": template_id,
            "hardware": template_info["hardware"],
            "guest_properties": template_info["guest_properties"],
            # "image": image,
        },
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    )
    if desktop.status_code != 200:
        if desktop.status_code == 409:
            desktop_id = [d["id"] for d in get_user_desktops(jwt) if d["name"] == name][
                0
            ]
            print(
                f"Desktop {name} already exists with id {desktop_id}. Use desktop_start to start it or desktop_delete to delete it."
            )
            exit(1)
        print(desktop.text)
        exit(1)
    return desktop.json().get("id")


def desktop_status(jwt, desktop_id):
    return (
        requests.get(
            url=URL + "/api/v3/user/desktop/" + desktop_id,
            headers=({"Authorization": "Bearer " + jwt}),
            timeout=10,
            verify=VERIFY_SSL,
        )
        .json()
        .get("state")
    )


def wait_status(jwt, desktop_id, status, timeout=60):
    while timeout > 0:
        if desktop_status(jwt, desktop_id) == status:
            return True
        time.sleep(1)
        timeout -= 1
    print(f"Timeout waiting for status {status}")
    return False


def desktop_stop(jwt, desktop_id):
    return requests.get(
        url=URL + "/api/v3/desktop/stop/" + desktop_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def desktop_force_stop(jwt, desktop_id):
    desktop_stop(jwt, desktop_id)
    time.sleep(0.5)
    desktop_stop(jwt, desktop_id)


def desktop_start(jwt, desktop_id):
    return requests.get(
        url=URL + "/api/v3/desktop/start/" + desktop_id,
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def desktop_delete(jwt, desktop_id):
    return requests.delete(
        url=URL + "/api/v3/desktop/" + desktop_id + "/permanent",
        headers=({"Authorization": "Bearer " + jwt}),
        timeout=10,
        verify=VERIFY_SSL,
    ).json()


def desktop_loop_start_stop(jwt, desktop_id, loops=2):
    for i in range(loops):
        print(f"Loop {i+1}/{loops}")
        desktop_start(jwt, desktop_id)
        print("  Waiting for status Started")
        wait_status(jwt, desktop_id, "Started")
        print("  Desktop started")
        desktop_stop(jwt, desktop_id)  # Use stop or force_stop
        print("  Waiting for status Stopped")
        wait_status(jwt, desktop_id, "Stopped")
        print("  Desktop stopped")


def desktop_loop_create_start_stop_delete(jwt, desktop_name, template_id, loops=2):
    for i in range(loops):
        print(f"Loop {i+1}/{loops}")
        desktop_id = new_desktop_from_template(jwt, desktop_name, template_id)
        # We can also guess desktop id by name:
        desktop_id = [
            d["id"] for d in get_user_desktops(jwt) if d["name"] == desktop_name
        ][0]
        print(f"  Waiting for desktop to be created")
        wait_status(jwt, desktop_id, "Stopped")
        print(f"  Desktop {desktop_id} created")
        print("  Waiting for status Started")
        wait_status(jwt, desktop_id, "Started")
        print("  Desktop started")
        desktop_force_stop(jwt, desktop_id)
        print("  Waiting for status Stopped")
        wait_status(jwt, desktop_id, "Stopped")
        print("  Desktop stopped")
        desktop_delete(jwt, desktop_id)
        print(f"  Desktop {desktop_id} deleted")


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
        url=URL + "/api/v3/deployments",
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
        verify=VERIFY_SSL,
    ).json()


if __name__ == "__main__":
    # read variables from api.cfg
    with open("api.cfg") as f:
        for line in f:
            if line.startswith("URL"):
                URL = line.split("=")[1].strip()
            if line.startswith("USERNAME"):
                USERNAME = line.split("=")[1].strip()
            if line.startswith("PASSWORD"):
                PASSWORD = line.split("=")[1].strip()
            if line.startswith("CATEGORY_NAME"):
                CATEGORY_NAME = line.split("=")[1].strip()
            if line.startswith("CATEGORY_ID"):
                CATEGORY_ID = line.split("=")[1].strip()
            if line.startswith("VERIFY_SSL"):
                VERIFY_SSL = line.split("=")[1].strip()
                if VERIFY_SSL == "True":
                    VERIFY_SSL = True
                else:
                    VERIFY_SSL = False
    print(f"          URL: {URL}")
    print(f"     USERNAME: {USERNAME}")
    print(f"   VERIFY_SSL: {VERIFY_SSL}")
    print(f"CATEGORY_NAME: {CATEGORY_NAME}")

    if CATEGORY_ID == "False":
        categories = get_categories()
        for category in categories:
            if category["name"] == CATEGORY_NAME:
                CATEGORY_ID = category["id"]
                print(
                    f"  CATEGORY_ID: {CATEGORY_ID} (Guessed from category name {CATEGORY_NAME})"
                )
    else:
        print(f"  CATEGORY_ID: {CATEGORY_ID}")

    if CATEGORY_ID == "False":
        print(
            "\n ERROR!\nCATEGORY_ID could not be guessed from CATEGORY_NAME. This are shown categories:"
        )
        show_categories()
        exit(1)

    if len(sys.argv) < 2:
        show_user_items()
        print("\nAvailable commands:")
        print("- show")
        print("- desktop status <desktop_id>")
        print("- desktop stop <desktop_id>")
        print("- desktop force_stop <desktop_id>")
        print("- desktop start <desktop_id>")
        print("- desktop delete <desktop_id>")
        print("- desktop loop_start_stop <desktop_id> <loops>")
        print(
            "- desktop loop_create_start_stop_delete <desktop_name> <template_id> <loops>"
        )

        exit(0)

    if sys.argv[1] == "desktop":
        if sys.argv[2] == "status":
            jwt = get_jwt()
            print(desktop_status(jwt, sys.argv[3]))
            exit(0)
        if sys.argv[2] == "stop":
            jwt = get_jwt()
            desktop_stop(jwt, sys.argv[3])
            exit(0)
        if sys.argv[2] == "delete":
            jwt = get_jwt()
            desktop_delete(jwt, sys.argv[3])
            exit(0)
        if sys.argv[2] == "force_stop":
            jwt = get_jwt()
            desktop_force_stop(jwt, sys.argv[3])
            exit(0)
        if sys.argv[2] == "start":
            jwt = get_jwt()
            desktop_start(jwt, sys.argv[3])
            exit(0)
        if sys.argv[2] == "loop_start_stop":
            jwt = get_jwt()
            desktop_loop_start_stop(jwt, sys.argv[3], int(sys.argv[4]))
            exit(0)
        if sys.argv[2] == "loop_create_start_stop_delete":
            jwt = get_jwt()
            desktop_loop_create_start_stop_delete(
                jwt, sys.argv[3], sys.argv[4], int(sys.argv[5])
            )
            exit(0)
