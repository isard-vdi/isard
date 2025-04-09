# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import admin_table_get, admin_table_update
from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_desktops_persistent import (
    unassign_resource_from_desktops_and_deployments,
)
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin, owns_table_item_id, ownsMediaId

alloweds = ApiAllowed()


# Gets all list of roles, categories, groups and users from a 2+ chars term
@app.route("/api/v3/admin/allowed/term/<table>", methods=["POST"])
@has_token
def alloweds_table_term(payload, table):
    if table not in [
        "domains",
        "roles",
        "categories",
        "groups",
        "users",
        "media",
        "deployments",
    ]:
        raise Error("forbidden", "Table not allowed.")
    data = request.get_json(force=True)
    data["pluck"] = ["id", "name"]
    if payload["role_id"] == "admin":
        if table == "groups":
            result = alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=["id", "name", "parent_category", "category_name"],
                index_key="parent_category" if data.get("category") else None,
                index_value=data["category"] if data.get("category") else None,
            )
        elif table == "users":
            if data.get("roles"):
                result = alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "uid", "role", "category_name", "group_name"],
                    query_filter=lambda user: (
                        user["role"] not in data.get("roles", [])
                        if data.get("roles")
                        else None
                    ),
                )
            elif data.get("category"):
                result = alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "uid", "role", "category_name", "group_name"],
                    index_key="category",
                    index_value=data["category"],
                )
            else:
                result = alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=[
                        "id",
                        "username",
                        "name",
                        "uid",
                        "role",
                        "category_name",
                        "group_name",
                    ],
                )
        elif table == "media":
            if data["kind"] == "isos":
                kind = "iso"
            if data["kind"] == "floppies":
                kind = "floppy"
            result = alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value=kind,
            )
        else:
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
    else:
        if table == "roles":
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
        if table == "categories":
            result = alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"],
                index_key="id",
                index_value=payload["category_id"],
            )
        if table == "groups":
            result = alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=["id", "name", "parent_category", "category_name"],
                index_key="parent_category",
                index_value=payload["category_id"],
            )
        if table == "users":
            if data.get("roles"):
                result = alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "category", "uid", "role"],
                    index_key="category",
                    index_value=payload["category_id"],
                    query_filter=lambda user: (
                        user["role"] not in data.get("roles", [])
                        if data.get("roles")
                        else None
                    ),
                )
            else:
                result = alloweds.get_table_term(
                    table,
                    "name",
                    data["term"],
                    pluck=["id", "name", "category", "uid"],
                    index_key="category",
                    index_value=payload["category_id"],
                )
        if table == "media":
            if data["kind"] == "isos":
                kind = "iso"
            if data["kind"] == "floppies":
                kind = "floppy"
            # Search in the db for the term
            term_results = alloweds.get_table_term(
                table,
                "name",
                data["term"],
                pluck=data["pluck"] + ["user", "allowed"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value=kind,
            )
            # Filter if the user is allowed to see said resource
            result = []
            for element in term_results:
                if alloweds.is_allowed(payload=payload, item=element, table="media"):
                    element.pop("allowed")
                    result.append(element)
    return json.dumps(result), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/allowed/update/<table>", methods=["POST"])
@owns_table_item_id
def admin_allowed_update(payload, table):
    data = request.get_json(force=True)
    data.update(_validate_item("allowed", data["allowed"]))

    if table == "bastion":
        table = "config"

        @is_admin
        def bastion_allowed_update(payload):
            alloweds.update_bastion_alloweds(
                data["allowed"],
            )
            # update targets table without the disallowed ones
            alloweds.remove_disallowed_bastion_targets_th()

        bastion_allowed_update()
    else:
        admin_table_update(table, {"id": data["id"], "allowed": data["allowed"]})
    if table in ["interfaces", "media", "reservables_vgpus", "boots", "videos"]:
        item = data
        if table == "media":
            ownsMediaId(payload, data["id"])
        if not data["allowed"].get("roles") or not data["allowed"].get("categories"):
            item = admin_table_get(table, data["id"])
            item["allowed"].update(data["allowed"])
        unassign_resource_from_desktops_and_deployments(table, item)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


# Who has acces to a table item
@app.route("/api/v3/allowed/table/<table>", methods=["POST"])
@owns_table_item_id
def allowed_table(payload, table):
    data = request.get_json(force=True)

    if table == "bastion":
        table = "config"
        result = alloweds.get_allowed(
            admin_table_get(table, data["id"], pluck={"bastion": "allowed"})["bastion"][
                "allowed"
            ]
        )
    else:
        result = alloweds.get_allowed(
            admin_table_get(table, data["id"], pluck=["allowed"])["allowed"]
        )
    return json.dumps(result), 200, {"Content-Type": "application/json"}
