#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import ipaddress
import os
import time
import traceback

import requests
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .._common.api_exceptions import Error
from .._common.storage_pool import DEFAULT_STORAGE_POOL_ID
from ..libv2.isardVpn import isardVpn
from .api_desktop_events import desktops_stop

isardVpn = isardVpn()

import socket
from subprocess import check_output

from .helpers import _check, generate_db_media


def get_hypervisors(status=None):
    with app.app_context():
        if not status:
            return list(r.table("hypervisors").run(db.conn))
        else:
            return list(r.table("hypervisors").filter({"status": status}).run(db.conn))


# os.environ['WG_HYPERS_NET']
# maximum_hypers=os.environ['WG_HYPERS_NET']
class ApiHypervisors:
    def __init__(self):
        None

    def hyper(
        self,
        hyper_id,
        hostname,
        port="2022",
        cap_disk=True,
        cap_hyper=True,
        enabled=False,
        description="Default hypervisor",
        browser_port="443",
        spice_port="80",
        isard_static_url=os.environ["DOMAIN"],
        isard_video_url=os.environ["DOMAIN"],
        isard_proxy_hyper_url="isard-hypervisor",
        isard_hyper_vpn_host="isard-vpn",
        nvidia_enabled=False,
        force_get_hyp_info=False,
        user="root",
        only_forced=False,
        min_free_mem_gb=0,
    ):
        data = {}

        # Check if it is in database
        with app.app_context():
            hypervisor = r.table("hypervisors").get(hyper_id).run(db.conn)
        if not hypervisor:
            result = self.add_hyper(
                hyper_id,
                hostname,
                port=port,
                cap_disk=cap_disk,
                cap_hyper=cap_hyper,
                enabled=False,
                browser_port=str(browser_port),
                spice_port=str(spice_port),
                isard_static_url=isard_static_url,
                isard_video_url=isard_video_url,
                isard_proxy_hyper_url=isard_proxy_hyper_url,
                isard_hyper_vpn_host=isard_hyper_vpn_host,
                nvidia_enabled=nvidia_enabled,
                description="Added via api",
                user=user,
                only_forced=only_forced,
                min_free_mem_gb=min_free_mem_gb,
            )
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            elif not self.check(result, "inserted"):
                raise Error("not_found", "Unable to add hypervisor")
        else:
            result = self.add_hyper(
                hyper_id,
                hostname,
                port=port,
                cap_disk=cap_disk,
                cap_hyper=cap_hyper,
                enabled=hypervisor["enabled"],
                browser_port=str(browser_port),
                spice_port=str(spice_port),
                isard_static_url=isard_static_url,
                isard_video_url=isard_video_url,
                isard_proxy_hyper_url=isard_proxy_hyper_url,
                isard_hyper_vpn_host=isard_hyper_vpn_host,
                nvidia_enabled=nvidia_enabled,
                force_get_hyp_info=force_get_hyp_info,
                description="Added via api",
                user=user,
                only_forced=only_forced,
                min_free_mem_gb=min_free_mem_gb,
            )
            # {'deleted': 0, 'errors': 0, 'inserted': 0, 'replaced': 1, 'skipped': 0, 'unchanged': 0}
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            if result["replaced"] and hypervisor["enabled"]:
                ## We should restart engine
                self.engine_restart()
            elif result["unchanged"] or not hypervisor["enabled"]:
                pass
            else:
                return {
                    "status": False,
                    "msg": "Unable to ssh-keyscan "
                    + hostname
                    + " port "
                    + str(port)
                    + ". Please ensure the port is opened in the hypervisor",
                    "data": data,
                }

            # Hypervisor already in database. Is asking for certs...
            # Lets check if it's fingerprint is already here
            # self.update_fingerprint(hostname,hypervisor['port'])

        data["certs"] = self.get_hypervisors_certs()

        return {"status": True, "msg": "Hypervisor added", "data": data}

    def add_hyper(
        self,
        hyper_id,
        hostname,
        port="2022",
        cap_disk=True,
        cap_hyper=True,
        enabled=False,
        description="Default hypervisor",
        browser_port="443",
        spice_port="80",
        isard_static_url=os.environ["DOMAIN"],
        isard_video_url=os.environ["DOMAIN"],
        isard_proxy_hyper_url="isard-hypervisor",
        isard_hyper_vpn_host="isard-vpn",
        nvidia_enabled=False,
        force_get_hyp_info=False,
        user="root",
        only_forced=False,
        min_free_mem_gb=0,
    ):
        # If we can't connect why we should add it? Just return False!
        if not self.update_fingerprint(hostname, port):
            return False

        hypervisor = {
            "capabilities": {"disk_operations": cap_disk, "hypervisor": cap_hyper},
            "description": description,
            "detail": "",
            "enabled": enabled,
            "hostname": hostname,
            "isard_hyper_vpn_host": isard_hyper_vpn_host,
            "hypervisors_pools": ["default"],
            "id": hyper_id,
            "port": port,
            "status": "Offline",
            "status_time": False,
            "uri": "",
            "user": user,
            "viewer": {
                "static": isard_static_url,  # isard-static nginx
                "proxy_video": isard_video_url,  # Video Proxy Host
                "spice_ext_port": spice_port,  # 80
                "html5_ext_port": browser_port,  # 443
                "proxy_hyper_host": isard_proxy_hyper_url,  # Viewed from isard-video
            },
            "info": {},
            "only_forced": only_forced,
            "nvidia_enabled": nvidia_enabled,
            "force_get_hyp_info": force_get_hyp_info,
            "min_free_mem_gb": min_free_mem_gb,
            "storage_pools": [DEFAULT_STORAGE_POOL_ID],
        }

        with app.app_context():
            result = (
                r.table("hypervisors")
                .insert(hypervisor, conflict="update")
                .run(db.conn)
            )
        return result

    def enable_hyper(self, hyper_id):
        with app.app_context():
            if not r.table("hypervisors").get(hyper_id).run(db.conn):
                return {"status": False, "msg": "Hypervisor not found", "data": {}}

        with app.app_context():
            r.table("hypervisors").get(hyper_id).update({"enabled": True}).run(db.conn)

        self.engine_restart()
        return {"status": True, "msg": "Hypervisor enabled", "data": {}}

    def remove_hyper(self, hyper_id, restart=True):
        self.stop_hyper_domains(hyper_id)
        with app.app_context():
            if not r.table("hypervisors").get(hyper_id).run(db.conn):
                return {"status": False, "msg": "Hypervisor not found", "data": {}}

        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"enabled": False, "status": "Deleting"}
            ).run(db.conn)

        now = int(time.time())
        while int(time.time()) - now < 20:
            time.sleep(1)
            with app.app_context():
                if not r.table("hypervisors").get(hyper_id).run(db.conn):
                    return {
                        "status": True,
                        "msg": "Removed from database",
                        "data": {},
                    }

        return {
            "status": False,
            "msg": "Hypervisor yet in database, timeout waiting to delete",
            "data": {},
        }

    def stop_hyper_domains(self, hyper_id):
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all("Started", index="status")
                .filter({"hyp_started": hyper_id})["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, force=True, wait_seconds=0)

    def engine_restart(self):
        try:
            requests.get("http://isard-engine:5000/restart")
        except:
            ## The procedure just restarts engine, so no answer is expected:
            pass

    def hypervisors_max_networks(self):
        ### There will be much more hypervisor networks available than dhcpsubnets
        # nparent = ipaddress.ip_network(os.environ['WG_MAIN_NET'], strict=False)
        # max_hypers=len(list(nparent.subnets(new_prefix=os.environ['WG_HYPERS_NET'])))

        ## So get the max from dhcpsubnets
        nparent = ipaddress.ip_network(os.environ["WG_GUESTS_NETS"], strict=False)
        max_hypers = len(
            list(nparent.subnets(new_prefix=int(os.environ["WG_GUESTS_DHCP_MASK"])))
        )
        return max_hypers

    def get_hypervisors_certs(self):
        certs = {}
        path = "/viewers"
        for subdir, dirs, files in os.walk(path):
            for file in files:
                with open(path + "/" + file, "r") as f:
                    certs[file] = f.read()
        with open("/sshkeys/id_rsa.pub", "r") as id_rsa:
            certs["id_rsa.pub"] = id_rsa.read()
        return certs

    def update_fingerprint(self, hostname, port):
        path = "/sshkeys/known_hosts"
        if not os.path.exists(path):
            os.mknod(path)

        try:
            print("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path)
            # Possible OS Command injection
            check_output(
                ("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path),
                text=True,
            ).strip()
        except:
            log.error("Could not remove ssh key for [" + hostname + "]" + str(port))
            return False
        try:
            # Possible OS Command injection
            check_output(
                (
                    "ssh-keygen",
                    "-R",
                    "[" + socket.gethostbyname(hostname) + "]:" + str(port),
                    "-f",
                    path,
                ),
                text=True,
            ).strip()
        except:
            log.error("Could not remove ssh key for [" + hostname + "]" + str(port))
            return False

        try:
            # Possible OS Command injection 
            new_fingerprint = check_output(
                ("ssh-keyscan", "-p", port, "-t", "rsa", "-T", "3", hostname), text=True
            ).strip()
        except:
            log.error("Could not get ssh-keyscan for " + hostname + ":" + str(port))
            return False

        with open(path, "a") as f:
            new_fingerprint = new_fingerprint + "\n"
            f.write(new_fingerprint)
            log.warning("Keys added for hypervisor " + hostname + ":" + str(port))

        return True

    def update_guest_addr(self, domain_id, data):
        with app.app_context():
            if not _check(
                r.table("domains").get(domain_id).update(data).run(db.conn), "replaced"
            ):
                raise Error(
                    "internal_server",
                    "Unable to update guest_addr",
                    traceback.format_exc(),
                )

    def update_wg_address(self, mac, data):
        with app.app_context():
            try:
                domain_id = list(
                    r.table("domains").get_all(mac, index="wg_mac").run(db.conn)
                )[0]["id"]
                r.table("domains").get(domain_id).update(data).run(db.conn)
                return domain_id
            except:
                # print(traceback.format_exc())
                return False

    def get_hypervisor_vpn(self, hyper_id):
        return isardVpn.vpn_data("hypers", "config", "", hyper_id)

    def get_vlans(self):
        with app.app_context():
            interfaces = r.table("interfaces").run(db.conn)
        return [v.split("br-")[1] for v in interfaces if v["net"].startswith("br-")]

    def add_vlans(self, vlans):
        for vlan in vlans:
            new_vlan = {
                "id": "v" + vlan,
                "name": "Vlan " + vlan,
                "description": "Infrastructure vlan",
                "ifname": "br-" + vlan,
                "kind": "bridge",
                "model": "virtio",
                "net": "br-" + vlan,
                "qos_id": False,
                "allowed": {
                    "roles": ["admin"],
                    "categories": False,
                    "groups": False,
                    "users": False,
                },
            }
            with app.app_context():
                r.db("isard").table("interfaces").insert(new_vlan).run(db.conn)

    def update_media_found(self, medias):
        with app.app_context():
            db_medias = list(r.table("media").pluck("path_downloaded").run(db.conn))
        db_medias_paths = [
            dbm["path_downloaded"] for dbm in db_medias if dbm.get("path_downloaded")
        ]

        medias_paths = [m[0] for m in medias]
        new = list(set(medias_paths) - set(db_medias_paths))

        for n in new:
            for m in medias:
                if m[0] == n:
                    with app.app_context():
                        db_medias = (
                            r.table("media")
                            .insert(generate_db_media(m[0], m[1]))
                            .run(db.conn)
                        )
                        log.info("Added new media from hypervisor: " + m[0])
                        print("Added new media from hypervisor: " + m[0])

    def update_disks_found(self, disks):
        with app.app_context():
            db_disks = list(
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck({"create_dict": {"hardware": {"disks"}}})
                .run(db.conn)
            )
        db_disks_paths = [
            d[0]["file"]
            for d in [
                ds["create_dict"]["hardware"]["disks"]
                for ds in db_disks
                if ds["create_dict"]["hardware"].get("disks", False)
                and len(ds["create_dict"]["hardware"]["disks"])
            ]
        ]

        disks_paths = [d[0] for d in disks]
        new = list(set(disks_paths) - set(db_disks_paths))

        for n in new:
            for m in disks:
                if m[0] == n:
                    with app.app_context():
                        db_medias = (
                            r.table("media")
                            .insert(generate_db_media(m[0], m[1]))
                            .run(db.conn)
                        )
                        log.info("Added new disk from hypervisor: " + m[0])
                        print("Added new disk from hypervisor: " + m[0])

    def delete_media(self, medias_paths):
        for mp in medias_paths:
            with app.app_context():
                db_medias = list(
                    r.table("media")
                    .filter({"path_downloaded": mp})
                    .delete()
                    .run(db.conn)
                )

    def check(self, dict, action):
        # ~ These are the actions:
        # ~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if not dict:
            return False
        if dict[action] or dict["unchanged"]:
            return True
        if not dict["errors"]:
            return True
        return False

    def domains_stop(self, hyp_id=False):
        with app.app_context():
            if hyp_id == False:
                desktops_ids = list(
                    r.table("domains")
                    .get_all("Started", index="status")
                    .filter({"viewer": {"client_since": False}})["id"]
                    .run(db.conn)["replaced"]
                )
            else:
                desktops_ids = list(
                    r.table("domains")
                    .get_all("Started", index="status")
                    .filter(
                        {
                            "hyp_started": hyp_id,
                            "viewer": {"client_since": False},
                        }
                    )["id"]
                    .run(db.conn)["replaced"]
                )
        desktops_stop(desktops_ids, force=True, wait_seconds=0)
        return True

    def assign_gpus(self):
        with app.app_context():
            hypers = [
                h["id"]
                for h in r.table("hypervisors")
                .filter({"status": "Online"})
                .run(db.conn)
            ]
            r.table("gpus").update({"physical_device": None}).run(db.conn)
            physical_devices = list(
                r.table("vgpus")
                .pluck("id", "brand", "hyp_id", {"info": "model"})
                .run(db.conn)
            )
            physical_devices = [pd for pd in physical_devices if pd["hyp_id"] in hypers]
            log.debug(
                "Matching hypers with cards found by engine: " + str(physical_devices)
            )
            for pd in physical_devices:
                gpus = list(
                    r.table("gpus")
                    .get_all([pd["brand"], pd["info"]["model"]], index="brand-model")
                    .filter({"physical_device": None})
                    .run(db.conn)
                )
                if len(gpus):
                    r.table("gpus").get(gpus[0]["id"]).update(
                        {"physical_device": pd["id"]}
                    ).run(db.conn)

    def get_hyper_status(self, hyper_id):
        with app.app_context():
            status = (
                r.table("hypervisors")
                .get(hyper_id)
                .pluck("status", "only_forced")
                .run(db.conn)
            )
        return status
