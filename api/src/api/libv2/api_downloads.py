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
from uuid import uuid4

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
from .helpers import gen_new_mac, get_user_data


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
            # The id is no longer in updates server. We better reset it.
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
            if kind in ["domains", "media"]:
                downloads = []
                for d in req.json():
                    # we base in db everything to it's disk filename in case of domains and media
                    if kind == "domains" or kind == "media":
                        d["id"] = d.get("url-isard")
                    downloads.append(d)
                return downloads
            else:
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
        print("Error repository getkind private.\n" + str(e))
    return False


def get_new_kind(kind, username):
    web = get_web_kinds()
    if kind == "viewers":
        # viewers are only links to open in _blank new page to download
        return web[kind]

    web = web[kind]
    result = []
    if kind in ["domains", "media"]:
        # We have downloaded_id index in domains and media
        with app.app_context():
            dbb = list(
                r.table(kind)
                .get_all(username, index="user")
                .has_fields("url-isard")
                .filter(~r.row["url-isard"].eq(False))
                .run(db.conn)
            )
            dbb_dict = {d["url-isard"]: d for d in dbb}
        if kind == "media":
            with app.app_context():
                mbb = list(
                    r.table(kind)
                    .get_all(username, index="user")
                    .has_fields("url-web")
                    .filter(~r.row["url-web"].eq(False))
                    .run(db.conn)
                )
            dbb_dict = {**dbb_dict, **{d["url-web"]: d for d in mbb if d["url-web"]}}
        for w in web:
            if w["url-isard"] in dbb_dict.keys() or w["url-web"] in dbb_dict.keys():
                result.append(
                    {
                        **w,
                        **{
                            "id": dbb_dict[w["url-isard"]]["id"]
                            if w["url-isard"]
                            else dbb_dict[w["url-web"]]["id"],
                            "new": False,
                            "status": dbb_dict[w["url-isard"]]["status"]
                            if w["url-isard"]
                            else dbb_dict[w["url-web"]]["status"],
                            "progress": dbb_dict[w["url-isard"]].get("progress")
                            if w["url-isard"]
                            else dbb_dict[w["url-web"]].get("progress"),
                        },
                    }
                )
            else:
                result.append(
                    {
                        **w,
                        **{
                            "id": str(uuid4()),
                            "new": True,
                            "status": "Available",
                        },
                    }
                )

    else:
        # We still use old named ids
        with app.app_context():
            dbb = list(r.table(kind).run(db.conn))
        for w in web:
            if w["id"] in [d["id"] for d in dbb]:
                result.append(
                    {
                        **w,
                        **{
                            "new": False,
                            "status": "Downloaded",
                        },
                    }
                )
            else:
                result.append({**w, **{"new": True, "status": "Available"}})

    return result


def get_new_kind_id(kind, username, id):
    web = get_web_kinds()
    if kind == "domains" or kind == "media":
        web = [d.copy() for d in web[kind] if d["id"] == id]
    else:
        web = [d.copy() for d in web[kind] if d["id"] == id]

    if len(web) == 0:
        return False
    w = web[0].copy()

    if kind == "domains" or kind == "media":
        with app.app_context():
            dbb = list(
                r.table(kind)
                .get_all(w["id"], index="url-isard")
                .filter({"user": username})
                .run(db.conn)
            )
        if not len(dbb):
            with app.app_context():
                dbb = list(
                    r.table(kind)
                    .get_all(w["id"], index="url-web")
                    .filter({"user": username})
                    .run(db.conn)
                )
        if not len(dbb):
            w["id"] = str(uuid4())
            return w
        elif dbb[0].get("status") == "DownloadFailed":
            return dbb[0]
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
    new_data = []
    for d in data:
        d = get_domain_if_already_downloaded(d, user_id)
        d["progress"] = {}
        d["status"] = "DownloadStarting"
        d["detail"] = ""
        d["image"] = get_domain_stock_card(d["id"])
        d["accessed"] = int(time.time())
        d["hypervisors_pools"] = d["create_dict"]["hypervisors_pools"]
        d["guest_properties"] = default_guest_properties()
        interfaces = d["create_dict"]["hardware"]["interfaces"]
        d["create_dict"]["hardware"]["interfaces"] = {
            interface: gen_new_mac() for interface in interfaces
        }
        if d.get("options"):
            d.pop("options")
        d.update(get_user_data(user_id))
        new_data.append(d)
    return new_data


def get_domain_if_already_downloaded(data, user_id):
    with app.app_context():
        dbb = list(
            r.table("domains")
            .get_all(data.get("url-isard"), index="url-isard")
            .filter({"user": user_id})
            .run(db.conn)
        )
    if not len(dbb):
        return data
    return dbb[0]


def formatMedias(data, user_id):
    new_data = []
    for d in data:
        d = get_media_if_already_downloaded(d, user_id)
        d.update(get_user_data(user_id))
        d["progress"] = {}
        d["status"] = "DownloadStarting"
        d["accessed"] = int(time.time())
        new_data.append(d)
    return new_data


def get_media_if_already_downloaded(data, user_id):
    with app.app_context():
        dbb = list(
            r.table("media")
            .get_all(data.get("url-isard"), index="url-isard")
            .filter({"user": user_id})
            .run(db.conn)
        )
    if not len(dbb):
        with app.app_context():
            dbb = list(
                r.table("media")
                .get_all(data.get("url-web"), index="url-web")
                .filter({"user": user_id})
                .run(db.conn)
            )
    if not len(dbb):
        return data
    return dbb[0]
