#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

import json
import time

import requests
from rethinkdb import RethinkDB

from scheduler import app

from .exceptions import Error

r = RethinkDB()
import os
import pickle
import tarfile
import traceback

from .flask_rethink import RDB
from .log import log

db = RDB(app)
db.init_app(app)

from datetime import datetime


def _put(url, data):

    try:
        resp = requests.put(url, json=data)
        if resp.status_code == 200:
            return json.loads(resp.text)
        raise Error("bad_request", "Bad request while contacting scheduler service")
    except:
        raise Error(
            "internal_server",
            "Could not contact scheduler service",
            traceback.format_exc(),
        )


def _get(url):

    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            return json.loads(resp.text)
        raise Error("bad_request", "Bad request while contacting scheduler service")
    except:
        raise Error(
            "internal_server",
            "Could not contact scheduler service",
            traceback.format_exc(),
        )


class Actions:
    def stop_domains():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").update(
                {"status": "Stopping"}
            ).run(db.conn)

    def stop_domains_without_viewer():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").filter(
                {"viewer": {"client_since": False}}
            ).update({"status": "Stopping"}).run(db.conn)

    def stop_shutting_down_desktops():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Shutting-down", index="status")
                .pluck("id", "accessed")
                .run(db.conn)
            )
            t = time.time()
            for d in domains:
                if d["accessed"] + 1.9 * 60 < t:  # 2 minutes * 60 seconds
                    r.table("domains").get(d["id"]).update(
                        {"status": "Stopping", "accessed": time.time()}
                    ).run(db.conn)

    def check_ephimeral_status():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Started", index="status")
                .has_fields("ephimeral")
                .pluck("id", "ephimeral", "history_domain")
                .run(db.conn)
            )
            t = time.time()
            for d in domains:
                if (
                    d["history_domain"][0]["when"] + int(d["ephimeral"]["minutes"]) * 60
                    < t
                ):
                    r.table("domains").get(d["id"]).update(
                        {"status": d["ephimeral"]["action"]}
                    ).run(db.conn)

    def backup_database():
        id = "isard_backup_" + datetime.now().strftime("%Y%m%d-%H%M%S")
        path = "./backups/"
        os.makedirs(path, exist_ok=True)
        with app.app_context():
            dict = {
                "id": id,
                "filename": id + ".tar.gz",
                "path": path,
                "description": "",
                "when": time.time(),
                "data": {},
                "status": "Initializing",
                "version": r.table("config")
                .get(1)
                .pluck("version")
                .run(db.conn)["version"],
            }
        with app.app_context():
            r.table("backups").insert(dict).run(db.conn)
        skip_tables = [
            "backups",
            "disk_operations",
        ]
        isard_db = {}
        with app.app_context():
            r.table("backups").get(id).update({"status": "Loading tables"}).run(db.conn)
            for table in r.table_list().run(db.conn):
                if table not in skip_tables:
                    isard_db[table] = list(r.table(table).run(db.conn))
                    dict["data"][table] = r.table(table).info().run(db.conn)
                    r.table("backups").get(id).update(
                        {"data": {table: r.table(table).count().run(db.conn)}}
                    ).run(db.conn)
        with app.app_context():
            dict = r.table("backups").get(id).run(db.conn)
            r.table("backups").get(id).update({"status": "Dumping to file"}).run(
                db.conn
            )
        with open(path + id + ".rethink", "wb") as isard_rethink_file:
            pickle.dump(dict, isard_rethink_file)
        with open(path + id + ".json", "wb") as isard_db_file:
            pickle.dump(isard_db, isard_db_file)
        with app.app_context():
            r.table("backups").get(id).update({"status": "Compressing"}).run(db.conn)
        with tarfile.open(path + id + ".tar.gz", "w:gz") as tar:
            tar.add(path + id + ".json", arcname=os.path.basename(path + id + ".json"))
            tar.add(
                path + id + ".rethink", arcname=os.path.basename(path + id + ".rethink")
            )
            tar.close()
        try:
            os.remove(path + id + ".json")
            os.remove(path + id + ".rethink")
        except OSError:
            pass
        with app.app_context():
            r.table("backups").get(id).update({"status": "Finished creating"}).run(
                db.conn
            )

    def domain_qmp_notification(**kwargs):
        # "kwargs": {
        #     "domain_id": "_local_default_..." ,
        #     "message": "Test"

        # } ,
        base_url = "http://isard-engine:5000"
        try:
            _put(
                base_url + "/qmp/" + kwargs["domain_id"],
                {"action": "message", "kwargs": {"message": kwargs["message"]}},
            )
        except:
            log.error("Exception when sending qmp message: " + traceback.format_exc())
            raise Error("internal_server", "Error when sending qmp message")

    def deployment_qmp_notification(**kwargs):
        # "kwargs": {
        #     "deployment_id": "_local_default_..." ,
        #     "message": "Test"
        # } ,
        base_url = "http://isard-engine:5000"
        deployment = r.table("deployments").get(kwargs["deployment_id"]).run(db.conn)
        if not deployment:
            log.error("Deployment id " + kwargs["deployment_id"] + " not found")
            raise Error(
                "not_found", "Deployment id " + kwargs["deployment_id"] + " not found"
            )
        domains_ids = (
            r.table("domains")
            .get_all(kwargs["deployment_id"], index="tag")["id"]
            .coerce_to("array")
            .run(db.conn)
        )
        for domain_id in domains_ids:
            try:
                _put(
                    base_url + "/qmp/" + domain_id,
                    {"action": "message", "kwargs": {"message": kwargs["message"]}},
                )
            except:
                log.error(
                    "Exception when sending qmp message: " + traceback.format_exc()
                )
                raise Error("internal_server", "Error when sending qmp message")

    ### GPUS SPECIFICS
    def gpu_desktops_notify(**kwargs):
        base_url = "http://isard-engine:5000"
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            log.error(
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!"
            )
            return
        try:
            domains_ids = _get(base_url + "/profile/gpu/started_domains/" + gpu_device)
        except:
            log.error(
                "Could not contact engine api to get desktops to notify! "
                + traceback.format_exc()
            )
            raise Error(
                "internal_server", "Could not contact engine to get desktops to destroy"
            )
        log.debug("-> We got " + str(domains_ids) + " domains id to be notified")
        for domain_id in domains_ids:
            data = {"domain_id": domain_id, "message": kwargs["message"]}
            try:
                _put(
                    base_url + "/qmp/" + domain_id,
                    {"action": "message", "message": kwargs["message"]},
                )
            except:
                log.error(
                    "Exception when sending qmp message: " + traceback.format_exc()
                )
                raise Error("internal_server", "Error when sending qmp message")

    def gpu_desktops_destroy(**kwargs):
        base_url = "http://isard-engine:5000"
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            log.error(
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!"
            )
            return
        try:
            domains_ids = _get(base_url + "/profile/gpu/started_domains/" + gpu_device)
        except:
            log.error(
                "Could not contact engine api to get desktops to destroy! "
                + traceback.format_exc()
            )
            raise Error(
                "internal_server", "Could not contact engine to get desktops to destroy"
            )

        log.debug("-> We got " + str(domains_ids) + " domains id to be destroyed")
        base_url = "http://isard-api:5000/api/v3"
        for domain_id in domains_ids:
            try:
                answer = _get(
                    base_url + "/desktop/stop/" + domain_id,
                    {},
                )
                log.debug("-> Stopping domain " + domain_id + ": " + str(answer))
            except:
                log.error(
                    "Exception when stopping domain "
                    + domain_id
                    + ": "
                    + traceback.format_exc()
                )

    def gpu_profile_set(**kwargs):
        # Will set profile_id on selected card.
        base_url = "http://isard-engine:5000"
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            log.error(
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!"
            )
            return
        try:
            answer = _get(base_url + "/profile/gpu/" + gpu_device)
            if (
                answer.get("vgpu_profile")
                and answer["vgpu_profile"] == kwargs["subitem_id"].split("-")[-1]
            ):
                log.debug(
                    "-> The actual profile at vgpu is the same we want to put: "
                    + str(kwargs["subitem_id"])
                    + ", so doing nothing."
                )
                return
        except:
            log.error("Exception when getting gpu profile: " + traceback.format_exc())
        try:
            answer = _put(
                base_url + "/profile/gpu/" + gpu_device,
                {"profile_id": kwargs["subitem_id"]},
            )
            log.debug("-> Setting profile answer: " + str(answer))
        except:
            log.error("Exception when setting gpu profile: " + traceback.format_exc())

    def domain_reservable_set(**kwargs):
        with app.app_context():
            if kwargs["item_type"] == "deployment":
                domains = (
                    r.table("domains")
                    .get_all(kwargs["item_id"], index="tag")
                    .run(db.conn)
                )
                domains_ids = [d["id"] for d in domains]
            if kwargs["item_type"] == "desktop":
                domains_ids = [
                    r.table("domains")
                    .get(kwargs["item_id"])
                    .pluck("id")
                    .run(db.conn)["id"]
                ]
        log.debug("-> We got " + str(domains_ids) + " domains id to update booking_id")
        if len(domains_ids):
            with app.app_context():
                r.table("domains").get_all(r.args(domains_ids), index="id").update(
                    {"booking_id": kwargs["booking_id"]}
                ).run(db.conn)

    """
    BULK ACTIONS
    """

    def bulk_action(table, tbl_filter, tbl_update):
        with app.app_context():
            log.info(
                "BULK ACTION: Table {}, Filter {}, Update {}".format(
                    table, filter, update
                )
            )
            r.table(table).filter(filter).update(update).run(db.conn)
            r.table(table).filter({"status": "Unknown"}).update(
                {"status": "Stopping"}
            ).run(db.conn)
