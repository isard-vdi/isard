#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import datetime
import ipaddress
import os
import time
import traceback

import pytz
from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from isardvdi_common.api_exceptions import Error
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from rethinkdb.errors import ReqlNonExistenceError

from ..libv2.caches import get_category_storage_pools, get_default_storage_pool
from ..libv2.isardVpn import isardVpn
from .api_desktop_events import desktops_stop

isardVpn = isardVpn()

import socket
from subprocess import check_output

from .helpers import _check, generate_db_media
from .validators import _validate_item


class ApiHypervisors:
    def get_hypervisors(
        self,
        status=None,
    ):
        query = r.table("hypervisors")
        if status:
            query = query.filter({"status": status})
        query = query.merge(
            lambda hyper: {
                "desktops_started": r.table("domains")
                .get_all(hyper["id"], index="hyp_started")
                .count(),
                "gpus": r.table("vgpus")
                .filter({"hyp_id": hyper["id"]})["id"]
                .coerce_to("array"),
                "physical_gpus": r.table("gpus")
                .filter(lambda gpu: gpu["physical_device"].ne(None))["physical_device"]
                .coerce_to("array"),
            }
        )

        with app.app_context():
            data = list(query.run(db.conn))
        return data

    def get_orchestrator_hypervisors(
        self,
        hyp_id=None,
    ):
        query = r.table("hypervisors")

        if hyp_id:
            query = query.get(hyp_id)

        query = query.pluck(
            "id",
            "status",
            "only_forced",
            "buffering_hyper",
            "destroy_time",
            "stats",
            "orchestrator_managed",
            "min_free_mem_gb",
            "gpu_only",
        )
        query = query.merge(
            lambda hyper: {
                "desktops_started": r.table("domains")
                .get_all(hyper["id"], index="hyp_started")
                .filter({"server": False})
                .count()
            }
        )
        if hyp_id:
            try:
                with app.app_context():
                    data = query.run(db.conn)
            except ReqlNonExistenceError:
                raise Error(
                    "not_found", "Hypervisor with ID " + hyp_id + " does not exist."
                )
            return {
                **{
                    "only_forced": False,
                    "buffering_hyper": False,
                    "destroy_time": None,
                    "stats": {},
                    "orchestrator_managed": False,
                    "min_free_mem_gb": 0,
                    "gpu_only": False,
                },
                **self._get_hypervisors_gpus(hyp_id, data["status"]),
                **data,
            }
        else:
            with app.app_context():
                data = list(query.run(db.conn))
            return [
                {
                    **{
                        "only_forced": False,
                        "buffering_hyper": False,
                        "destroy_time": None,
                        "stats": {},
                        "orchestrator_managed": False,
                        "min_free_mem_gb": 0,
                        "gpu_only": False,
                    },
                    **self._get_hypervisors_gpus(d["id"], d["status"]),
                    **d,
                }
                for d in data
            ]

    def _gpu_card_data_integrity(self, desktops_started, hyper_id, card_id=None):
        if desktops_started:
            # Check if desktop is started in more than one mdev
            if len(list(set(desktops_started))) != len(desktops_started):
                app.logger.error(
                    (
                        "GPU CHECKS: " + "card " + card_id
                        if card_id
                        else "hypervisor "
                        + hyper_id
                        + " has the same started desktop in more than one GPU mdev!"
                    ),
                )
                desktops_started = list(
                    set(desktops_started)
                )  # FIXME: This should not happen! But it does... so we remove duplicates

            # Check if desktops in vgpus table in the correct status
            with app.app_context():
                if r.table("domains").get_all(
                    r.args(desktops_started), index="id"
                ).filter(
                    lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                        domain["status"]
                    )
                ).count().run(
                    db.conn
                ) != len(
                    desktops_started
                ):
                    app.logger.error(
                        (
                            "GPU CHECKS: " + "card " + card_id
                            if card_id
                            else "hypervisor "
                            + hyper_id
                            + " has started mdev desktops not in Started or Shutting-down status!"
                        ),
                    )

            # Should we check if domains table gpu desktops are set in hyper?

        return desktops_started

    def _get_hypervisors_gpus(self, hyp_id, hyp_status):
        data = {"bookings_end_time": None, "gpus": []}
        if hyp_status != "Online":
            return data
        with app.app_context():
            cards = list(
                r.table("vgpus")
                .filter({"hyp_id": hyp_id})
                .pluck("id", "vgpu_profile", "brand", "model", "mdevs")
                .run(db.conn)
            )
        if not len(cards):
            return data

        hypervisor_gpu_desktops_started = []
        for card in cards:
            active_profile = card.get("vgpu_profile")
            if not active_profile:
                continue
            card_desktops_started = [
                mdev["domain_started"]
                for mdev in [
                    card["mdevs"][active_profile][k]
                    for k in card["mdevs"][active_profile].keys()
                    if card["mdevs"][active_profile][k]["domain_started"]
                ]
            ]
            card_desktops_started = self._gpu_card_data_integrity(
                card_desktops_started, hyp_id, card["id"]
            )
            data["gpus"].append(
                {
                    "id": card["id"],
                    "total_units": len(card["mdevs"][active_profile].keys()),
                    "used_units": len(card_desktops_started),
                    "free_units": len(card["mdevs"][active_profile].keys())
                    - len(card_desktops_started),
                    "brand": card["brand"],
                    "model": card["model"],
                    "profile": active_profile,
                }
            )
            hypervisor_gpu_desktops_started += card_desktops_started

        # Get max end time of bookings in hypervisor
        with app.app_context():
            bookings_ids = (
                r.table("domains")
                .get_all(r.args(hypervisor_gpu_desktops_started), index="id")
                .filter(lambda dom: dom["booking_id"] != False)
                .pluck("booking_id")["booking_id"]
                .coerce_to("array")
                .run(db.conn)
            )
        if not bookings_ids:
            data["bookings_end_time"] = None
        else:
            try:
                with app.app_context():
                    data["bookings_end_time"] = (
                        r.table("bookings")
                        .get_all(r.args(bookings_ids))
                        .pluck("end")
                        .order_by(r.desc("end"))
                        .limit(1)["end"]
                        .nth(0)
                        .run(db.conn)
                    ).isoformat()
            except:
                app.logger.error(
                    "GPU CHECKS: Traceback in getting bookings end time for hypervisor "
                    + hyp_id
                    + ": "
                    + traceback.format_exc(),
                )
                data["bookings_end_time"] = None
        return data

    def get_orchestrator_managed_hypervisors(self):
        hypervisors = (
            r.table("hypervisors")
            .filter({"orchestrator_managed": True})
            .pluck("id", "info", "stats", "status", "destroy_time", "status_time")
            .merge(
                lambda hyper: {
                    "desktops_started": r.table("domains")
                    .get_all(hyper["id"], index="hyp_started")
                    .filter({"server": False})
                    .count()
                }
            )
        )
        with app.app_context():
            return list(hypervisors.run(db.conn))

    def hyper(
        self,
        hyper_id,
        hostname,
        port="2022",
        cap_disk=True,
        cap_hyper=True,
        enabled=False,
        description="Added via api",
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
        min_free_gpu_mem_gb=0,
        storage_pools=[DEFAULT_STORAGE_POOL_ID],
        buffering_hyper=False,
        gpu_only=False,
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
                description=description,
                user=user,
                only_forced=only_forced,
                min_free_mem_gb=min_free_mem_gb,
                min_free_gpu_mem_gb=min_free_gpu_mem_gb,
                storage_pools=storage_pools,
                buffering_hyper=buffering_hyper,
                gpu_only=gpu_only,
            )
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            elif not self.check(result, "inserted"):
                raise Error("not_found", "Unable to add hypervisor")
        else:
            # Second time will try to enable itself
            if hypervisor.get("enabled"):
                with app.app_context():
                    r.table("hypervisors").get(hyper_id).update({"enabled": False}).run(
                        db.conn
                    )
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
                description=description,
                user=user,
                only_forced=only_forced,
                min_free_mem_gb=min_free_mem_gb,
                min_free_gpu_mem_gb=min_free_gpu_mem_gb,
                storage_pools=storage_pools,
                buffering_hyper=buffering_hyper,
                gpu_only=gpu_only,
            )
            # {'deleted': 0, 'errors': 0, 'inserted': 0, 'replaced': 1, 'skipped': 0, 'unchanged': 0}
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            if result["unchanged"] or result["replaced"] or not hypervisor["enabled"]:
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
        min_free_gpu_mem_gb=0,
        storage_pools=[DEFAULT_STORAGE_POOL_ID],
        buffering_hyper=False,
        gpu_only=False,
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
                "static": (
                    isard_static_url + ":" + os.environ.get("HTTPS_PORT")
                    if os.environ.get("HTTPS_PORT")
                    else isard_static_url
                ),  # isard-static nginx
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
            "min_free_gpu_mem_gb": min_free_gpu_mem_gb,
            "storage_pools": storage_pools,
            "buffering_hyper": buffering_hyper,
            "gpu_only": gpu_only,
        }

        hypervisor = _validate_item("hypervisors", hypervisor)

        with app.app_context():
            result = (
                r.table("hypervisors")
                .insert(hypervisor, conflict="update")
                .run(db.conn)
            )
        return result

    def enable_hyper(self, hyper_id, enable=True):
        with app.app_context():
            if not r.table("hypervisors").get(hyper_id).run(db.conn):
                return {"status": False, "msg": "Hypervisor not found", "data": {}}

        with app.app_context():
            r.table("hypervisors").get(hyper_id).update({"enabled": enable}).run(
                db.conn
            )
        if enable:
            return {"status": True, "msg": "Hypervisor enabled", "data": {}}
        else:
            return {"status": True, "msg": "Hypervisor disabled", "data": {}}

    def remove_hyper(self, hyper_id, restart=True):
        try:
            with app.app_context():
                r.table("hypervisors").get(hyper_id).update({"forced_hyp": True}).run(
                    db.conn
                )
            self.stop_hyper_domains(hyper_id)
            with app.app_context():
                r.table("hypervisors").get(hyper_id).update({"enabled": False}).run(
                    db.conn
                )
            time.sleep(1)
            with app.app_context():
                r.table("hypervisors").get(hyper_id).update({"status": "Deleting"}).run(
                    db.conn
                )
        except:
            return {"status": False, "msg": "Hypervisor not found", "data": {}}

        # Wait for engine to remove hyper thread
        timeout = 10
        while timeout:
            time.sleep(1)
            with app.app_context():
                hyper = r.table("hypervisors").get(hyper_id).run(db.conn)
            if not hyper:
                return {
                    "status": True,
                    "msg": "Hypervisor removed by engine from database",
                    "data": {},
                }
            timeout -= 1

        with app.app_context():
            r.table("hypervisors").get(hyper_id).delete().run(db.conn)
        return {
            "status": True,
            "msg": "Hypervisor force removed from database",
            "data": {},
        }

    def stop_hyper_domains(self, hyper_id):
        with app.app_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(hyper_id, index="hyp_started")["id"]
                .run(db.conn)
            )
        desktops_stop(desktops_ids, force=True, wait_seconds=0)

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
        # Keys generated by engine. Engine alpine previous to 3.19 uses rsa.
        if os.path.exists("/sshkeys/id_rsa.pub"):
            with open("/sshkeys/id_rsa.pub", "r") as id_rsa:
                certs["id_rsa.pub"] = id_rsa.read()
                return certs
        # Keys generated by engine. Engine alpine 3.19 uses ed25519.
        if os.path.exists("/sshkeys/id_ed25519.pub"):
            with open("/sshkeys/id_ed25519.pub", "r") as id_rsa:
                certs["id_rsa.pub"] = id_rsa.read()
                return certs
        raise Error(
            "internal_server",
            "Unable to get certificates",
            traceback.format_exc(),
        )

    def update_fingerprint(self, hostname, port):
        path = "/sshkeys/known_hosts"
        if not os.path.exists(path):
            os.mknod(path)

        try:
            print("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path)
            check_output(
                ("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path),
                text=True,
            ).strip()
        except:
            log.error("Could not remove ssh key for [" + hostname + "]" + str(port))
            return False
        try:
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
        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all(mac, index="wg_mac")
                    .filter({"kind": "desktop"})
                    .filter(
                        lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                            domain["status"]
                        )
                    )
                    .run(db.conn)
                )
            if not len(domains):
                app.logger.error(
                    f"UPDATE_WG_ADDR: Domain with mac {mac} not found or not started"
                )
                return False
            if len(domains) > 1:
                app.logger.error(
                    f"UPDATE_WG_ADDR: More than one started domain {' '.join([d['id'] for d in domains])} with mac {mac} found! This should not happen!"
                )
                return False

            app.logger.info(
                f"UPDATE_WG_ADDR: Updating wg_address {data.get('viewer',{}).get('guest_ip')} for domain {domains[0]['id']}"
            )
            with app.app_context():
                r.table("domains").get(domains[0]["id"]).update(data).run(db.conn)
            return domains[0]["id"]
        except:
            app.logger.error(
                f"UPDATE_WG_ADDR: Error updating wg_address for domain {domains[0]['id']}: {traceback.format_exc()}"
            )
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

    def assign_gpus(self):
        with app.app_context():
            hypers = [
                h["id"]
                for h in r.table("hypervisors")
                .filter({"status": "Online"})
                .run(db.conn)
            ]
        with app.app_context():
            r.table("gpus").update({"physical_device": None}).run(db.conn)
        with app.app_context():
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
            with app.app_context():
                gpus = list(
                    r.table("gpus")
                    .get_all([pd["brand"], pd["info"]["model"]], index="brand-model")
                    .filter({"physical_device": None})
                    .run(db.conn)
                )
            if len(gpus):
                with app.app_context():
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

    def set_hyper_deadrow_time(self, hyper_id, reset=False):
        with app.app_context():
            hypervisor = r.table("hypervisors").get(hyper_id).run(db.conn)
        if not hypervisor:
            raise Error(
                "not_found", "Hypervisor with ID " + hyper_id + " does not exist."
            )

        if not hypervisor.get("orchestrator_managed"):
            raise Error(
                "precondition_required",
                "Hypervisor with ID " + hyper_id + " is not managed by orchestrator.",
            )

        # Check if hypervisor is in dead row to remove it
        if reset:
            if hypervisor.get("only_forced") and hypervisor.get("destroy_time"):
                with app.app_context():
                    r.table("hypervisors").get(hyper_id).update(
                        {"only_forced": False, "destroy_time": None}
                    ).run(db.conn)
                return True
            else:
                raise Error(
                    "precondition_required",
                    "Hypervisor with ID " + hyper_id + " not in dead row.",
                )

        # Check if hypervisor is already in dead row return actual destroy time
        # NOTE: This should not happen, but if it does, we return the actual destroy time
        if hypervisor.get("only_forced") and hypervisor.get("destroy_time"):
            return {"destroy_time": hypervisor.get("destroy_time")}

        # Check max desktops timeout, if set
        # If not set, we will use a default 12 hours timeout (12*60=720)
        with app.app_context():
            desktops_max_timeout = list(
                r.table("desktops_priority")
                .has_fields({"shutdown": {"max": True}})
                .order_by(r.desc(lambda priority: priority["shutdown"]["max"]))
                .run(db.conn)
            )
        if not len(desktops_max_timeout):
            # If no max timeout is set, we use a default 12 hours timeout (12*60=720)
            desktops_max_timeout = 720
        else:
            desktops_max_timeout = desktops_max_timeout[0]["shutdown"]["max"]

        # Get time now + desktops_max_timeout
        d = datetime.datetime.utcnow() + datetime.timedelta(
            minutes=desktops_max_timeout
        )
        dtz = d.replace(tzinfo=pytz.UTC).isoformat()

        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"only_forced": True, "destroy_time": dtz}
            ).run(db.conn)
        return {"destroy_time": dtz}

    def set_hyper_orchestrator_managed(self, hyper_id, reset=False):
        try:
            with app.app_context():
                hypervisor = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .update({"destroy_time": None, "orchestrator_managed": not reset})
                    .run(db.conn)
                )
            return True
        except:
            raise Error(
                "not_found", "Hypervisor with ID " + hyper_id + " does not exist."
            )

    def get_hyper_mountpoints(self, hyper_id):
        with app.app_context():
            status = (
                r.table("hypervisors").get(hyper_id).pluck("mountpoints").run(db.conn)
            )
        if not status:
            raise Error(
                "not_found",
                "Mountpoints information still not available",
            )
        return status

    @cached(cache=TTLCache(maxsize=200, ttl=10))
    def get_hyper_started_domains(self, hyper_id):
        with app.app_context():
            domains = list(
                r.table("domains")
                .get_all(hyper_id, index="hyp_started")
                .filter({"status": "Started", "kind": "desktop"})
                .pluck(
                    [
                        "id",
                        "name",
                        {
                            "create_dict": {
                                "hardware": ["vcpus", "memory"],
                            }
                        },
                        "username",
                        "category",
                        "group",
                        "server",
                        "persistent",
                    ]
                )
                .map(
                    lambda domain: domain.merge(
                        {
                            "category_name": r.table("categories")
                            .get(domain["category"])
                            .pluck("name")["name"]
                            .default(""),
                            "group_name": r.table("groups")
                            .get(domain["group"])
                            .pluck("name")["name"]
                            .default(""),
                        }
                    )
                )
                .run(db.conn)
            )
        return domains


@cached(cache=TTLCache(maxsize=50, ttl=10))
def check_storage_pool_availability(category_id=None):
    # Hypervisors online
    with app.app_context():
        hypers_online = list(
            r.table("hypervisors")
            .filter({"status": "Online", "enabled": True, "only_forced": False})
            .pluck("storage_pools")
            .run(db.conn)
        )
    if not len(hypers_online):
        raise Error(
            "precondition_required",
            "No storage pool hypervisor available in system",
            description_code="no_storage_pool_available",
        )

    # Check category storage pools for category
    storage_pools = get_category_storage_pools(category_id)
    ## As only one category per pool is allowed. This should not happen.
    if len(storage_pools) > 1:
        raise Error(
            "internal_server",
            f"More than one storage pool available for category {category_id}",
            description_code="no_storage_pool_available",
        )
    if not len(storage_pools) or category_id is None:
        # Check if default storage pool is available
        default_storage_pool = get_default_storage_pool()
        if not default_storage_pool.get("enabled"):
            raise Error(
                "precondition_required",
                "No storage pool available",
                description_code="no_storage_pool_available",
            )
        storage_pools = [DEFAULT_STORAGE_POOL_ID]
    storage_pool = storage_pools[0]
    for hyper in hypers_online:
        if storage_pool in hyper.get("storage_pools", []):
            return True
    raise Error(
        "precondition_required",
        f"No hypervisors available for category {category_id} with storage pool {storage_pool}",
        description_code="no_storage_pool_available",
    )
