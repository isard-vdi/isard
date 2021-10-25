# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import (
    Response,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r

from ...lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin, isAdminManager

"""
LANDING ADMIN PAGE
"""


@app.route("/isard-admin/admin")
@login_required
@isAdmin
def admin():
    return render_template(
        "admin/pages/hypervisors.html",
        title="Hypervisors",
        header="Hypervisors",
        nav="Hypervisors",
    )


@app.route("/isard-admin/admin/table/<table>/get")
@login_required
@isAdminManager
def admin_table_get(table):
    result = app.adminapi.get_admin_table(table)
    if table == "scheduler_jobs":
        for i, val in enumerate(result):
            result[i].pop("job_state", None)
    if current_user.role == "manager":
        if table == "categories":
            result = [
                {**r, **{"editable": False}}
                for r in result
                if r["id"] == current_user.category
            ]

        if table == "groups":
            result = [
                r
                for r in result
                if "parent_category" in r.keys()
                and r["parent_category"] == current_user.category
            ]
        if table == "roles":
            result = [r for r in result if r["id"] != "admin"]
    return json.dumps(result), 200, {"Content-Type": "application/json"}


# Used in quota.js for admin users
@app.route("/isard-admin/admin/load/<table>/post", methods=["POST"])
@login_required
@isAdminManager
def admin_load_post(table):
    if request.method == "POST":
        data = request.get_json(force=True)
        if "id" not in data.keys():
            data["id"] = False
        if "pluck" not in data.keys():
            data["pluck"] = False
        if "order" not in data.keys():
            data["order"] = False
        if "flatten" not in data.keys():
            data["flatten"] = True
        if table == "media" and current_user.role == "manager":
            result = app.isardapi.get_all_alloweds_table(
                "media", current_user.id, pluck=False
            )
        else:
            result = app.adminapi.get_admin_table(
                table,
                id=data["id"],
                pluck=data["pluck"],
                order=data["order"],
                flatten=data["flatten"],
            )

        return json.dumps(result), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not delete."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/table/<table>/post", methods=["POST"])
@login_required
@isAdminManager
def admin_table_post(table):
    if request.method == "POST":
        data = request.get_json(force=True)
        if "pluck" not in data.keys():
            data["pluck"] = False
        if "kind" not in data.keys():
            data["kind"] = False
        # ~ else:
        # ~ if data['kind']=='template':
        # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
        # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
        # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
        # ~ else:
        # ~ if data['kind']='not_desktops':
        # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=)
        # ~ if 'order' not in data.keys():
        # ~ data['order']=False
        result = app.adminapi.get_admin_table_term(
            table, "name", data["term"], pluck=data["pluck"], kind=data["kind"]
        )
        return json.dumps(result), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not delete."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/getAllTemplates", methods=["POST"])
@login_required
@isAdminManager
def admin_get_all_templates():
    if request.method == "POST":
        data = request.get_json(force=True)
        result = app.adminapi.get_admin_templates(data["term"])
        if current_user.role == "manager":
            result = [d for d in result if d["category"] == current_user.category]
        return json.dumps(result), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not delete."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/delete", methods=["POST"])
@login_required
@isAdminManager
def admin_delete():
    if request.method == "POST":
        if app.adminapi.delete_table_key(
            request.get_json(force=True)["table"], request.get_json(force=True)["pk"]
        ):
            return json.dumps("Deleted"), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not delete."), 500, {"Content-Type": "application/json"}


"""
CONFIG
"""


@app.route("/isard-admin/admin/config", methods=["GET", "POST"])
@login_required
@isAdminManager
def admin_config():
    if request.method == "POST":
        return (
            json.dumps(app.adminapi.get_admin_config(1)),
            200,
            {"Content-Type": "application/json"},
        )
    return render_template("admin/pages/config.html", nav="Config")


# ~ @app.route('/isard-admin/admin/disposables', methods=["POST"])
# ~ @login_required
# ~ @isAdmin
# ~ def admin_disposables():
# ~ result=app.adminapi.get_admin_table('disposables')
# ~ return json.dumps(result), 200, {'Content-Type':'application/json'}


@app.route("/isard-admin/admin/config/update", methods=["POST"])
@login_required
@isAdminManager
def admin_config_update():
    if request.method == "POST":
        dict = app.isardapi.f.unflatten_dict(request.form)
        if "auth" in dict:
            dict["auth"]["local"] = (
                {"active": False} if "local" not in dict["auth"] else {"active": True}
            )
            dict["auth"]["ldap"]["active"] = (
                False if "active" not in dict["auth"]["ldap"] else True
            )
        if "engine" in dict:
            if "grafana" in dict["engine"]:
                dict["engine"]["grafana"]["active"] = (
                    False if "active" not in dict["engine"]["grafana"] else True
                )
            if "ssh" in dict["engine"]:
                if "hidden" in dict["engine"]["ssh"]:
                    dict["engine"]["ssh"]["paramiko_host_key_policy_check"] = (
                        True
                        if "paramiko_host_key_policy_check" in dict["engine"]["ssh"]
                        else False
                    )
                    dict["engine"]["ssh"].pop("hidden", None)
        if "disposable_desktops" in dict:
            dict["disposable_desktops"].pop("id", None)
            dict["disposable_desktops"]["active"] = (
                False if "active" not in dict["disposable_desktops"] else True
            )
        if app.adminapi.update_table_dict("config", 1, dict):
            # ~ return json.dumps('Updated'), 200, {'Content-Type':'application/json'}
            return render_template("admin/pages/config.html", nav="Config")
    return json.dumps("Could not update."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/disposable/add", methods=["POST"])
@login_required
@isAdminManager
def admin_disposable_add():
    if request.method == "POST":
        dsps = []
        # ~ Next 2 lines should be removed when form returns a list
        nets = [request.form["nets"]]
        disposables = request.form.getlist("disposables")
        for d in disposables:
            dsps.append(
                app.adminapi.get_admin_table(
                    "domains", pluck=["id", "name", "description"], id=d
                )
            )
        disposable = [
            {
                "id": app.isardapi.parse_string(request.form["name"]),
                "active": True,
                "name": request.form["name"],
                "description": request.form["description"],
                "nets": nets,
                "disposables": dsps,
            }
        ]
        if app.adminapi.insert_table_dict("disposables", disposable):
            return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not update."), 500, {"Content-Type": "application/json"}


"""
BACKUP & RESTORE
"""


@app.route("/isard-admin/admin/backup", methods=["POST"])
@login_required
@isAdmin
def admin_backup():
    if request.method == "POST":
        app.adminapi.backup_db()
        return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/restore", methods=["POST"])
@login_required
@isAdmin
def admin_restore():
    if request.method == "POST":
        app.adminapi.restore_db(request.get_json(force=True)["pk"])
        return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/restore/<table>", methods=["POST"])
@login_required
@isAdmin
def admin_restore_table(table):
    global backup_data, backup_db
    if request.method == "POST":
        data = request.get_json(force=True)["data"]
        insert = data["new_backup_data"]
        data.pop("new_backup_data", None)
        if insert:
            if app.adminapi.insert_table_dict(table, data):
                return json.dumps("Inserted"), 200, {"Content-Type": "application/json"}
        else:
            id = data["id"]
            data.pop("id", None)
            if app.adminapi.update_table_dict(table, id, data):
                return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/backup_remove", methods=["POST"])
@login_required
@isAdmin
def admin_backup_remove():
    if request.method == "POST":
        app.adminapi.remove_backup_db(request.get_json(force=True)["pk"])
        return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


backup_data = {}
backup_db = []


@app.route("/isard-admin/admin/backup_info", methods=["POST"])
@login_required
@isAdmin
def admin_backup_info():
    global backup_data, backup_db
    if request.method == "POST":
        backup_data, backup_db = app.adminapi.info_backup_db(
            request.get_json(force=True)["pk"]
        )
        return json.dumps(backup_data), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/backup_detailinfo", methods=["POST"])
@login_required
@isAdmin
def admin_backup_detailinfo():
    global backup_data, backup_db
    if request.method == "POST":
        table = request.get_json(force=True)["table"]
        if table == "":
            return json.dumps({}), 200, {"Content-Type": "application/json"}
        new_db = app.adminapi.check_new_values(table, backup_db[table])
        return json.dumps(new_db), 200, {"Content-Type": "application/json"}
    return json.dumps("Method not allowed."), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/backup/download/<id>", methods=["GET"])
@login_required
@isAdmin
def admin_backup_download(id):
    filedir, filename, data = app.adminapi.download_backup(id)
    return Response(
        data,
        mimetype="application/x-gzip",
        headers={"Content-Disposition": "attachment;filename=" + filename},
    )


@app.route("/isard-admin/admin/backup/upload", methods=["POST"])
@login_required
@isAdmin
def admin_backup_upload():
    for f in request.files:
        app.adminapi.upload_backup(request.files[f])
    return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
