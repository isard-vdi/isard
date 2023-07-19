#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import time
from functools import wraps

import requests
from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .._common.api_exceptions import Error
from .flask_rethink import RDB
from .isardViewer import default_guest_properties

db = RDB(app)
db.init_app(app)

from .api_cards import get_domain_stock_card
from .helpers import get_user_data


def is_registered(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            req = requests.get(get_cfg()[0], allow_redirects=False, timeout=10)
            if req.status_code == 200:
                if not get_cfg()[1]:
                    raise Error(
                        "precondition_required", "IsardVDI hasn't been registered yet."
                    )
                return f(*args, **kwargs)
        except:
            raise
        raise Error(
            "gateway_timeout",
            "There is a network or update server error at the moment. Try again later.",
        )

    return decorated


@cached(cache=TTLCache(maxsize=1, ttl=360))
def get_cfg():
    with app.app_context():
        cfg = r.table("config").get(1).pluck("resources").run(db.conn).get("resources")
    return (
        cfg["url"],
        cfg["code"],
        (False if "private_code" not in cfg.keys() else cfg["private_code"]),
    )


def register():
    url, code, private_code = get_cfg()
    if code:
        return True
    try:
        req = requests.post(url + "/register", allow_redirects=False, timeout=10)
        if req.status_code == 200:
            with app.app_context():
                r.table("config").get(1).update(
                    {"resources": {"code": req.json()}}
                ).run(db.conn)
            get_cfg.cache_clear()
            return True
        else:
            print(
                "Error response code: " + str(req.status_code) + "\nDetail: " + r.json()
            )
    except Exception as e:
        print("Error repository register.\n" + str(e))
    return False


@cached(cache=TTLCache(maxsize=1, ttl=360))
def get_web_kinds():
    web = {}
    kinds = [
        "media",
        "domains",
        "virt_install",
        "videos",
        "viewers",
    ]
    url, code, private_code = get_cfg()
    for k in kinds:
        web[k] = download_web_kind(kind=k)
        if web[k] == 500:
            # The id is no longer in updates server.
            # We better reset it
            with app.app_context():
                r.table("config").get(1).update({"resources": {"code": False}}).run(
                    db.conn
                )
    if private_code != False:
        private_web = download_web_private_kind(kind="private_domains")
        if private_web != False:
            web["domains"] = web["domains"] + private_web
    return web


@cached(cache=TTLCache(maxsize=10, ttl=360))
def download_web_kind(kind):
    url, code, private_code = get_cfg()
    try:
        req = requests.post(
            url + "/get/" + kind + "/list",
            headers={"Authorization": str(code)},
            allow_redirects=False,
            timeout=10,
        )
        if req.status_code == 200:
            return req.json()
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


@cached(cache=TTLCache(maxsize=10, ttl=360))
def download_web_private_kind(kind="private_domains"):
    url, code, private_code = get_cfg()
    try:
        req = requests.post(
            url + "/private_get/" + kind + "/list",
            headers={"Authorization": str(code)},
            json={"private_code": private_code},
            allow_redirects=False,
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


def get_new_kind(kind, username):
    web = get_web_kinds()
    if kind == "viewers":
        return web[kind]
    web = web[kind]
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


def get_new_kind_id(kind, username, id):
    web = get_web_kinds()
    if kind == "domains" or kind == "media":
        web = [d.copy() for d in web[kind] if "_" + username + "_" + d["id"] == id]
    else:
        web = [d.copy() for d in web[kind] if d["id"] == id]

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


def get_missing_resources(domain, username):
    missing_resources = {"videos": []}

    dom_videos = domain["create_dict"]["hardware"]["videos"]
    with app.app_context():
        sys_videos = list(r.table("videos").pluck("id").run(db.conn))
    sys_videos = [sv["id"] for sv in sys_videos]
    for v in dom_videos:
        if v not in sys_videos:
            resource = get_new_kind_id("videos", username, v)
            if resource != False:
                missing_resources["videos"].append(resource)
    ## graphics and interfaces missing
    return missing_resources


def formatDomains(data, user_id):
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
        path = get_user_path(user_id)
        for disk in d["create_dict"]["hardware"]["disks"]:
            if not disk["file"].startswith(path):
                disk["file"] = path + disk["file"]
    return new_data


def formatMedias(data, user_id):
    new_data = data.copy()
    for d in new_data:
        d.update(get_user_data(user_id))
        d["progress"] = {}
        d["status"] = "DownloadStarting"
        d["accessed"] = int(time.time())
        path = get_user_path(user_id)
        if d["url-isard"] == False:
            d["path"] = path + d["url-web"].split("/")[-1]
        else:
            d["path"] = path + d["url-isard"]
    return new_data


def get_user_path(user_id):
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
