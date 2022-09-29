#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import csv
import io
import os

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from ..api_exceptions import Error
from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..api_desktops_common import ApiDesktopsCommon
from ..api_desktops_persistent import ApiDesktopsPersistent
from ..ds import DS
from ..helpers import (
    _parse_deployment_booking,
    _parse_deployment_desktop,
    _parse_string,
)

ds = DS()


def lists(user_id):
    with app.app_context():
        deployments = list(
            r.table("deployments")
            .get_all(user_id, index="user")
            .pluck(
                "id",
                "name",
                {
                    "create_dict": {
                        "tag_visible": True,
                        "template": True,
                        "name": True,
                        "description": True,
                    }
                },
            )
            .merge(
                lambda deployment: {
                    "totalDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .count(),
                    "startedDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .filter({"status": "Started"})
                    .count(),
                    "description": deployment["create_dict"]["description"],
                    "visible": deployment["create_dict"]["tag_visible"],
                    "template": r.table("domains")
                    .get(deployment["create_dict"]["template"])
                    .default({"name": False})["name"],
                    "desktop_name": deployment["create_dict"]["name"],
                }
            )
            .run(db.conn)
        )
    parsed_deployments = []
    for deployment in deployments:
        if not deployment["template"]:
            # Template does no exist anymore
            with app.app_context():
                r.table("deployments").get(deployment["id"]).delete().run(db.conn)
            continue
        parsed_deployments.append(
            {**deployment, **_parse_deployment_booking(deployment)}
        )
    return parsed_deployments


def get(deployment_id):
    with app.app_context():
        deployment = r.table("deployments").get(deployment_id).run(db.conn)
        desktops = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .pluck(
                "id",
                "user",
                "name",
                "description",
                "status",
                "icon",
                "os",
                "image",
                "persistent",
                "parents",
                "create_dict",
                "viewer",
                "guest_properties",
            )
            .run(db.conn)
        )

    parsed_desktops = []
    desktop_name = ""
    desktop_description = ""
    for desktop in desktops:
        tmp_desktop = _parse_deployment_desktop(desktop, deployment["user"])
        desktop_name = tmp_desktop.pop("name")
        desktop_description = tmp_desktop.pop("description")
        parsed_desktops.append(tmp_desktop)

    return {
        "id": deployment["id"],
        "name": deployment["name"],
        "desktop_name": desktop_name,
        "description": desktop_description,
        "desktops": parsed_desktops,
        "visible": deployment["create_dict"]["tag_visible"],
    }


def new(
    payload,
    template_id,
    name,
    description,
    desktop_name,
    selected,
    visible=False,
    skip_existing_desktops=False,
):
    # CREATE_DEPLOYMENT
    with app.app_context():
        try:
            hardware = (
                r.table("domains")
                .get(template_id)
                .pluck(
                    {
                        "create_dict": {
                            "hardware": {
                                "vcpus": True,
                                "memory": True,
                                "videos": True,
                                "disk_bus": True,
                                "interfaces": True,
                                "graphics": True,
                                "boot_order": True,
                                "qos_id": True,
                                "virtualization_nested": True,
                            }
                        }
                    }
                )
                .run(db.conn)["create_dict"]["hardware"]
            )
        except:
            raise Error(
                "not_found",
                "Template to create deployment not found",
                description_code="not_found",
            )

    deployment_tag = {
        "tag": payload["user_id"] + "=" + _parse_string(name),
        "tag_name": name,
        "tag_visible": visible,
    }
    deployment = {
        "create_dict": {
            "allowed": selected,
            "description": description,
            "hardware": hardware,
            "name": desktop_name,
            "tag": _parse_string(name),
            "tag_name": name,
            "tag_visible": visible,
            "template": template_id,
        },
        "id": payload["user_id"] + "=" + _parse_string(name),
        "name": name,
        "user": payload["user_id"],
    }

    """Check who has to be created"""
    users = []

    group_users = []

    secondary_groups_users = []
    if selected["groups"] is not False:
        with app.app_context():
            query_group_users = (
                r.table("users")
                .get_all(r.args(selected["groups"]), index="group")
                .pluck("id", "username", "category", "group")
            )
            if payload["role_id"] != "admin":
                query_group_users.filter({"category": payload["category_id"]})
            group_users = list(query_group_users.run(db.conn))

            secondary_groups_users = list(
                r.table("users")
                .get_all(r.args(selected["groups"]), index="secondary_groups")
                .pluck("id", "username", "category", "group")
                .run(db.conn)
            )
    # Add payload user if not in list
    if selected["users"]:
        if payload["user_id"] not in selected["users"]:
            selected["users"].append(payload["user_id"])
    else:
        selected["users"] = [payload["user_id"]]
    user_users = []
    with app.app_context():
        query_user_users = (
            r.table("users")
            .get_all(r.args(selected["users"]), index="id")
            .pluck("id", "username", "category", "group")
        )
        if payload["role_id"] != "admin":
            query_user_users.filter({"category": payload["category_id"]})
        user_users = list(query_user_users.run(db.conn))

    users = group_users + user_users + secondary_groups_users
    # Remove duplicate user dicts in list
    users = list({u["id"]: u for u in users}.values())

    """ DOES THE USERS ALREADY HAVE A DESKTOP WITH THIS NAME? """
    users_ids = [u["id"] for u in users]
    with app.app_context():
        try:
            existing_desktops = [
                u["user"]
                for u in list(
                    r.table("domains")
                    .get_all(r.args(users_ids), index="user")
                    .filter({"name": desktop_name})
                    .pluck("id", "user", "username")
                    .run(db.conn)
                )
            ]
        except:
            raise Error(
                "internal_server",
                "Unable to get deployment desktops",
                description_code="unable_to_get_deployment_desktops",
            )
    if len(existing_desktops):
        if not skip_existing_desktops:
            raise Error(
                "conflict",
                "This users already have a desktop with this name: "
                + str(existing_desktops),
                description_code="new_desktop_name_exists",
            )
        else:
            users = [u for u in users if u["id"] not in existing_desktops]

    """Create deployment"""
    with app.app_context():
        try:
            r.table("deployments").insert(deployment).run(db.conn)
        except:
            raise Error(
                "conflict",
                "Deployment id already exists",
                description_code="unable_to_insert",
            )

    """Create desktops for each user found"""
    for user in users:
        ApiDesktopsPersistent().NewFromTemplate(
            desktop_name,
            description,
            template_id,
            user_id=user["id"],
            deployment_tag_dict=deployment_tag,
        )
    return deployment["id"]


def delete(deployment_id):
    with app.app_context():
        deployment_domains = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .pluck("id", "status")
            .run(db.conn)
        )

    for desktop in deployment_domains:
        DS().delete_desktop(desktop["id"], desktop["status"])

    with app.app_context():
        r.table("deployments").get(deployment_id).delete().run(db.conn)


def recreate(payload, deployment_id):
    with app.app_context():
        deployment = r.table("deployments").get(deployment_id).run(db.conn)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to recreate: " + str(deployment_id),
            description_code="not_found",
        )

    new(
        payload,
        deployment["create_dict"]["template"],
        deployment["name"],
        deployment["create_dict"]["description"],
        deployment["create_dict"]["name"],
        deployment["create_dict"]["allowed"],
        deployment["create_dict"]["tag_visible"],
        skip_existing_desktops=True,
    )


def useradd(payload, deployment_id, user_id):
    with app.app_context():
        deployment = r.table("deployments").get(deployment_id).run(db.conn)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to recreate: " + str(deployment_id),
            description_code="not_found",
        )
    if deployment["allowed"]["users"]:
        deployment["allowed"]["users"].append(user_id)
    else:
        deployment["allowed"]["users"] = [user_id]
    deployment_new(
        payload,
        deployment["create_dict"]["template"],
        deployment["name"],
        deployment["create_dict"]["description"],
        deployment["create_dict"]["name"],
        deployment["allowed"],
        deployment["create_dict"]["tag_visible"],
        skip_existing_desktops=True,
    )


def start(deployment_id):
    try:
        with app.app_context():
            domains_ids = [
                d["id"]
                for d in r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id")
                .run(db.conn)
            ]
    except:
        raise Error(
            "not_found",
            "Deployment id not found: " + str(deployment_id),
            description_code="not_found",
        )

    for domain_id in domains_ids:
        try:
            ApiDesktopsPersistent().Start(domain_id)
        except:
            None


def stop(deployment_id):
    try:
        with app.app_context():
            domains_ids = [
                d["id"]
                for d in r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id")
                .run(db.conn)
            ]
    except:
        raise Error(
            "not_found",
            "Deployment id not found: " + str(deployment_id),
            description_code="not_found" + str(deployment_id),
        )

    for domain_id in domains_ids:
        try:
            ApiDesktopsPersistent().Stop(domain_id)
        except:
            None


def visible(deployment_id, stop_started_domains=True):
    try:
        with app.app_context():
            visible = (
                not r.table("deployments")
                .get(deployment_id)
                .pluck({"create_dict": {"tag_visible": True}})
                .run(db.conn)["create_dict"]["tag_visible"]
            )
        if visible:
            stop_started_domains = False
        with app.app_context():
            r.table("domains").get_all(deployment_id, index="tag").update(
                {"tag_visible": visible}
            ).run(db.conn)
            r.table("deployments").get(deployment_id).update(
                {"create_dict": {"tag_visible": visible}}
            ).run(db.conn)
    except:
        raise Error(
            "not_found",
            "Deployment id not found: " + str(deployment_id),
            description_code="not_found" + str(deployment_id),
        )

    if stop_started_domains:
        with app.app_context():
            for domain in list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id", "status")
                .run(db.conn)
            ):
                if domain["status"] == "Started":
                    try:
                        ds.WaitStatus(
                            domain["id"],
                            "Any",
                            "ShuttingDown",
                            "Stopped",
                            wait_seconds=5,
                        )
                    except:
                        try:
                            ds.WaitStatus(
                                domain["id"],
                                "Any",
                                "Stopping",
                                "Stopped",
                                wait_seconds=5,
                            )
                        except:
                            log.warning(
                                "internal_server",
                                "Unable to stop domain: " + str(domain["id"]),
                            )


def direct_viewer_csv(deployment_id):
    with app.app_context():
        ## Add jumperurl token if not there already
        domains_wo_token_ids = [
            d["id"]
            for d in list(
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id", "user", "jumperurl")
                .run(db.conn)
            )
            if not d.get("jumperurl")
        ]
        for domain_id in domains_wo_token_ids:
            ApiDesktopsCommon().gen_jumpertoken(domain_id)

        ## Get data to generate csv
        domains = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .has_fields("jumperurl")
            .pluck("id", "user", "jumperurl")
            .run(db.conn)
        )

    if not len(domains):
        return "username,name,email,url"

    users = list(
        r.table("users")
        .get_all(r.args([u["user"] for u in domains]))
        .pluck("id", "username", "name", "email")
        .run(db.conn)
    )
    result = []
    for d in domains:
        u = [u for u in users if u["id"] == d["user"]][0]
        result.append(
            {
                "username": u["username"],
                "name": u["name"],
                "email": u["email"],
                "url": "https://" + os.environ["DOMAIN"] + "/vw/" + d["jumperurl"],
            }
        )

    fieldnames = ["username", "name", "email", "url"]
    with io.StringIO() as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in result:
            writer.writerow(row)
        return csvfile.getvalue()


def jumper_url_reset(deployment_id):
    with app.app_context():
        deployment_desktops = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .pluck("id", "user", "jumperurl")
            .run(db.conn)
        )

        for deployment_desktop in deployment_desktops:
            ApiDesktopsCommon().gen_jumpertoken(deployment_desktop["id"])
