#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import csv
import io
import os

from api.libv2.quotas import Quotas
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from ..._common.api_exceptions import Error
from ..flask_rethink import RDB

quotas = Quotas()


db = RDB(app)
db.init_app(app)

from api.libv2.quotas import Quotas

from ..api_desktop_events import desktops_delete, desktops_stop
from ..api_desktops_common import ApiDesktopsCommon
from ..api_desktops_persistent import ApiDesktopsPersistent
from ..bookings.api_booking import Bookings
from ..ds import DS
from ..helpers import (
    _check,
    _parse_deployment_booking,
    _parse_deployment_desktop,
    _parse_string,
    parse_domain_insert,
)
from ..validators import _validate_item

apib = Bookings()

quotas = Quotas()

ds = DS()


def lists(user_id):
    with app.app_context():
        deployments = list(
            r.table("deployments")
            .get_all(user_id, index="user")
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
            .without("create_dict")
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


def get(deployment_id, desktops=True):
    with app.app_context():
        deployment = (
            r.table("deployments")
            .get(deployment_id)
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
            .without("create_dict")
            .run(db.conn)
        )

    deployment = {
        **deployment,
        **_parse_deployment_booking(deployment),
    }

    if desktops:
        parsed_desktops = []
        desktops = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .pluck(
                "id",
                "user",
                "group",
                "category",
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
                "accessed",
                "tag",
                "booking_id",
                "tag_visible",
            )
            .merge(
                lambda domain: {
                    "user_name": r.table("users").get(domain["user"])["name"],
                    "user_photo": r.table("users")
                    .get(domain["user"])["photo"]
                    .default(None),
                    "category_name": r.table("categories").get(domain["category"])[
                        "name"
                    ],
                    "group_name": r.table("groups").get(domain["group"])["name"],
                }
            )
            .run(db.conn)
        )
        for desktop in desktops:
            tmp_desktop = _parse_deployment_desktop(desktop, deployment["user"])
            parsed_desktops.append(tmp_desktop)
        deployment["desktops"] = parsed_desktops

    return deployment


def new(
    payload,
    template_id,
    name,
    description,
    desktop_name,
    selected,
    new_data,
    deployment_id,
    visible=False,
):
    # CREATE_DEPLOYMENT
    new_data["hardware"] = parse_domain_insert(new_data)["hardware"]
    new_data["hardware"]["memory"] = new_data["hardware"]["memory"] * 1048576
    new_data["reservables"] = new_data["hardware"].pop("reservables")
    deployment = {
        "create_dict": {
            "allowed": selected,
            "description": description,
            "hardware": new_data.get("hardware"),
            "reservables": new_data.get("reservables"),
            "guest_properties": new_data.get("guest_properties"),
            "name": desktop_name,
            "tag": deployment_id,
            "tag_name": name,
            "tag_visible": visible,
            "template": template_id,
            "image": new_data.get("image"),
        },
        "id": deployment_id,
        "name": name,
        "user": payload["user_id"],
    }

    users = get_selected_users(payload, selected, desktop_name, False)
    quotas.deployment_create(users)

    """Create deployment"""
    with app.app_context():
        query = r.table("deployments").insert(deployment).run(db.conn)
        if not _check(query, "inserted"):
            raise Error(
                "internal_server",
                "Unable to create deployment",
                description_code="unable_to_insert",
            )

    """Create desktops for each user found"""
    deployment_tag = {
        "tag": deployment_id,
        "tag_name": name,
        "tag_visible": visible,
    }
    desktop = {
        "name": desktop_name,
        "description": description,
        "template_id": template_id,
        "hardware": {
            **deployment["create_dict"]["hardware"],
            "memory": deployment["create_dict"]["hardware"]["memory"] / 1048576,
            "reservables": new_data.get("reservables"),
        },
        "guest_properties": deployment["create_dict"]["guest_properties"],
        "image": deployment["create_dict"]["image"],
    }
    create_deployment_desktops(deployment_tag, desktop, users)

    return deployment["id"]


def get_selected_users(payload, selected, desktop_name, skip_existing_desktops):
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
    return users


def create_deployment_desktops(deployment_tag, desktop_data, users):
    for user in users:

        desktop = _validate_item("desktop_from_template", desktop_data)

        ApiDesktopsPersistent().NewFromTemplate(
            desktop["name"],
            desktop["description"],
            desktop["template_id"],
            user_id=user["id"],
            deployment_tag_dict=deployment_tag,
            domain_id=desktop["id"],
            new_data=desktop,
            image=desktop.get("image"),
        )


def checkDesktopsStarted(deployment_id):
    with app.app_context():
        started_desktops = (
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .filter(
                lambda desktop: r.not_(
                    r.expr(["Stopped", "Failed", "Unknown"]).contains(desktop["status"])
                )
            )
            .count()
            .run(db.conn)
        )
    if started_desktops > 0:
        raise Error(
            "precondition_required",
            "The deployment " + str(deployment_id) + " desktops must be stopped ",
            description_code="deployment_delete_stop",
        )


def delete(deployment_id):
    with app.app_context():
        r.table("domains").get_all(deployment_id, index="tag").update(
            {"status": "ForceDeleting"}
        ).run(db.conn)
        apib.delete_item_bookings("deployment", deployment_id)
        if (
            not r.table("domains")
            .get_all(deployment_id, index="tag")
            .count()
            .run(db.conn)
        ):
            r.table("deployments").get(deployment_id).delete().run(db.conn)
        else:
            r.table("deployments").get(deployment_id).update(
                {"status": "deleting"}
            ).run(db.conn)


def recreate(payload, deployment_id):
    with app.app_context():
        deployment = r.table("deployments").get(deployment_id).run(db.conn)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to recreate: " + str(deployment_id),
            description_code="not_found",
        )

    users = get_selected_users(
        payload,
        deployment["create_dict"]["allowed"],
        deployment["create_dict"]["name"],
        True,
    )

    """Create desktops for each user found"""
    desktop = {
        "name": deployment["create_dict"]["name"],
        "description": deployment["create_dict"]["description"],
        "template_id": deployment["create_dict"]["template"],
        "hardware": {
            **deployment["create_dict"]["hardware"],
            "memory": deployment["create_dict"]["hardware"]["memory"] / 1048576,
        },
    }
    # Get from the deployment, otherwise it will be fetched from its template
    if deployment["create_dict"].get("guest_properties"):
        desktop["guest_properties"] = deployment["create_dict"]["guest_properties"]
    if deployment["create_dict"].get("reservables"):
        desktop["hardware"]["reservables"] = deployment["create_dict"]["reservables"]
    if deployment["create_dict"].get("image"):
        desktop["image"] = deployment["create_dict"]["image"]

    deployment_tag = {
        "tag": deployment_id,
        "tag_name": deployment["create_dict"]["name"],
        "tag_visible": deployment["create_dict"]["tag_visible"],
    }
    create_deployment_desktops(deployment_tag, desktop, users)


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

    desktops_stop(domains_ids, force=True, wait_seconds=30)


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
            desktops_ids = list(
                r.table("domains")
                .get_all(deployment_id, index="tag")["id"]
                .run(db.conn)
            )
            desktops_stop(desktops_ids, force=True, wait_seconds=5)


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
