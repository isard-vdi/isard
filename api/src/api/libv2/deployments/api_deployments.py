#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import copy
import csv
import io
import os
import traceback
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
    parse_domain_insert,
    parse_domain_update,
)
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
                    "totalDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .count(),
                    "startedDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .filter({"status": "Started"})
                    .count(),
                    "visibleDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .filter({"tag_visible": True})
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
    with app.app_context():
        deployments_coowners = list(
            r.table("deployments")
            .get_all(user_id, index="co_owners")
            .merge(
                lambda deployment: {
                    "totalDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .count(),
                    "startedDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .filter({"status": "Started"})
                    .count(),
                    "visibleDesktops": r.table("domains")
                    .get_all(deployment["id"], index="tag")
                    .filter({"tag_visible": True})
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
    deployments = deployments_owner + deployments_coowners
    deployments.sort(key=lambda x: x["name"].lower(), reverse=True)

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
    deployment = get_document("deployments", deployment_id)
    if deployment is None:
        raise Error(
            "not_found",
            "Deployment id not found: " + str(deployment_id),
            description_code="not_found",
        )
    deployment["totalDesktops"] = len(get_cached_deployment_desktops(deployment_id))
    deployment["visibleDesktops"] = len(
        [
            desktop
            for desktop in get_cached_deployment_desktops(deployment_id)
            if desktop["tag_visible"] == True
        ]
    )
    deployment["startedDesktops"] = len(
        [
            desktop
            for desktop in get_cached_deployment_desktops(deployment_id)
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
    deployment["description"] = get_document(
        "deployments", deployment_id, ["create_dict"]
    ).get("description")
    deployment["visible"] = get_document(
        "deployments", deployment_id, ["create_dict"]
    ).get("tag_visible")
    deployment["template"] = get_document(
        "domains",
        get_document("deployments", deployment_id, ["create_dict"]).get("template"),
    ).get("name")
    deployment["desktop_name"] = get_document(
        "deployments", deployment_id, ["create_dict"]
    ).get("name")
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
    from pprint import pformat

    app.logger.debug(pformat(template))
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
            "user_permissions": user_permissions,
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
    ApiDesktopsPersistent().NewFromTemplateTh(desktops)


def edit_deployment_users(payload, deployment_id, allowed, users):
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
    data["user_permissions"] = data.get("user_permissions", [])
    with app.app_context():
        r.table("deployments").get(deployment_id).update(
            {
                "create_dict": {
                    **data,
                    "guest_properties": r.literal(data["guest_properties"]),
                },
                "name": data["tag_name"],
                "user_permissions": data["user_permissions"],
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

    # Otherwise the rest of the hardware can be update at once
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
        with app.app_context():
            r.table("deployments").get(deployment_id).update(
                {"create_dict": {"tag_visible": visible}}
            ).run(db.conn)
        invalidate_cache("deployments", deployment_id)
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


def update_owner(payload, deployment_id, owner_id):
    deployment = get_document("deployments", deployment_id)
    if deployment is None:
        raise Error(
            "not_found",
            f"Not found deployment id to update owner: {deployment_id}",
            description_code="not_found",
        )
    owner = get_document("users", owner_id)
    if owner is None:
        raise Error(
            "not_found",
            f"Not found owner id to update owner: {owner_id}",
            description_code="not_found",
        )

    if deployment.get("user") == owner_id:
        raise Error(
            "bad_request",
            "Owner is already the same as the new owner",
            description_code="already_owner",
        )

    if owner.get("role") not in ["admin", "manager", "advanced"]:
        raise Error(
            "bad_request",
            f"New owner for deployment {deployment_id} is a user",
            description_code="new_owner_is_user",
        )

    if (
        owner.get("category") != deployment.get("category")
        and owner.get("role") != "admin"
    ):
        edit_deployment_users(
            payload,
            deployment_id,
            _validate_item("allowed", {"allowed": {}})["allowed"],
        )

    try:
        co_owners = deployment.get("co_owners")
        if owner_id in deployment.get("co_owners"):
            co_owners.remove(owner_id)
        co_owners.append(deployment.get("user"))

        with app.app_context():
            r.table("deployments").get(deployment_id).update(
                {
                    "co_owners": co_owners,
                    "user": owner_id,
                }
            ).run(db.conn)
        invalidate_cache("deployments", deployment_id)
    except:
        raise Error(
            "internal_server",
            f"Unable to update owner for deployment: {deployment_id}",
            description_code="unable_to_update",
        )


def get_deployment_permissions(deployment_id):
    deployment = get_document("deployments", deployment_id, "user_permissions")
    if deployment is None:
        raise Error(
            "not_found",
            "Could not find deployment",
            description_code="not_found",
        )
    return deployment.get("user_permissions", [])
