# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

import json
import time
from uuid import uuid4

from flask import Response, request

from webapp import app

from ..auth.authentication import *
from ..lib.isardViewer import isardViewer
from ..lib.log import *

isardviewer = isardViewer()


class usrTokens:
    def __init__(self):
        self.tokens = {}
        self.valid_seconds = 300  # Between client accesses to api

    def tkns(self):
        return self.tokens

    def add(self, usr):
        tkn = str(uuid4())[:32]
        self.tokens[tkn] = {"usr": usr, "timestamp": time.time(), "domains": []}
        return tkn
        # we should check other tokens for expiry time

    def valid(self, tkn):
        if tkn in self.tokens.keys():
            if time.time() - self.tokens[tkn]["timestamp"] < self.valid_seconds:
                self.tokens[tkn]["timestamp"] = time.time()
                return True
            else:
                self.tokens.pop(tkn, None)
        return False

    def login(self, usr, pwd):
        # CHECK IF USR ALREADY IN TOKENS??
        au = auth()
        if au.check(usr, pwd):
            return self.add(usr)
        return False

    def domains(self, tkn):
        if not self.valid(tkn):
            return False
        usr_domains = app.isardapi.get_user_domains(self.tokens[tkn]["usr"])
        self.tokens[tkn]["domains"] = [
            {"id": d["id"], "name": d["name"], "status": d["status"]}
            for d in usr_domains
        ]
        return self.tokens[tkn]["domains"]

    def start(self, tkn, id):
        if not self.valid(tkn):
            return False
        if not any(d["id"] == id for d in self.tokens[tkn]["domains"]):
            return False
        for d in self.tokens[tkn]["domains"]:
            if d["id"] == id:
                if d["status"] in ["Stopped", "Failed"]:
                    app.isardapi.update_table_value("domains", id, "status", "Starting")
                    step = 0
                    while step < 5:
                        status = app.isardapi.get_domain(id)["status"]
                        if status is not "Starting":
                            return status
                        time.sleep(1)
                        step = step + 1
                    return status
                elif d["status"] in ["Started"]:
                    return d["status"]

                else:
                    err = "domain in unknown status: " + d["status"]
                    log.debug(err)
                    return err

        return False

    def viewer(self, tkn, id, remote_addr):
        if not self.valid(tkn):
            return False
        data = {"pk": id, "kind": "spice-client"}

        # this little hack is needed since the get_viewer function is going to access the the role and the id using attribute notation
        class current_user:
            pass

        current_user.id = self.tokens[tkn]["usr"]

        if current_user.id == "admin":
            current_user.role = "admin"

        else:
            current_user.role = False

        viewer = isardviewer.get_viewer(data, current_user, remote_addr)
        return Response(
            viewer["content"],
            mimetype="application/x-virt-viewer",
            headers={"Content-Disposition": "attachment;filename=console.vv"},
        )
        # SPICE {'kind':'file','ext':'vv','mime':'application/x-virt-viewer','content':'vv data file'}
        # PC VNC 'vnc','text/plain'


app.tokens = usrTokens()


@app.route("/pxe/login", methods=["POST"])
def pxe_login():
    usr = request.get_json(force=True)["usr"]
    pwd = request.get_json(force=True)["pwd"]
    tkn = app.tokens.login(usr, pwd)

    if tkn:
        return json.dumps({"tkn": tkn}), 200, {"ContentType": "application/json"}
    return json.dumps({"tkn": ""}), 401, {"ContentType": "application/json"}


@app.route("/pxe/list", methods=["GET"])
def pxe_list():
    tkn = request.args.get("tkn")
    domains = app.tokens.domains(tkn)
    if domains is not False:
        # What happens if user has no domains?
        return json.dumps({"vms": domains}), 200, {"ContentType": "application/json"}
    return json.dumps({"vms": ""}), 403, {"ContentType": "application/json"}


@app.route("/pxe/start", methods=["POST"])
def pxe_start():
    tkn = request.get_json(force=True)["tkn"]
    id = request.get_json(force=True)["id"]
    res = app.tokens.start(tkn, id)
    if res is False:
        return (
            json.dumps({"code": 0, "msg": "Token expired or not user domain"}),
            403,
            {"ContentType": "application/json"},
        )
    else:
        if res == "Started":
            return json.dumps({}), 200, {"ContentType": "application/json"}
        else:
            if res == "Failed":
                return (
                    json.dumps({"code": 2, "msg": "Get domain message for failed..."}),
                    500,
                    {"ContentType": "application/json"},
                )
            if res == "Starting":
                return (
                    json.dumps(
                        {
                            "code": 1,
                            "msg": "Engine seems to be down. Contact administrator.",
                        }
                    ),
                    500,
                    {"ContentType": "application/json"},
                )

            if str(res).startswith("domain in unknown status: "):
                return (
                    json.dumps({"code": 2, "msg": res}),
                    500,
                    {"ContentType": "application/json"},
                )

        return (
            json.dumps(
                {"code": 1, "msg": "Unknown error. Domain status is: " + str(res)}
            ),
            500,
            {"ContentType": "application/json"},
        )


@app.route("/pxe/viewer", methods=["GET"])
def pxe_viewer():
    remote_addr = (
        request.headers["X-Forwarded-For"].split(",")[0]
        if "X-Forwarded-For" in request.headers
        else request.remote_addr.split(",")[0]
    )
    tkn = request.args.get("tkn")
    id = request.args.get("id")
    res = app.tokens.viewer(tkn, id, remote_addr)
    if res is False:
        return (
            json.dumps({"code": 0, "msg": "Token expired or not user domain"}),
            403,
            {"ContentType": "application/json"},
        )
    else:
        return res
