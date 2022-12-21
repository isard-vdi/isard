#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

import requests
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .._common.api_exceptions import Error
from .flask_rethink import RDB
from .isardViewer import default_guest_properties

db = RDB(app)
db.init_app(app)

from .api_cards import get_domain_stock_card
from .helpers import get_user_data


class Downloads(object):
    def __init__(self):
        self.reload_updates()

    def reload_updates(self):
        self.updateFromConfig()
        if not self.is_registered():
            self.register()
            self.updateFromConfig()
        self.updateFromWeb()

    def updateFromWeb(self):
        self.web = {}
        self.kinds = [
            "media",
            "domains",
            "virt_install",
            "videos",
            "viewers",
        ]
        for k in self.kinds:
            self.web[k] = self.getKind(kind=k)
            if self.web[k] == 500:
                # The id is no longer in updates server.
                # We better reset it
                with app.app_context():
                    r.table("config").get(1).update({"resources": {"code": False}}).run(
                        db.conn
                    )
                    self.code = False
        if self.private_code != False:
            private_web = self.getPrivateKind(kind="private_domains")
            if private_web != False:
                self.web["domains"] = self.web["domains"] + private_web

    def updateFromConfig(self):
        with app.app_context():
            failed = True
            while failed:
                try:
                    cfg = (
                        r.table("config")
                        .get(1)
                        .pluck("resources")
                        .run(db.conn)["resources"]
                    )
                    failed = False
                except Exception as e:
                    log.warning("Waiting for database to be ready...")
                    time.sleep(1)

        self.url = cfg["url"]
        self.code = cfg["code"]
        self.private_code = (
            False if "private_code" not in cfg.keys() else cfg["private_code"]
        )

    def is_conected(self):
        try:
            req = requests.get(self.url, allow_redirects=False, verify=True, timeout=10)
            if req.status_code == 200:
                return True
        except:
            return False
        return False

    def is_registered(self):
        if self.is_conected():
            return self.code
        return False

    def register(self):
        try:
            req = requests.post(
                self.url + "/register", allow_redirects=False, verify=True, timeout=10
            )
            if req.status_code == 200:
                with app.app_context():
                    r.table("config").get(1).update(
                        {"resources": {"code": req.json()}}
                    ).run(db.conn)
                    self.code = req.json()
                    self.updateFromConfig()
                    self.updateFromWeb()
                    return True
            else:
                print(
                    "Error response code: "
                    + str(req.status_code)
                    + "\nDetail: "
                    + r.json()
                )
        except Exception as e:
            print("Error repository register.\n" + str(e))
        return False

    def getNewKind(self, kind, username):
        if kind == "viewers":
            return self.web[kind]
        web = self.web[kind]
        with app.app_context():
            dbb = list(r.table(kind).run(db.conn))
        result = []
        for w in web:
            dict = {}
            found = False
            for d in dbb:
                if kind == "domains" or kind == "media":
                    if d["id"] == "_" + username + "_" + w["id"]:
                        dict = w.copy()
                        found = True
                        dict["id"] = "_" + username + "_" + dict["id"]
                        dict["new"] = False
                        dict["status"] = d["status"]
                        dict["progress"] = d.get("progress", False)
                        break
                else:
                    if d["id"] == w["id"]:
                        dict = w.copy()
                        found = True
                        dict["new"] = False
                        dict["status"] = "Downloaded"
                        break

            if not found:
                dict = w.copy()
                if kind == "domains" or kind == "media":
                    dict["id"] = "_" + username + "_" + dict["id"]
                dict["new"] = True
                dict["status"] = "Available"
            result.append(dict)
        return result

    def getNewKindId(self, kind, username, id):
        if kind == "domains" or kind == "media":
            web = [
                d.copy() for d in self.web[kind] if "_" + username + "_" + d["id"] == id
            ]
        else:
            web = [d.copy() for d in self.web[kind] if d["id"] == id]

        if len(web) == 0:
            return False
        w = web[0].copy()

        if kind == "domains" or kind == "media":
            with app.app_context():
                dbb = r.table(kind).get("_" + username + "_" + w["id"]).run(db.conn)
            if dbb is None:
                w["id"] = "_" + username + "_" + w["id"]
                return w
            elif dbb.get("status") == "DownloadFailed":
                return dbb
        else:
            with app.app_context():
                dbb = r.table(kind).get(w["id"]).run(db.conn)
            if dbb == None:
                return w
        return False

    def getKind(self, kind):
        try:
            req = requests.post(
                self.url + "/get/" + kind + "/list",
                headers={"Authorization": str(self.code)},
                allow_redirects=False,
                verify=True,
                timeout=10,
            )
            if req.status_code == 200:
                return req.json()
                # ~ return True
            elif req.status_code == 500:
                return 500
            else:
                print(
                    "Error response code: "
                    + str(req.status_code)
                    + "\nDetail: "
                    + req.json()
                )
        except Exception as e:
            print("Error repository getkinds.\n" + str(e))
        return False

    def getPrivateKind(self, kind="private_domains"):
        try:
            req = requests.post(
                self.url + "/private_get/" + kind + "/list",
                headers={"Authorization": str(self.code)},
                json={"private_code": self.private_code},
                allow_redirects=False,
                verify=True,
                timeout=10,
            )
            if req.status_code == 200:
                return req.json()
            else:
                print(
                    "Error response code: "
                    + str(req.status_code)
                    + "\nDetail: "
                    + str(req.json())
                )
                return False
        except Exception as e:
            print("Error repository getkind priv.\n" + str(e))
        return False

    """
    RETURN FORMATTED DOMAINS TO INSERT ON TABLES
    """

    def formatDomains(self, data, user_id):
        new_data = data.copy()
        for d in new_data:
            d["progress"] = {}
            d["status"] = "DownloadStarting"
            d["detail"] = ""
            d["image"] = get_domain_stock_card(d["id"])
            d["accessed"] = int(time.time())
            d["hypervisors_pools"] = d["create_dict"]["hypervisors_pools"]
            d["guest_properties"] = default_guest_properties()
            if d.get("options"):
                d.pop("options")
            d.update(get_user_data(user_id))
            path = self.get_user_path(user_id)
            for disk in d["create_dict"]["hardware"]["disks"]:
                if not disk["file"].startswith(path):
                    disk["file"] = path + disk["file"]
        return new_data

    def formatMedias(self, data, user_id):
        new_data = data.copy()
        for d in new_data:
            d.update(get_user_data(user_id))
            d["progress"] = {}
            d["status"] = "DownloadStarting"
            d["accessed"] = int(time.time())
            path = self.get_user_path(user_id)
            if d["url-isard"] == False:
                d["path"] = path + d["url-web"].split("/")[-1]
            else:
                d["path"] = path + d["url-isard"]
        return new_data

    def get_user_path(self, user_id):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        return (
            user["category"]
            + "/"
            + user["group"]
            + "/"
            + user["provider"]
            + "/"
            + user["uid"]
            + "-"
            + user["username"]
            + "/"
        )

    """
    DOWNLOAD MISSING DOMAIN RESOURCES
    """

    def get_missing_resources(self, domain, username):
        missing_resources = {"videos": []}

        dom_videos = domain["create_dict"]["hardware"]["videos"]
        with app.app_context():
            sys_videos = list(r.table("videos").pluck("id").run(db.conn))
        sys_videos = [sv["id"] for sv in sys_videos]
        for v in dom_videos:
            if v not in sys_videos:
                resource = self.getNewKindId("videos", username, v)
                if resource != False:
                    missing_resources["videos"].append(resource)
        ## graphics and interfaces missing
        return missing_resources
