#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import copy
import csv
import io
import logging as log
import os
import time
import traceback
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from api.libv2.quotas import Quotas
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from api.libv2.caches import (
    get_cached_deployment_desktops,
    get_document,
    invalidate_cache,
)
from isardvdi_common.api_exceptions import Error

from ..flask_rethink import RDB

quotas = Quotas()


db = RDB(app)
db.init_app(app)

from api.libv2.api_allowed import ApiAllowed

alloweds = ApiAllowed()


from api.libv2.quotas import Quotas

from ..api_desktop_events import deployment_delete_desktops, desktops_stop
from ..api_desktops_common import ApiDesktopsCommon
from ..api_desktops_persistent import ApiDesktopsPersistent
from ..bookings.api_booking import Bookings
from ..helpers import (
    _check,
    _parse_deployment_booking,
    _parse_deployment_desktop,
    change_owner_deployments,
    gen_payload_from_user,
    get_new_user_data,
    parse_domain_insert,
    parse_domain_update,
)
from ..rules import get_unused_item_timeout
from ..validators import _validate_item

apib = Bookings()

quotas = Quotas()


def lists(user_id):
    with app.app_context():
        deployments_owner = list(
            r.table("deployments")
            .get_all(user_id, index="user")
            .merge(
                lambda deployment: {
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
    with app.app_context():
        deployments_coowners = list(
            r.table("deployments")
            .get_all(user_id, index="co_owners")
            .merge(
                lambda deployment: {
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
    deployments = deployments_owner + deployments_coowners

    for deployment in deployments:
        deployment_desktops = get_cached_deployment_desktops(deployment["id"])

        deployment["totalDesktops"] = len(deployment_desktops)
        deployment["visibleDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["tag_visible"] is True
            ]
        )
        deployment["startedDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["status"]
                in [
                    "Started",
                    "Starting",
                    "StartingPaused",
                    "CreatingAndStarting",
                    "Shutting-down",
                ]
            ]
        )
        deployment["creatingDesktops"] = len(
            [
                desktop
                for desktop in deployment_desktops
                if desktop["status"]
                in [
                    "Creating",
                    "CreatingAndStarting",
                ]
            ]
        )

    deployments.sort(key=lambda x: x["name"].lower(), reverse=True)

    parsed_deployments = []
    for deployment in deployments:
        if not deployment["template"]:
            # Template does no exist anymore
            with app.app_context():
                r.table("deployments").get(deployment["id"]).delete().run(db.conn)
                invalidate_cache("deployments", deployment["id"])
            continue
        parsed_deployments.append(
            {**deployment, **_parse_deployment_booking(deployment)}
        )
    return parsed_deployments


def get(deployment_id, desktops=True):
    deployment = get_document("deployments", deployment_id)
    if deployment is None:
        raise Error(
            "not_found",
            "Deployment id not found: " + str(deployment_id),
            description_code="not_found",
        )
    deployment_desktops = get_cached_deployment_desktops(deployment_id)
    deployment["totalDesktops"] = len(deployment_desktops)
    deployment["visibleDesktops"] = len(
        [desktop for desktop in deployment_desktops if desktop["tag_visible"] is True]
    )
    deployment["startedDesktops"] = len(
        [
            desktop
            for desktop in deployment_desktops
            if desktop["status"]
            in [
                "Started",
                "Starting",
                "StartingPaused",
                "CreatingAndStarting",
                "Shutting-down",
            ]
        ]
    )
    deployment["creatingDesktops"] = len(
        [
            desktop
            for desktop in deployment_desktops
            if desktop["status"]
            in [
                "Creating",
                "CreatingAndStarting",
            ]
        ]
    )
    deployment["description"] = deployment.get("create_dict", {}).get("description")
    deployment["visible"] = deployment.get("create_dict", {}).get("tag_visible")
    deployment["desktop_name"] = deployment.get("create_dict", {}).get("name")
    deployment["template"] = get_document(
        "domains", deployment.get("create_dict", {}).get("template"), ["name"]
    )
    del deployment["create_dict"]

    deployment = {
        **deployment,
        **_parse_deployment_booking(deployment),
    }

    if desktops:
        parsed_desktops = []
        with app.app_context():
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
                .run(db.conn)
            )

        for desktop in desktops:
            desktop["user_name"] = get_document("users", desktop["user"], ["name"])
            desktop["user_photo"] = get_document("users", desktop["user"], ["photo"])
            desktop["category_name"] = get_document(
                "categories", desktop["category"], ["name"]
            )
            desktop["group_name"] = get_document("groups", desktop["group"], ["name"])

            tmp_desktop = _parse_deployment_desktop(desktop)
            parsed_desktops.append(tmp_desktop)
        deployment["desktops"] = parsed_desktops

    return deployment


def get_deployment_info(deployment_id):
    create_dict = get_document("deployments", deployment_id, ["create_dict"])
    template = get_document(
        "domains", create_dict["template"], ["create_dict", "guest_properties", "image"]
    )

    template["hardware"] = template["create_dict"].pop("hardware")
    template.pop("create_dict")
    template["guest_properties"] = template.pop("guest_properties")
    template["image"] = template.pop("image")
    template.update(create_dict)
    if "isos" in create_dict["hardware"]:
        isos = create_dict["hardware"]["isos"]
        create_dict["hardware"]["isos"] = []
        # Loop instead of a get_all query to keep the isos array order
        for iso in isos:
            create_dict["hardware"]["isos"].append(
                get_document("media", iso["id"], ["id", "name"])
            )
    if "floppies" in create_dict["hardware"]:
        with app.app_context():
            create_dict["hardware"]["floppies"] = list(
                r.table("media")
                .get_all(
                    r.args([i["id"] for i in create_dict["hardware"]["floppies"]]),
                    index="id",
                )
                .pluck("id", "name")
                .run(db.conn)
            )

    create_dict["hardware"]["interfaces"] = [
        {"id": i, "mac": ""} for i in create_dict["hardware"]["interfaces"]
    ]
    create_dict["hardware"]["memory"] = create_dict["hardware"]["memory"] / 1048576
    create_dict["id"] = deployment_id
    create_dict["allowed"] = alloweds.get_allowed(create_dict.get("allowed"))
    return create_dict


def new(
    payload,
    template_id,
    name,
    description,
    desktop_name,
    selected,
    new_data,
    deployment_id,
    co_owners=[],
    visible=False,
    user_permissions=[],
):
    # CREATE_DEPLOYMENT
    new_data["hardware"] = parse_domain_insert(new_data)["hardware"]
    new_data["hardware"]["interfaces"] = [
        i["id"] for i in new_data["hardware"].get("interfaces", {})
    ]
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
        "co_owners": co_owners,
        "user_permissions": user_permissions,
    }

    users = get_selected_users(payload, selected, desktop_name, False, True)
    quotas.deployment_create(users, payload["user_id"])

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


def get_selected_users(
    payload,
    selected,
    desktop_name,
    deployment_id=None,
    existing_desktops_error=False,
    include_existing_desktops=False,
):
    """Check who has to be created"""
    users = []

    group_users = []

    secondary_groups_users = []
    if selected["groups"] is not False:
        query_group_users = (
            r.table("users")
            .get_all(r.args(selected["groups"]), index="group")
            .filter(lambda user: user["active"].eq(True))
            .pluck("id", "username", "category", "group")
        )
        if payload["role_id"] != "admin":
            query_group_users.filter({"category": payload["category_id"]})
        with app.app_context():
            group_users = list(query_group_users.run(db.conn))

        with app.app_context():
            secondary_groups_users = list(
                r.table("users")
                .get_all(r.args(selected["groups"]), index="secondary_groups")
                .filter(lambda user: user["active"].eq(True))
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
            .filter(lambda user: user["active"].eq(True))
            .pluck("id", "username", "category", "group")
        )
    if payload["role_id"] != "admin":
        query_user_users.filter({"category": payload["category_id"]})
    with app.app_context():
        user_users = list(query_user_users.run(db.conn))

    users = group_users + user_users + secondary_groups_users
    # Remove duplicate user dicts in list
    users = list({u["id"]: u for u in users}.values())

    """ DOES THE USERS ALREADY HAVE A DESKTOP WITH THIS NAME? """
    users_ids = [u["id"] for u in users]
    with app.app_context():
        existing_desktops = [
            u["user"]
            for u in list(
                r.table("domains")
                .get_all(r.args(users_ids), index="user")
                .filter({"name": desktop_name, "tag": deployment_id})
                .pluck("id", "user", "username")
                .run(db.conn)
            )
        ]
    if len(existing_desktops):
        if existing_desktops_error:
            raise Error(
                "conflict",
                "This users already have a desktop with this name: "
                + str(existing_desktops),
                description_code="new_desktop_name_exists",
            )
        elif not include_existing_desktops:
            users = [u for u in users if u["id"] not in existing_desktops]
    return users


def create_deployment_desktops(deployment_tag, desktop_data, users):
    desktops = []
    for user in users:
        desktop = _validate_item("desktop_from_template", desktop_data)
        domain_id = str(uuid4())
        desktops.append(
            {
                "name": desktop["name"],
                "description": desktop["description"],
                "template_id": desktop["template_id"],
                "hardware": desktop["hardware"],
                "guest_properties": desktop.get("guest_properties"),
                "image": desktop.get("image"),
                "user_id": user["id"],
                "deployment_tag_dict": deployment_tag,
                "domain_id": domain_id,
                "new_data": desktop,
                "image": desktop.get("image"),
            }
        )
    deployment = get_document("deployments", deployment_tag["tag"])
    ApiDesktopsPersistent().new_from_templateTh(desktops, deployment)


def edit_deployment_users(payload, deployment_id, allowed):
    deployment = get_document("deployments", deployment_id)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to edit its users: " + str(deployment_id),
            description_code="not_found",
        )

    deployment_booking = _parse_deployment_booking(deployment)
    if deployment_booking.get("next_booking_end"):
        raise Error(
            "precondition_required",
            "Can't edit a deployment with a scheduled booking",
            traceback.format_exc(),
            "cant_edit_booked_deployment",
        )
    with app.app_context():
        r.table("deployments").get(deployment_id).update(
            {"create_dict": {"allowed": allowed}}
        ).run(db.conn)
    invalidate_cache("deployments", deployment_id)

    old_users = get_selected_users(
        payload,
        deployment.get("create_dict").get("allowed"),
        deployment.get("create_dict").get("name"),
        False,
        True,
    )
    new_users = get_selected_users(
        payload,
        allowed,
        deployment.get("create_dict").get("name"),
        existing_desktops_error=False,
        include_existing_desktops=True,
    )

    desktops_ids = []
    for user in old_users:
        if user not in new_users:
            with app.app_context():
                domain_id = (
                    r.table("domains")
                    .get_all(
                        ["desktop", user["id"], deployment_id], index="kind_user_tag"
                    )
                    .pluck("id")["id"]
                    .nth(0)
                    .default(None)
                    .run(db.conn)
                )
            if domain_id:
                desktops_ids.append(domain_id)
    if len(desktops_ids):
        deployment_delete_desktops(payload["user_id"], desktops_ids, True)
    recreate(payload, deployment_id)


def edit_deployment(payload, deployment_id, data):
    deployment = get_document("deployments", deployment_id)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to edit: " + str(deployment_id),
            description_code="not_found",
        )
    data["tag_name"] = data.get("name")
    data["name"] = data.pop("desktop_name")
    data["reservables"] = data.get("hardware").pop("reservables")
    data["hardware"]["memory"] = data["hardware"]["memory"] * 1048576
    deployment_booking = _parse_deployment_booking(deployment)
    get_selected_users(
        payload,
        deployment["create_dict"].get("allowed"),
        data.get("name"),
        existing_desktops_error=False,
        include_existing_desktops=True,
    )
    if data.get("reservables") != deployment["create_dict"].get(
        "reservables"
    ) and deployment_booking.get("next_booking_end"):
        raise Error(
            "precondition_required",
            "Can't edit a deployment with a scheduled booking",
            traceback.format_exc(),
            "cant_edit_booked_deployment",
        )
    if data["reservables"].get("vgpus") == ["None"]:
        data["reservables"]["vgpus"] = None
    user_permissions = data.pop("user_permissions")
    with app.app_context():
        r.table("deployments").get(deployment_id).update(
            {
                "create_dict": {
                    **data,
                    "guest_properties": r.literal(data["guest_properties"]),
                },
                "name": data["tag_name"],
                "user_permissions": user_permissions,
            }
        ).run(db.conn)
    invalidate_cache("deployments", deployment_id)
    # If the networks have changed new macs should be generated for each domain
    if (
        deployment["create_dict"]["hardware"]["interfaces"]
        != data["hardware"]["interfaces"]
    ):
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all(deployment_id, index="tag")
                .pluck("id")["id"]
                .run(db.conn)
            )
        deployment_interfaces = data["hardware"]["interfaces"]
        data["hardware"]["memory"] = data["hardware"]["memory"] / 1048576
        for domain in domains:
            domain_data = copy.deepcopy(data)
            domain_update = parse_domain_update(domain, domain_data)
            with app.app_context():
                r.table("domains").get(domain).update(
                    {
                        "status": "Updating",
                        "create_dict": {
                            "hardware": domain_update["create_dict"]["hardware"],
                            "reservables": r.literal(data.get("reservables")),
                        },
                        "name": data["name"],
                        "description": data["description"],
                        "guest_properties": data.get("guest_properties"),
                        "image": data["image"],
                    }
                ).run(db.conn)
            invalidate_cache("domains", domain)
            data["hardware"]["interfaces"] = deployment_interfaces

    # Otherwise the rest of the hardware can be updated at once
    else:
        data["hardware"].pop("interfaces")
        with app.app_context():
            r.table("domains").get_all(deployment_id, index="tag").update(
                {
                    "status": "Updating",
                    "create_dict": {
                        "hardware": data["hardware"],
                        "reservables": r.literal(data.get("reservables")),
                    },
                    "name": data["name"],
                    "description": data["description"],
                    "guest_properties": r.literal(data["guest_properties"]),
                    "image": data["image"],
                }
            ).run(db.conn)


def check_desktops_started(deployment_id):
    with app.app_context():
        started_desktops = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .filter(
                lambda desktop: r.not_(
                    r.expr(["Stopped", "Failed", "Unknown"]).contains(desktop["status"])
                )
            )
            .pluck("status")
            .run(db.conn)
        )
    if len(started_desktops) > 0:
        raise Error(
            "precondition_required",
            "The deployment " + str(deployment_id) + " desktops must be stopped ",
            description_code="deployment_stop",
        )
    if any([desktop["status"].startswith("Creating") for desktop in started_desktops]):
        raise Error(
            "precondition_required",
            "The deployment " + str(deployment_id) + " desktops are being created",
            description_code="deployment_stop",
        )


def delete(deployment_id):
    with app.app_context():
        r.table("domains").get_all(deployment_id, index="tag").update(
            {"status": "ForceDeleting"}
        ).run(db.conn)

    apib.delete_item_bookings("deployment", deployment_id)
    with app.app_context():
        deployment_domains_count = (
            r.table("domains").get_all(deployment_id, index="tag").count().run(db.conn)
        )
    if not deployment_domains_count:
        with app.app_context():
            r.table("deployments").get(deployment_id).delete().run(db.conn)
    else:
        with app.app_context():
            r.table("deployments").get(deployment_id).update(
                {"status": "deleting"}
            ).run(db.conn)
        invalidate_cache("deployments", deployment_id)


def recreate(payload, deployment_id):
    deployment = get_document("deployments", deployment_id)
    if not deployment:
        raise Error(
            "not_found",
            "Not found deployment id to recreate: " + str(deployment_id),
            description_code="not_found",
        )
    # If the deployment has bookings check if the new deployment can be recreated considering the booked units
    deployment_booking = _parse_deployment_booking(deployment)
    if deployment_booking.get("next_booking_end"):
        check_deployment_bookings(payload, deployment)

    users = get_selected_users(
        payload,
        deployment["create_dict"]["allowed"],
        deployment["create_dict"]["name"],
        deployment["id"],
        existing_desktops_error=False,
        include_existing_desktops=False,
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


def check_deployment_bookings(payload, deployment):
    with app.app_context():
        deployment_bookings = list(
            r.table("bookings")
            .get_all(deployment["id"], index="item_id")
            .filter(lambda booking: booking["end"].gt(r.now()))
            .run(db.conn)
        )

    deployment_users = get_selected_users(
        payload,
        deployment["create_dict"]["allowed"],
        deployment["create_dict"]["name"],
        deployment["id"],
        existing_desktops_error=False,
        include_existing_desktops=True,
    )

    for booking in deployment_bookings:
        if booking["units"] < len(deployment_users):
            raise Error(
                "precondition_required",
                f'The deployment {deployment["id"]} has a future booking ({booking["start"]} - {booking["end"]}) with only {booking["units"]} units booked and recreating would require {len(deployment_users)} units',
                description_code="deployment_recreate_booking_not_enough_units",
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

    desktops_stop(domains_ids, force=True)


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
        invalidate_cache("deployments", deployment_id)
        with app.app_context():
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
            desktops_stop(desktops_ids, force=True)


def user_visible(id):
    with app.app_context():
        query = r.table("domains").get(id).pluck("user", "tag_visible").run(db.conn)
    result = dict(query)

    update_query = (
        r.table("domains").get(id).update({"tag_visible": not result["tag_visible"]})
    )
    with app.app_context():
        update_query.run(db.conn)


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
    with app.app_context():
        domains = list(
            r.table("domains")
            .get_all(deployment_id, index="tag")
            .has_fields("jumperurl")
            .pluck("id", "user", "jumperurl")
            .run(db.conn)
        )

    if len(domains) == 0:
        return "username,name,email,url"

    with app.app_context():
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


def get_deployment_details_hardware(deployment_id):
    with app.app_context():
        hardware = (
            r.table("deployments")
            .get(deployment_id)
            .pluck("create_dict")["create_dict"]
            .merge(
                lambda domain: {
                    "video_name": domain["hardware"]["videos"].map(
                        lambda video: r.table("videos").get(video)["name"]
                    ),
                    "boot_name": domain["hardware"]["boot_order"].map(
                        lambda boot_order: r.table("boots").get(boot_order)["name"]
                    ),
                    "reservable_name": r.branch(
                        domain["reservables"]["vgpus"].default(None),
                        domain["reservables"]["vgpus"].map(
                            lambda reservable: r.table("reservables_vgpus").get(
                                reservable
                            )["name"]
                        ),
                        False,
                    ),
                }
            )
            .run(db.conn)
        )
    if "interfaces" in hardware["hardware"]:
        interfaces = hardware["hardware"]["interfaces"]
        hardware["hardware"]["interfaces"] = []
        # Loop instead of a get_all query to keep the interfaces array order
        for interface in interfaces:
            with app.app_context():
                hardware["hardware"]["interfaces"].append(
                    r.table("interfaces")
                    .get(interface)
                    .pluck("id", "name")
                    .run(db.conn)
                )
    if "isos" in hardware["hardware"]:
        isos = hardware["hardware"]["isos"]
        hardware["hardware"]["isos"] = []
        # Loop instead of a get_all query to keep the isos array order
        for iso in isos:
            with app.app_context():
                hardware["hardware"]["isos"].append(
                    r.table("media").get(iso["id"]).pluck("id", "name").run(db.conn)
                )
    if "floppies" in hardware["hardware"]:
        with app.app_context():
            hardware["hardware"]["floppies"] = list(
                r.table("media")
                .get_all(
                    r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                    index="id",
                )
                .pluck("id", "name")
                .run(db.conn)
            )
    hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576
    return hardware


def get_co_owners(deployment_id):
    try:
        with app.app_context():
            deployment = r.table("deployments").get(deployment_id).run(db.conn)
        return {
            "owner": alloweds.get_allowed({"users": [deployment.get("user")]})["users"][
                0
            ],
            "co_owners": alloweds.get_allowed({"users": deployment.get("co_owners")})[
                "users"
            ],
        }
    except:
        raise Error(
            "not_found",
            f"Not found deployment id to get co-owners: {deployment_id}",
            description_code="not_found",
        )


def update_co_owners(deployment_id, co_owners: list):
    try:
        with app.app_context():
            deployment = r.table("deployments").get(deployment_id).run(db.conn)
    except:
        raise Error(
            "not_found",
            f"Not found deployment id to update co-owners: {deployment_id}",
            description_code="not_found",
        )

    try:
        owner = deployment.get("user")
        if owner in co_owners:
            co_owners.remove(owner)

        with app.app_context():
            co_owners = (
                r.table("users")
                .get_all(r.args(co_owners))
                .filter(lambda doc: doc["role"].ne("user"))
                .pluck("id")
                .map(lambda doc: doc["id"])
                .coerce_to("array")
                .run(db.conn)
            )

        with app.app_context():
            r.table("deployments").get(deployment_id).update(
                {"co_owners": co_owners}
            ).run(db.conn)
        invalidate_cache("deployments", deployment_id)
    except:
        raise Error(
            "internal_server",
            f"Unable to update co-owners for deployment: {deployment_id}",
            description_code="unable_to_update",
        )


def change_owner_deployment(payload, deployment_id, owner_id):
    deployment_user = get_document("deployments", deployment_id, ["user"])
    category = get_document("users", deployment_user, ["category"])
    user_data = get_new_user_data(owner_id)
    if (
        user_data["new_user"].get("category") != category
        and user_data["new_user"].get("role") != "admin"
    ):
        edit_deployment_users(
            payload,
            deployment_id,
            _validate_item("allowed", {"allowed": {}})["allowed"],
        )
    invalidate_cache("deployments", deployment_id)
    change_owner_deployments([deployment_id], user_data, deployment_user)


def get_deployment_permissions(deployment_id):
    users_permissions = get_document("deployments", deployment_id, ["user_permissions"])
    if users_permissions is None:
        raise Error(
            "not_found",
            "Could not find deployment",
            description_code="not_found",
        )
    return users_permissions


def get_unused_deployments():
    """
    Retrieve a list of unused deployments that have not been accessed considering the specified cutoff time in the unused_item_timeout table.

    :return: List of deployments that have not been accessed within the specified cutoff_time.
    :rtype: list
    """
    deployments = []
    start = absolute_start = time.time()

    with app.app_context():
        users_with_deployments = list(
            r.table("deployments").pluck("user").distinct()["user"].run(db.conn)
        )

    log.debug(
        "api_deployments get unused desktops: Retrieved users with desktops in %s seconds",
        time.time() - start,
    )

    for user in users_with_deployments:
        start = time.time()
        try:
            payload = gen_payload_from_user(user)
            user_timeout_rule = get_unused_item_timeout(
                payload, "send_unused_deployments_to_recycle_bin"
            )
        except TypeError as e:
            # If the user does not exist then send to the recycle bin all of its deployments
            log.error(
                "api_deployments get unused deployments: Could not generate payload for user %s",
                user,
            )
            user_timeout_rule = {"cutoff_time": 0}
            pass

        log.debug(
            "api_deployments get unused desktops: User %s applied rule %s",
            user,
            user_timeout_rule,
        )
        if user_timeout_rule is False or user_timeout_rule["cutoff_time"] is None:
            continue
        cutoff_time = timedelta(days=user_timeout_rule["cutoff_time"] * 30)
        cutoff_timestamp = (datetime.now() - cutoff_time).timestamp()
        with app.app_context():
            user_deployments = list(
                r.table("deployments")
                .get_all(user, index="user")
                .eq_join("id", r.table("domains"), index="tag")
                .pluck(
                    {"left": ["id", "user", "name", "co_owners"]},
                    {"right": ["accessed"]},
                )
                .group(r.row["left"]["id"])
                .max(r.row["right"]["accessed"])
                .ungroup()
                .filter(
                    lambda row: row["reduction"]["right"]["accessed"] < cutoff_timestamp
                )
                .map(
                    lambda row: {
                        "id": row["reduction"]["left"]["id"],
                        "accessed": row["reduction"]["right"]["accessed"],
                        "user": row["reduction"]["left"]["user"],
                        "name": row["reduction"]["left"]["name"],
                        "co_owners": row["reduction"]["left"]["co_owners"],
                    }
                )
                .run(db.conn)
            )

        log.debug(
            "api_deployments get unused desktops: Retrieved deployments and applied rule in %s seconds",
            time.time() - start,
        )

        deployments += user_deployments

    log.debug(
        "api_deployments get unused deployments: Retrieved users with deployments in %s seconds",
        time.time() - absolute_start,
    )

    return deployments
