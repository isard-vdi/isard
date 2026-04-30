#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Pau Abril Iranzo
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


import datetime
import ipaddress
import logging as log
import os
import re
import socket
import time
import traceback
from subprocess import check_output

import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.isard_vpn import IsardVpn
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.hypervisor import HypervisorModel
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError

_get_desktops_max_timeout_cache: TTLCache = TTLCache(maxsize=200, ttl=100)
_get_hyper_started_domains_cache: TTLCache = TTLCache(maxsize=200, ttl=10)
_check_create_storage_pool_availability_cache: TTLCache = TTLCache(maxsize=50, ttl=10)
_check_virt_storage_pool_availability_cache: TTLCache = TTLCache(maxsize=50, ttl=10)


class HypervisorsProcessed(RethinkSharedConnection):
    """_From api/libv2/api_hypervisors.py ApiHypervisors_"""

    @classmethod
    def get_hypervisors(cls, status=None):
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

        with cls._rdb_context():
            data = list(query.run(cls._rdb_connection))
        return data

    @classmethod
    def get_orchestrator_hypervisors(cls, hyp_id=None):
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
                with cls._rdb_context():
                    data = query.run(cls._rdb_connection)
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
                **cls._get_hypervisors_gpus(hyp_id, data["status"]),
                **data,
            }
        else:
            with cls._rdb_context():
                data = list(query.run(cls._rdb_connection))
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
                    **cls._get_hypervisors_gpus(d["id"], d["status"]),
                    **d,
                }
                for d in data
            ]

    @classmethod
    def _gpu_card_data_integrity(cls, desktops_started, hyper_id, card_id=None):
        if desktops_started:
            # Check if desktop is started in more than one mdev
            if len(list(set(desktops_started))) != len(desktops_started):
                log.error(
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
            with cls._rdb_context():
                if r.table("domains").get_all(
                    r.args(desktops_started), index="id"
                ).filter(
                    lambda domain: r.expr(["Started", "Shutting-down"]).contains(
                        domain["status"]
                    )
                ).count().run(
                    cls._rdb_connection
                ) != len(
                    desktops_started
                ):
                    log.error(
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

    @classmethod
    def _get_hypervisors_gpus(cls, hyp_id, hyp_status):
        data = {"bookings_end_time": None, "gpus": []}
        if hyp_status != "Online":
            return data
        with cls._rdb_context():
            cards = list(
                r.table("vgpus")
                .filter({"hyp_id": hyp_id})
                .pluck("id", "vgpu_profile", "brand", "model", "mdevs")
                .run(cls._rdb_connection)
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
            card_desktops_started = cls._gpu_card_data_integrity(
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
        with cls._rdb_context():
            bookings_ids = (
                r.table("domains")
                .get_all(r.args(hypervisor_gpu_desktops_started), index="id")
                .filter(lambda dom: dom["booking_id"] != False)
                .pluck("booking_id")["booking_id"]
                .coerce_to("array")
                .run(cls._rdb_connection)
            )
        if not bookings_ids:
            data["bookings_end_time"] = None
        else:
            try:
                with cls._rdb_context():
                    data["bookings_end_time"] = (
                        r.table("bookings")
                        .get_all(r.args(bookings_ids))
                        .pluck("end")
                        .order_by(r.desc("end"))
                        .limit(1)["end"]
                        .nth(0)
                        .run(cls._rdb_connection)
                    ).isoformat()
            except Exception:
                log.error(
                    "GPU CHECKS: Traceback in getting bookings end time for hypervisor "
                    + hyp_id
                    + ": "
                    + traceback.format_exc(),
                )
                data["bookings_end_time"] = None
        return data

    @classmethod
    def get_orchestrator_managed_hypervisors(cls):
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
        with cls._rdb_context():
            return list(hypervisors.run(cls._rdb_connection))

    @classmethod
    def hyper(
        cls,
        hyper_id,
        hostname,
        port="2022",
        cap_disk=True,
        cap_hyper=True,
        enabled=False,
        description="Added via api",
        browser_port="443",
        spice_port="80",
        isard_static_url=os.environ.get("DOMAIN"),
        isard_video_url=os.environ.get("DOMAIN"),
        isard_proxy_hyper_url="isard-hypervisor",
        isard_hyper_vpn_host="isard-vpn",
        nvidia_enabled=False,
        force_get_hyp_info=False,
        user="root",
        only_forced=False,
        min_free_mem_gb=0,
        min_free_gpu_mem_gb=0,
        storage_pools=[DEFAULT_STORAGE_POOL_ID],
        enabled_storage_pools=[DEFAULT_STORAGE_POOL_ID],
        virt_pools=[],
        enabled_virt_pools=[],
        buffering_hyper=False,
        gpu_only=False,
        hugepages_info=None,
    ):
        data = {}

        if hugepages_info is not None:
            data["hugepages_info"] = hugepages_info

        # Check if it is in database
        with cls._rdb_context():
            hypervisor = r.table("hypervisors").get(hyper_id).run(cls._rdb_connection)
        if not hypervisor:
            result = cls.add_hyper(
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
                enabled_storage_pools=enabled_storage_pools,
                virt_pools=virt_pools,
                enabled_virt_pools=enabled_virt_pools,
                buffering_hyper=buffering_hyper,
                gpu_only=gpu_only,
            )
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            elif not cls.check(result, "inserted"):
                raise Error("not_found", "Unable to add hypervisor")
        else:
            # Second time will try to enable itself
            if hypervisor.get("enabled"):
                with cls._rdb_context():
                    r.table("hypervisors").get(hyper_id).update({"enabled": False}).run(
                        cls._rdb_connection
                    )
            result = cls.add_hyper(
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
                enabled_storage_pools=enabled_storage_pools,
                virt_pools=virt_pools,
                enabled_virt_pools=enabled_virt_pools,
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

        if hugepages_info is not None:
            with cls._rdb_context():
                r.table("hypervisors").get(hyper_id).update(
                    {"hugepages_info": hugepages_info}
                ).run(cls._rdb_connection)

        data["certs"] = cls.get_hypervisors_certs()

        return {"status": True, "msg": "Hypervisor added", "data": data}

    @classmethod
    def add_hyper(
        cls,
        hyper_id,
        hostname,
        port="2022",
        cap_disk=True,
        cap_hyper=True,
        enabled=False,
        description="Default hypervisor",
        browser_port="443",
        spice_port="80",
        isard_static_url=os.environ.get("DOMAIN"),
        isard_video_url=os.environ.get("DOMAIN"),
        isard_proxy_hyper_url="isard-hypervisor",
        isard_hyper_vpn_host="isard-vpn",
        nvidia_enabled=False,
        force_get_hyp_info=False,
        user="root",
        only_forced=False,
        min_free_mem_gb=0,
        min_free_gpu_mem_gb=0,
        storage_pools=[DEFAULT_STORAGE_POOL_ID],
        enabled_storage_pools=[DEFAULT_STORAGE_POOL_ID],
        virt_pools=[],
        enabled_virt_pools=[],
        buffering_hyper=False,
        gpu_only=False,
    ):
        # If we can't connect why we should add it? Just return False!
        if not cls.update_fingerprint(hostname, port):
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
            "virt_pools": virt_pools,
            "buffering_hyper": buffering_hyper,
            "gpu_only": gpu_only,
        }

        # exclude_unset prevents the model's defaults (vpn=None,
        # cap_status={...}, info={}, mountpoints=[], prev_status=[],
        # stats=None, viewer_status=None) from leaking into the upsert.
        # With conflict="update", any explicitly-dumped key overwrites
        # the existing value — so vpn=None would wipe the live
        # wireguard peer config that isard-vpn populated, sending the
        # hypervisor into a 428 retry loop on every restart.
        hypervisor = HypervisorModel(**hypervisor).model_dump(
            mode="json", exclude_unset=True
        )
        hypervisor["enabled_virt_pools"] = (
            enabled_virt_pools or virt_pools or storage_pools
        )
        hypervisor["enabled_storage_pools"] = enabled_storage_pools or storage_pools

        with cls._rdb_context():
            result = (
                r.table("hypervisors")
                .insert(hypervisor, conflict="update")
                .run(cls._rdb_connection)
            )
        return result

    @classmethod
    def update_vpn_field(cls, hyper_id, vpn_data):
        """Merge vpn_data into the hypervisor's vpn sub-document."""
        with cls._rdb_context():
            r.table("hypervisors").get(hyper_id).update(
                {"vpn": r.row["vpn"].default({}).merge(vpn_data)}
            ).run(cls._rdb_connection)

    @staticmethod
    def _normalize_gpu_model(gpu_name, vgpu_profiles=None):
        """Dash-free model name derivation (mirror of gpu_discovery.normalize_gpu_model).

        Handles both classic time-sliced profile suffixes ("-4Q", "-96Q") and
        MIG-backed slot-notation suffixes ("-1-3Q", "-4-48Q") so GPUs like the
        RTX PRO 6000 Blackwell DC produce a dash-free model name.
        """
        if vgpu_profiles:
            profile_name = vgpu_profiles[0]["name"]
            match = re.match(r"^(.+?)(-\d+-\d+[ABCQ]|-\d+[ABCQ])$", profile_name)
            if match:
                model_part = match.group(1)
            else:
                model_part = profile_name.rsplit("-", 1)[0]
            return (
                model_part.replace("NVIDIA ", "")
                .replace("GRID ", "")
                .replace(" ", "")
                .replace("-", "")
            )
        return gpu_name.replace("NVIDIA ", "").replace(" ", "").replace("-", "")

    @classmethod
    def enable_hyper(cls, hyper_id, enable=True):
        with cls._rdb_context():
            if not r.table("hypervisors").get(hyper_id).run(cls._rdb_connection):
                return {"status": False, "msg": "Hypervisor not found", "data": {}}

        with cls._rdb_context():
            r.table("hypervisors").get(hyper_id).update({"enabled": enable}).run(
                cls._rdb_connection
            )
        if enable:
            return {"status": True, "msg": "Hypervisor enabled", "data": {}}
        else:
            return {"status": True, "msg": "Hypervisor disabled", "data": {}}

    @classmethod
    def update_hyper_numa_topology(cls, hyper_id, numa_topology):
        if not isinstance(numa_topology, dict):
            return
        with cls._rdb_context():
            r.table("hypervisors").get(hyper_id).update(
                {"numa_topology": numa_topology}
            ).run(cls._rdb_connection)

    @classmethod
    def remove_hyper(cls, hyper_id, restart=True):
        try:
            with cls._rdb_context():
                r.table("hypervisors").get(hyper_id).update({"forced_hyp": True}).run(
                    cls._rdb_connection
                )
            cls.stop_hyper_domains(hyper_id)
            with cls._rdb_context():
                r.table("hypervisors").get(hyper_id).update({"enabled": False}).run(
                    cls._rdb_connection
                )
            time.sleep(1)
            with cls._rdb_context():
                r.table("hypervisors").get(hyper_id).update({"status": "Deleting"}).run(
                    cls._rdb_connection
                )
        except Exception:
            return {"status": False, "msg": "Hypervisor not found", "data": {}}

        # Wait for engine to remove hyper thread
        timeout = 10
        while timeout:
            time.sleep(1)
            with cls._rdb_context():
                hyper = r.table("hypervisors").get(hyper_id).run(cls._rdb_connection)
            if not hyper:
                return {
                    "status": True,
                    "msg": "Hypervisor removed by engine from database",
                    "data": {},
                }
            timeout -= 1

        with cls._rdb_context():
            r.table("hypervisors").get(hyper_id).delete().run(cls._rdb_connection)
        return {
            "status": True,
            "msg": "Hypervisor force removed from database",
            "data": {},
        }

    @classmethod
    def stop_hyper_domains(cls, hyper_id):
        with cls._rdb_context():
            desktops_ids = list(
                r.table("domains")
                .get_all(hyper_id, index="hyp_started")["id"]
                .run(cls._rdb_connection)
            )
        DesktopEvents.desktops_stop(desktops_ids, force=True, update_accessed=False)

    @classmethod
    def hypervisors_max_networks(cls):
        ### There will be much more hypervisor networks available than dhcpsubnets
        # nparent = ipaddress.ip_network(os.environ['WG_MAIN_NET'], strict=False)
        # max_hypers=len(list(nparent.subnets(new_prefix=os.environ['WG_HYPERS_NET'])))

        ## So get the max from dhcpsubnets
        nparent = ipaddress.ip_network(os.environ["WG_GUESTS_NETS"], strict=False)
        max_hypers = len(
            list(nparent.subnets(new_prefix=int(os.environ["WG_GUESTS_DHCP_MASK"])))
        )
        return max_hypers

    @classmethod
    def get_hypervisors_certs(cls):
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

    @classmethod
    def update_fingerprint(cls, hostname, port):
        # Block loopback/link-local hostnames to prevent SSRF
        import ipaddress
        import socket as _socket

        try:
            results = _socket.getaddrinfo(
                hostname, None, _socket.AF_UNSPEC, _socket.SOCK_STREAM
            )
            for _, _, _, _, sockaddr in results:
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_loopback or ip.is_link_local:
                    raise Error(
                        "bad_request",
                        f"Hostname {hostname} resolves to loopback/link-local",
                    )
        except _socket.gaierror:
            raise Error("bad_request", f"DNS resolution failed for {hostname}")

        path = "/sshkeys/known_hosts"
        if not os.path.exists(path):
            os.mknod(path)

        try:
            print("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path)
            check_output(
                ("ssh-keygen", "-R", "[" + hostname + "]:" + str(port), "-f", path),
                text=True,
            ).strip()
        except Exception:
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
        except Exception:
            log.error("Could not remove ssh key for [" + hostname + "]" + str(port))
            return False

        try:
            new_fingerprint = check_output(
                ("ssh-keyscan", "-p", port, "-t", "rsa", "-T", "3", hostname), text=True
            ).strip()
        except Exception:
            log.error("Could not get ssh-keyscan for " + hostname + ":" + str(port))
            return False

        with open(path, "a") as f:
            new_fingerprint = new_fingerprint + "\n"
            f.write(new_fingerprint)
            log.warning("Keys added for hypervisor " + hostname + ":" + str(port))

        return True

    @classmethod
    def update_guest_addr(cls, domain_id, data):
        with cls._rdb_context():
            r.table("domains").get(domain_id).update(data).run(cls._rdb_connection)

    @classmethod
    @cached(
        cache=TTLCache(maxsize=25, ttl=10),
        key=lambda cls, mac, data: f"{mac}:{data.get('viewer', {}).get('guest_ip', '')}",
    )
    def update_wg_address(cls, mac, data):
        domain_id = Caches.get_domain_id_from_wg_mac(mac)
        if not domain_id:
            raise Error(
                "not_found",
                "Domain with mac " + mac + " not found in wireguard cache",
            )
        try:
            with cls._rdb_context():
                r.table("domains").get(domain_id).update(data).run(cls._rdb_connection)
            return domain_id
        except ReqlNonExistenceError:
            raise Error(
                "not_found",
                "Domain with ID " + domain_id + " not found in database",
            )
        except Exception:
            raise Error(
                "internal_server",
                "Unable to update wireguard address",
                traceback.format_exc(),
            )

    @classmethod
    def get_hypervisor_vpn(cls, hyper_id):
        return IsardVpn.vpn_data("hypers", "config", "", hyper_id)

    @classmethod
    def get_vlans(cls):
        with cls._rdb_context():
            interfaces = r.table("interfaces").run(cls._rdb_connection)
        return [v.split("br-")[1] for v in interfaces if v["net"].startswith("br-")]

    @classmethod
    def add_vlans(cls, vlans):
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
            with cls._rdb_context():
                r.db("isard").table("interfaces").insert(new_vlan).run(
                    cls._rdb_connection
                )

    @classmethod
    def update_media_found(cls, medias):
        with cls._rdb_context():
            db_medias = list(
                r.table("media").pluck("path_downloaded").run(cls._rdb_connection)
            )
        db_medias_paths = [
            dbm["path_downloaded"] for dbm in db_medias if dbm.get("path_downloaded")
        ]

        medias_paths = [m[0] for m in medias]
        new = list(set(medias_paths) - set(db_medias_paths))

        for n in new:
            for m in medias:
                if m[0] == n:
                    with cls._rdb_context():
                        # TODO(move-api-hypervisors-to-common): generate_db_media will always fail
                        db_medias = (
                            r.table("media")
                            .insert(Helpers.generate_db_media(m[0], m[1]))
                            .run(cls._rdb_connection)
                        )
                log.info("Added new media from hypervisor: " + m[0])
                print("Added new media from hypervisor: " + m[0])

    @classmethod
    def update_disks_found(cls, disks):
        with cls._rdb_context():
            db_disks = list(
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck({"create_dict": {"hardware": {"disks"}}})
                .run(cls._rdb_connection)
            )
        db_disks_paths = [
            d[0].get("file")
            for d in [
                ds["create_dict"]["hardware"]["disks"]
                for ds in db_disks
                if ds["create_dict"]["hardware"].get("disks", False)
                and len(ds["create_dict"]["hardware"]["disks"])
            ]
            if d and d[0].get("file")
        ]

        disks_paths = [d[0] for d in disks]
        new = list(set(disks_paths) - set(db_disks_paths))

        for n in new:
            for m in disks:
                if m[0] == n:
                    with cls._rdb_context():
                        # TODO(move-api-hypervisors-to-common): generate_db_media will always fail
                        db_medias = (
                            r.table("media")
                            .insert(Helpers.generate_db_media(m[0], m[1]))
                            .run(cls._rdb_connection)
                        )
                    log.info("Added new disk from hypervisor: " + m[0])

    @classmethod
    def delete_media(cls, medias_paths):
        for mp in medias_paths:
            with cls._rdb_context():
                db_medias = list(
                    r.table("media")
                    .filter({"path_downloaded": mp})
                    .delete()
                    .run(cls._rdb_connection)
                )

    @classmethod
    def check(cls, dict, action):
        # ~ These are the actions:
        # ~ {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        if not dict:
            return False
        if dict[action] or dict["unchanged"]:
            return True
        if not dict["errors"]:
            return True
        return False

    @classmethod
    def assign_gpus(cls):
        with cls._rdb_context():
            hypers = [
                h["id"]
                for h in r.table("hypervisors")
                .filter({"status": "Online"})
                .run(cls._rdb_connection)
            ]
        with cls._rdb_context():
            r.table("gpus").update({"physical_device": None}).run(cls._rdb_connection)
        with cls._rdb_context():
            physical_devices = list(
                r.table("vgpus")
                .pluck("id", "brand", "hyp_id", {"info": "model"})
                .run(cls._rdb_connection)
            )
        physical_devices = [pd for pd in physical_devices if pd["hyp_id"] in hypers]
        log.debug(
            "Matching hypers with cards found by engine: " + str(physical_devices)
        )
        for pd in physical_devices:
            with cls._rdb_context():
                gpus = list(
                    r.table("gpus")
                    .get_all([pd["brand"], pd["info"]["model"]], index="brand-model")
                    .filter({"physical_device": None})
                    .run(cls._rdb_connection)
                )
            if len(gpus):
                with cls._rdb_context():
                    r.table("gpus").get(gpus[0]["id"]).update(
                        {"physical_device": pd["id"]}
                    ).run(cls._rdb_connection)

    @classmethod
    def get_hyper_status(cls, hyper_id):
        with cls._rdb_context():
            hyper = (
                r.table("hypervisors")
                .get(hyper_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if hyper is None:
            raise Error(
                "not_found",
                f"Hypervisor {hyper_id} not found",
                description_code="hypervisor_not_found",
            )
        return {
            "status": hyper.get("status"),
            "only_forced": hyper.get("only_forced"),
        }

    @classmethod
    def set_hyper_deadrow_time(cls, hyper_id, reset=False):
        with cls._rdb_context():
            hypervisor = r.table("hypervisors").get(hyper_id).run(cls._rdb_connection)
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
                with cls._rdb_context():
                    r.table("hypervisors").get(hyper_id).update(
                        {"only_forced": False, "destroy_time": None}
                    ).run(cls._rdb_connection)
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

        with cls._rdb_context():
            furthest_shutdown = (
                r.table("domains")
                .get_all(hyper_id, index="hyp_started")
                .filter(
                    lambda domain: domain.has_fields("server_autostart")
                    .not_()
                    .or_(domain["server_autostart"].ne(True))
                )
                .pluck("scheduled")["scheduled"]["shutdown"]
                .max()
                .default(None)
                .run(cls._rdb_connection)
            )
        if furthest_shutdown:
            d = datetime.datetime.strptime(furthest_shutdown, "%Y-%m-%dT%H:%M%z")
        else:
            # If no runnng desktops in the hypervisor, we use as default desktops max timeout
            desktops_max_timeout = cls.get_desktops_max_timeout()
            d = datetime.datetime.utcnow() + datetime.timedelta(
                minutes=desktops_max_timeout
            )

        dtz = d.replace(tzinfo=pytz.UTC).isoformat()

        with cls._rdb_context():
            r.table("hypervisors").get(hyper_id).update(
                {"only_forced": True, "destroy_time": dtz}
            ).run(cls._rdb_connection)
        return {"destroy_time": dtz}

    @classmethod
    @cached(cache=_get_desktops_max_timeout_cache)
    def get_desktops_max_timeout(cls):
        with cls._rdb_context():
            return (
                r.table("desktops_priority")
                .has_fields({"shutdown": {"max": True}})
                .order_by(r.desc(lambda priority: priority["shutdown"]["max"]))
                .nth(0)["shutdown"]["max"]
                .default(720)  # Default to 12 hours if no max timeout found (12*60=720)
                .run(cls._rdb_connection)
            )

    @classmethod
    def clear_get_desktops_max_timeout_cache(cls):
        _get_desktops_max_timeout_cache.clear()

    @classmethod
    def set_hyper_orchestrator_managed(cls, hyper_id, reset=False):
        try:
            with cls._rdb_context():
                hypervisor = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .update({"destroy_time": None, "orchestrator_managed": not reset})
                    .run(cls._rdb_connection)
                )
            return True
        except Exception:
            raise Error(
                "not_found", "Hypervisor with ID " + hyper_id + " does not exist."
            )

    @classmethod
    def get_hyper_virt_pools(cls, hyper_id):
        with cls._rdb_context():
            storage_pools = list(
                r.table("storage_pool")
                .merge(lambda sp: {"categories": sp["categories"].count()})
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            hypervisor = (
                r.table("hypervisors")
                .get(hyper_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if hypervisor is None:
            raise Error("not_found", f"Hypervisor {hyper_id} not found")
        hypervisor_pools = {
            "virt_pools": hypervisor.get("virt_pools", []),
            "enabled_virt_pools": hypervisor.get("enabled_virt_pools", []),
        }
        # hypervisor virt_pools is storage_pool ids or less than that
        return [
            {
                "id": sp["id"],
                "name": sp["name"],
                "categories": sp["categories"],
                "enabled": sp["enabled"],
                "available": sp["id"] in hypervisor_pools.get("virt_pools", []),
                "enabled_virt_pool": sp["id"]
                in hypervisor_pools.get("enabled_virt_pools", []),
            }
            for sp in storage_pools
        ]

    @classmethod
    def update_hyper_virt_pools(cls, hyper_id, virt_pool_data):
        virt_pool_id = virt_pool_data["id"]
        enable_virt_pool = virt_pool_data["enable_virt_pool"]
        with cls._rdb_context():
            hypervisor = (
                r.table("hypervisors")
                .get(hyper_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if hypervisor is None:
            raise Error("not_found", f"Hypervisor {hyper_id} not found")
        virts = {
            "virt_pools": hypervisor.get("virt_pools", []),
            "enabled_virt_pools": hypervisor.get("enabled_virt_pools", []),
        }
        enabled_virt_pools = virts.get("enabled_virt_pools", [])
        if virt_pool_id not in virts.get("virt_pools", []):
            raise Error(
                "precondition_required",
                "Virt pool with ID "
                + virt_pool_id
                + " is not available for hypervisor.",
            )
        if enable_virt_pool is True:
            if virt_pool_id not in enabled_virt_pools:
                virt_pools = enabled_virt_pools + [virt_pool_id]
                with cls._rdb_context():
                    r.table("hypervisors").get(hyper_id).update(
                        {"enabled_virt_pools": virt_pools}
                    ).run(cls._rdb_connection)
        else:
            if virt_pool_id in enabled_virt_pools:
                enabled_virt_pools.remove(virt_pool_id)
            with cls._rdb_context():
                r.table("hypervisors").get(hyper_id).update(
                    {
                        "enabled_virt_pools": enabled_virt_pools,
                    }
                ).run(cls._rdb_connection)
        return True

    @classmethod
    def get_hyper_mountpoints(cls, hyper_id):
        # ``.pluck()`` on a missing hypervisor crashes with
        # ReqlNonExistenceError before the if-check below ever runs;
        # ``.default(None)`` lets the function translate it into a
        # typed 404 cleanly.
        with cls._rdb_context():
            hyper = (
                r.table("hypervisors")
                .get(hyper_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if hyper is None or "mountpoints" not in hyper:
            raise Error(
                "not_found",
                "Mountpoints information still not available",
            )
        return {"mountpoints": hyper["mountpoints"]}

    @classmethod
    @cached(cache=_get_hyper_started_domains_cache)
    def get_hyper_started_domains(cls, hyper_id):
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )
        return domains

    @classmethod
    def clear_get_hyper_started_domains_cache(cls):
        _get_hyper_started_domains_cache.clear()

    @staticmethod
    @cached(cache=_check_create_storage_pool_availability_cache)
    def check_create_storage_pool_availability(category_id=None):
        """_From api/libv2/api_hypervisors.py check_create_storage_pool_availability()_"""
        # Check category storage pools for category. Will raise error if no storage pool available
        # Will return DEFAULT_STORAGE_POOL_ID if no category_id is found
        storage_pool_id = Caches.get_cached_available_category_storage_pool_id(
            category_id
        )

        # Hypervisors online
        ## NOTE_ default storage pool just for backward hypers compatibility, can be removed in future
        for hyper in Caches.get_cached_hypervisors_online():
            if storage_pool_id in hyper.get(
                "enabled_storage_pools", hyper.get("storage_pools", [])
            ):
                return True

        raise Error(
            "precondition_required",
            f"No hypervisors available for category {category_id} with storage pool {storage_pool_id}",
            description_code="no_storage_pool_available",
        )

    @classmethod
    def clear_check_create_storage_pool_availability_cache(cls):
        _check_create_storage_pool_availability_cache.clear()

    @staticmethod
    @cached(cache=_check_virt_storage_pool_availability_cache)
    def check_virt_storage_pool_availability(domain_id):
        """_From api/libv2/api_hypervisors.py check_virt_storage_pool_availability()_"""
        # Check category storage pools for category. Will raise error if no storage pool available
        virt_pool_id = Domain.get_cached_available_domain_storage_pool_id(domain_id)

        # Is that pool available in any hypervisor?
        ## NOTE_ default storage pool just for backward hypers compatibility, can be removed in future
        ##       storage_pools default is just for backward compatibility, can be removed in future
        for hyper in Caches.get_cached_hypervisors_online():
            if virt_pool_id in hyper.get(
                "enabled_virt_pools", hyper.get("storage_pools", [])
            ):
                return True
        raise Error(
            "precondition_required",
            f"No hypervisor available for domain {domain_id} with storage pool {virt_pool_id}",
            description_code="no_storage_pool_available",
        )

    @classmethod
    def clear_check_virt_storage_pool_availability_cache(cls):
        _check_virt_storage_pool_availability_cache.clear()
