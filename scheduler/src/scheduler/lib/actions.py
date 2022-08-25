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

import time

from rethinkdb import RethinkDB

from scheduler import app

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

from .api_client import ApiClient
from .exceptions import Error

api_client = ApiClient("api")
engine_client = ApiClient("engine")


class Actions:
    def stop_domains_kwargs():
        return {}

    def stop_domains():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").update(
                {"status": "Stopping"}
            ).run(db.conn)

    def stop_domains_without_viewer_kwargs():
        return {}

    def stop_domains_without_viewer():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").filter(
                {"viewer": {"client_since": False}}
            ).update({"status": "Stopping"}).run(db.conn)

    def stop_shutting_down_desktops_kwargs():
        return {}

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

    def check_ephimeral_status_kwargs():
        return {}

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

    def backup_database_kwargs():
        return {}

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

    def domain_qmp_notification_kwargs(**kwargs):
        return [
            {
                "id": "domain_id",
                "name": "Domain ID",
                "placeholder": "Domain to be notified",
                "element": "select",
                "ajax": {
                    "type": "POST",
                    "url": "/api/v3/admin/table/domains",
                    "url_id": None,
                    "data": {"pluck": ["id", "name"]},
                    "ids": "id",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "Message to be sent",
                "element": "textarea",
            },
        ]

    def domain_qmp_notification(**kwargs):
        engine_client.put(
            "/qmp/" + kwargs["domain_id"],
            {"action": "message", "kwargs": {"message": kwargs["message"]}},
        )

    def deployment_qmp_notification_kwargs(**kwargs):
        return [
            {
                "id": "deployment_id",
                "name": "Deployment ID",
                "placeholder": "Deployment desktops to be notified",
                "element": "select",
                "ajax": {
                    "type": "POST",
                    "url": "/api/v3/admin/table/deployments",
                    "url_id": None,
                    "data": {"pluck": ["id", "name"]},
                    "ids": "id",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "Message to be sent",
                "element": "textarea",
            },
        ]

    def deployment_qmp_notification(**kwargs):
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
            engine_client.put(
                "/qmp/" + domain_id,
                {"action": "message", "kwargs": {"message": kwargs["message"]}},
            )

    ### GPUS SPECIFICS
    def gpu_desktops_notify_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU phy id",
                "placeholder": "gpu physical_device",
                "element": "input",
                "ajax": {
                    "type": "GET",
                    "url": "/api/v3/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "physical_device",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "message to send to domains using this gpu",
                "element": "textarea",
            },
        ]

    def gpu_desktops_notify(**kwargs):
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            raise Error(
                "bad_request",
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!",
                traceback.format_exc(),
            )

        domains_ids = engine_client.get("/profile/gpu/started_domains/" + gpu_device)
        log.debug("-> We got " + str(domains_ids) + " domains id to be notified...")
        for domain_id in domains_ids:
            engine_client.put(
                "/qmp/" + domain_id,
                {"action": "message", "message": kwargs["message"]},
            )

    def gpu_desktops_destroy_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU phy id",
                "placeholder": "gpu physical_device to destroy domains using it",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/api/v3/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "physical_device",
                    "values": "name",
                },
            },
        ]

    def gpu_desktops_destroy(**kwargs):
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            raise Error(
                "bad_request",
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!",
                traceback.format_exc(),
            )

        domains_ids = engine_client.get("/profile/gpu/started_domains/" + gpu_device)
        log.debug("-> We got " + str(domains_ids) + " domains id to be destroyed...")

        for domain_id in domains_ids:
            try:
                answer = api_client.get("/desktop/stop/" + domain_id)
                log.debug("-> Stopping domain " + domain_id + ": " + str(answer))
            except:
                log.error(
                    "Exception when stopping domain "
                    + domain_id
                    + ": "
                    + traceback.format_exc()
                )

    def gpu_profile_set_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU phy ID",
                "placeholder": "GPU physical id to set profile",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/api/v3/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "physical_device",
                    "values": "name",
                },
            },
            {
                "id": "subitem_id",
                "name": "GPU profile ID",
                "placeholder": "GPU profile to be set",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/api/v3/admin/reservables/enabled/gpus",
                    "url_id": "item_id",
                    "data": {},
                    "ids": "id",
                    "values": "name",
                },
            },
        ]

    def gpu_profile_set(**kwargs):
        # Will set profile_id on selected card.
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

        answer = engine_client.get("/profile/gpu/" + gpu_device)
        if (
            answer.get("vgpu_profile")
            and answer["vgpu_profile"] == kwargs["subitem_id"].split("-")[-1]
        ):
            raise Error(
                "bad_request",
                "-> The actual profile at vgpu is the same we want to put: "
                + str(kwargs["subitem_id"])
                + ", so doing nothing.",
            )

        answer = engine_client.put(
            "/profile/gpu/" + gpu_device,
            {"profile_id": kwargs["subitem_id"]},
        )
        log.debug(
            "-> Profile "
            + kwargs["subitem_id"]
            + " set to gpu "
            + gpu_device
            + ": "
            + str(answer)
        )

    def domain_reservable_set_kwargs(**kwargs):
        return []

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
