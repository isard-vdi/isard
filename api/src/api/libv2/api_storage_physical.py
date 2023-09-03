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
import logging as log
import random
import time
import traceback
import uuid

from rethinkdb import RethinkDB

from api import app

from .. import socketio
from .._common.api_exceptions import Error
from .._common.api_rest import ApiRest
from .api_desktop_events import desktops_stop_all
from .maintenance import Maintenance

r = RethinkDB()


from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def build_path_from_storage(s):
    return s["directory_path"] + "/" + s["id"] + "." + s["type"]


def phy_storage_list(table):
    if table == "domains":
        with app.app_context():
            storage = list(
                r.table("storage")
                .pluck("id", "directory_path", "type", "status")
                .run(db.conn)
            )
            storage_physical = list(r.table("storage_physical_domains").run(db.conn))
            domains = list(
                r.table("domains")
                .pluck("id", "status", {"create_dict": {"hardware": {"disks": True}}})
                .run(db.conn)
            )
        # To speedup the search
        storage_dict = {}
        for s in storage:
            storage_dict[build_path_from_storage(s)] = {
                "path": build_path_from_storage(s),
                "status": s["status"],
            }

        domains_dict = {}
        for d in domains:
            for disk in d["create_dict"]["hardware"]["disks"]:
                if disk.get("storage_id"):
                    # If storage_id is not in storage table, then it is a file
                    if not storage_dict.get(disk.get("storage_id")):
                        # The storage_id is not in storage table. Must not happen.
                        continue
                    else:
                        domains_dict[storage_dict[disk.get("storage_id")]["path"]] = {
                            "d": d["id"],
                            "ds": d["status"],
                        }
                else:
                    domains_dict[disk.get("file")] = {"d": d["id"], "ds": d["status"]}

        storage_physical_parents_dict = {}
        for sp in storage_physical:
            if not sp["parents"]:
                continue
            for p in sp["parents"]:
                storage_physical_parents_dict[p] = True

        return [
            {
                **sp,
                **{
                    "domains": domains_dict[sp["path"]]["d"]
                    if domains_dict.get(sp["path"])
                    else False,
                    "domains_status": False
                    if not domains_dict.get(sp["path"])
                    else domains_dict[sp["path"]]["ds"],
                    "storage_status": False
                    if not storage_dict.get(sp["path"])
                    else storage_dict[sp["path"]]["status"],
                    "storage": True if storage_dict.get(sp["path"]) else False,
                    "haschilds": storage_physical_parents_dict.get(sp["path"], False),
                },
            }
            for sp in storage_physical
        ]
    if table == "media":
        return [
            {**sp, **{"domains": "NaN"}}
            for sp in list(r.table("storage_physical_media").run(db.conn))
        ]


def phy_storage_reset_domains(data):
    with app.app_context():
        instorage = list(r.table("storage")["qemu-img-info"]["filename"].run(db.conn))
    # data = [d for d in data if d["path"] not in instorage]
    socketio.emit(
        "storage_migration_progress",
        json.dumps(
            {
                "type": "info",
                "description": "Starting...",
                "current": 0,
                "total": data,
            }
        ),
        namespace="/administrators",
        room="admins",
    )
    i = 0
    for d in data:
        d["tomigrate"] = True if d["path"] not in instorage else False
        if d.get("qemu-img-info").get("format") == "qcow2":
            qemu_img_info = d.pop("qemu-img-info", None)
            d["migrate_data"] = {
                "directory_path": "/".join(d["path"].split("/")[:3]),
                "id": str(uuid.uuid4()),
                "parent": qemu_img_info.get("backing-filename")
                if qemu_img_info
                else None,
                "parents": d["parents"],
                "correct-chain": d["correct-chain"],
                "qemu-img-info": qemu_img_info,
                "status": "ready",
                "type": qemu_img_info.get("format") if qemu_img_info else "Unknown",
                "user_id": None,
                "status_logs": [{"status": "ready", "time": int(time.time())}],
            }
            socketio.emit(
                "storage_migration_progress",
                json.dumps(
                    {
                        "type": "info",
                        "description": "Correctly updated.",
                        "current": i + 1,
                        "total": len(data),
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
            i += 1
    with app.app_context():
        r.table("storage_physical_domains").delete().run(db.conn)
        r.table("storage_physical_domains").insert(data).run(db.conn)


def phy_storage_reset_media(data):
    with app.app_context():
        instorage = list(r.table("media")["path_downloaded"].run(db.conn))
    data = [d for d in data if d["path"] not in instorage]
    with app.app_context():
        r.table("storage_physical_media").delete().run(db.conn)
        r.table("storage_physical_media").insert(data).run(db.conn)


def phy_storage_update(table, data):
    with app.app_context():
        return (
            r.table("storage_physical_" + table)
            .insert(data, conflict="update")
            .run(db.conn)
        )


def phy_storage_delete(table, path_id):
    with app.app_context():
        return (
            r.table("storage_physical_" + table)
            .filter({"path": path_id})
            .delete()
            .run(db.conn)
        )


def phy_add_to_storage(
    path_id,
    user_id,
    timestamp,
):
    try:
        qemu_img_info = ApiRest(
            service="isard-storage", base_url=_phy_internal_storage_host()
        ).post("/storage/disk/info", {"path_id": path_id})
        if qemu_img_info.get("format") in ["qcow2"]:
            new_disk = {
                "directory_path": "/".join(path_id.split("/")[:3]),
                "id": str(uuid.uuid4()),
                "parent": qemu_img_info.get("backing-filename"),
                "qemu-img-info": qemu_img_info,
                "status": "ready",
                "type": qemu_img_info.get("format"),
                "user_id": user_id,
                "status_logs": [
                    {"status": "created", "time": timestamp - 1},
                    {"status": "ready", "time": timestamp},
                ],
            }
            with app.app_context():
                r.table("storage").insert(new_disk).run(db.conn)
            return new_disk
        else:
            return None
    except:
        log.error(
            "Error migrating disk to storage: "
            + path_id
            + ": "
            + traceback.format_exc()
        )
        return None


def phy_storage_upgrade_to_storage(data, user_id):
    # Set manteinance
    Maintenance.enabled = True

    # Stop domains started before upgrading? What happens with servers?
    with app.app_context():
        forceds = r.table("hypervisors").pluck("id", "only_forced").run(db.conn)
        r.table("hypervisors").update({"only_forced": True}).run(db.conn)
    time.sleep(2)
    desktops_stop_all()
    time.sleep(2)
    i = 0
    socketio.emit(
        "storage_migration_progress",
        json.dumps(
            {
                "type": "info",
                "description": "Starting...",
                "current": i + 1,
                "total": len(data["paths"]),
            }
        ),
        namespace="/administrators",
        room="admins",
    )

    with app.app_context():
        domains = list(
            r.table("domains")
            .pluck(
                "id", "user", "accessed", {"create_dict": {"hardware": {"disks": True}}}
            )
            .run(db.conn)
        )
    # To speedup the search
    domains_dict = {}
    timestamp_dict = {}
    for d in domains:
        for disk in d["create_dict"]["hardware"]["disks"]:
            domains_dict[disk.get("storage_id", disk.get("file"))] = d["user"]
            timestamp_dict[disk.get("storage_id", disk.get("file"))] = d.get(
                "accessed", int(time.time())
            )

    errors = []
    for path_id in data["paths"]:
        new_disk = phy_add_to_storage(
            path_id,
            domains_dict.get(path_id, user_id),
            timestamp_dict.get(path_id, int(time.time())),
        )
        if not new_disk:
            errors.append("disk path " + str(path_id) + ": bad format.")
            socketio.emit(
                "storage_migration_progress",
                json.dumps(
                    {
                        "type": "error",
                        "description": "Bad disk format for path " + str(path_id),
                        "current": i,
                        "total": len(data["paths"]),
                    }
                ),
                namespace="/administrators",
                room="admins",
            )
            continue
        with app.app_context():
            domains_to_be_updated = (
                r.table("domains")
                .get_all(path_id, index="disk_paths")
                .pluck("id", "create_dict", "hardware")
                .run(db.conn)
            )
        for domain in domains_to_be_updated:
            disks = []
            hardware_disks = []
            for disk in domain["create_dict"]["hardware"]["disks"]:
                if disk["file"] == path_id:
                    disk = {
                        "extension": new_disk.get("qemu-img-info", {}).get("format"),
                        "storage_id": new_disk["id"],
                    }
                    hardware_disk = {
                        "extension": new_disk.get("qemu-img-info", {}).get("format"),
                        "file": new_disk["directory_path"]
                        + "/"
                        + new_disk["id"]
                        + "."
                        + new_disk["type"],
                        "parent": new_disk.get("qemu-img-info", {}).get(
                            "backing-filename"
                        ),
                        "path_selected": new_disk["directory_path"],
                        "storage_id": new_disk["id"],
                    }
                disks.append(disk)
                hardware_disks.append(hardware_disk)
            domain["create_dict"]["hardware"]["disks"] = disks
            domain["hardware"]["disks"] = hardware_disks
            with app.app_context():
                r.table("domains").get(domain["id"]).update(domain).run(db.conn)
        phy_storage_delete("domains", path_id)
        socketio.emit(
            "storage_migration_progress",
            json.dumps(
                {
                    "type": "info",
                    "description": "Correctly updated.",
                    "current": i + 1,
                    "total": len(data["paths"]),
                }
            ),
            namespace="/administrators",
            room="admins",
        )
        i += 1
    # take over manteinance
    with app.app_context():
        for hyper in forceds:
            r.table("hypervisors").get(hyper["id"]).update(
                {"only_forced": hyper["only_forced"]}
            ).run(db.conn)
    Maintenance.enabled = False
    return errors


def _phy_internal_storage_host():
    with app.app_context():
        viewers = list(
            r.table("hypervisors")
            .filter({"status": "Online"})
            .pluck("viewer")["viewer"]
            .run(db.conn)
        )
    if not len(viewers):
        raise Error("precondition_required", "No hypervisors currently online")
    if "isard-hypervisor" in [v["proxy_hyper_host"] for v in viewers]:
        return "http://isard-storage:5000/storage/api"
    data = viewers[random.randint(0, len(viewers) - 1)]
    return (
        "https://" + data["proxy_video"] + ":" + data["html5_ext_port"] + "/storage/api"
    )


def phy_storage_host():
    with app.app_context():
        viewers = list(
            r.table("hypervisors")
            .filter({"status": "Online"})
            .pluck("viewer")["viewer"]
            .run(db.conn)
        )
    if not len(viewers):
        raise Error("precondition_required", "No hypervisors currently online")
    data = viewers[random.randint(0, len(viewers) - 1)]
    return (
        "https://" + data["proxy_video"] + ":" + data["html5_ext_port"] + "/storage/api"
    )
