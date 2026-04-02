#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import datetime
import glob
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

from ..libv2.caches import (
    get_cached_available_category_storage_pool_id,
    get_cached_available_domain_storage_pool_id,
    get_cached_enabled_virt_pools,
    get_cached_hypervisors_online,
    get_domain_id_from_wg_mac,
)
from ..libv2.isardVpn import isardVpn
from .api_desktop_events import desktops_stop
from .url_validation import SSRFError, validate_hostname_not_loopback_or_linklocal

isardVpn = isardVpn()

import socket
from subprocess import check_output

from cachetools import TTLCache, cached

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
        nvidia_gpus=None,
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
        pci_devices=None,
        numa_topology=None,
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
                nvidia_gpus=nvidia_gpus,
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
                hugepages_info=hugepages_info,
                pci_devices=pci_devices,
                numa_topology=numa_topology,
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
                nvidia_gpus=nvidia_gpus,
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
                hugepages_info=hugepages_info,
                pci_devices=pci_devices,
                numa_topology=numa_topology,
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

        # Log PCI device changes (informational)
        if pci_devices and hypervisor:
            try:
                self._diff_pci_devices(hypervisor.get("pci_devices", {}), pci_devices)
            except Exception as e:
                log.warning(f"Failed to diff PCI devices: {e}")

        # Auto-populate gpu_profiles and gpu cards from scanned GPU data
        if nvidia_gpus:
            try:
                self._resolve_gpu_models(hyper_id, nvidia_gpus)
            except Exception as e:
                log.warning(f"Failed to resolve GPU models: {e}")
            try:
                self.ensure_gpu_profiles(nvidia_gpus)
            except Exception as e:
                log.warning(f"Failed to auto-populate gpu_profiles: {e}")
            try:
                self.ensure_gpu_cards(hyper_id, nvidia_gpus)
            except Exception as e:
                log.warning(f"Failed to auto-create gpu cards: {e}")

        data["certs"] = self.get_hypervisors_certs()

        # Return the tunneling mode and infrastructure MTU for hypervisor OVS setup
        geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
        vpn_tunneling_mode = "geneve" if geneve_only else "wireguard+geneve"
        data["vpn"] = {
            "tunneling_mode": vpn_tunneling_mode,
            "infrastructure_mtu": int(
                os.environ.get("INFRASTRUCTURE_MTU", "")
                or ("9000" if vpn_tunneling_mode == "geneve" else "1500")
            ),
        }

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
        nvidia_gpus=None,
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
        pci_devices=None,
        numa_topology=None,
    ):
        # If we can't connect why we should add it? Just return False!
        if not self.update_fingerprint(hostname, port):
            return False

        # Determine tunneling mode centrally based on GENEVE_ONLY_INFRA
        vpn_tunneling_mode = (
            "geneve"
            if os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
            else "wireguard+geneve"
        )

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
            "nvidia_gpus": nvidia_gpus if nvidia_gpus is not None else [],
            "min_free_mem_gb": min_free_mem_gb,
            "min_free_gpu_mem_gb": min_free_gpu_mem_gb,
            "storage_pools": storage_pools,
            "virt_pools": virt_pools,
            "buffering_hyper": buffering_hyper,
            "gpu_only": gpu_only,
            "vpn": {"tunneling_mode": vpn_tunneling_mode},
            "hugepages_info": hugepages_info if hugepages_info else {},
            "pci_devices": pci_devices if pci_devices else {},
            "numa_topology": numa_topology if numa_topology else {},
        }

        hypervisor = _validate_item("hypervisors", hypervisor)
        hypervisor["enabled_virt_pools"] = (
            enabled_virt_pools or virt_pools or storage_pools
        )
        hypervisor["enabled_storage_pools"] = enabled_storage_pools or storage_pools

        with app.app_context():
            result = (
                r.table("hypervisors")
                .insert(hypervisor, conflict="update")
                .run(db.conn)
            )
        return result

    @staticmethod
    def _normalize_gpu_model(gpu_name, vgpu_profiles=None):
        """Dash-free model name derivation (same logic as gpu_discovery)."""
        if vgpu_profiles:
            return vgpu_profiles[0]["name"].split("-")[0]
        return gpu_name.replace("NVIDIA ", "").replace(" ", "").replace("-", "")

    def _resolve_gpu_models(self, hyper_id, nvidia_gpus):
        """Resolve stable model names for discovered GPUs.

        For each GPU, checks if an auto-created card already exists in the
        database (by deterministic PCI-based card_id).  If so, uses the
        existing card's model name to prevent flipping between vGPU-derived
        and nvidia-smi-derived names across restarts.

        Modifies each GPU dict in-place, setting ``_resolved_model``.
        """
        for gpu in nvidia_gpus:
            pci_bus_id = gpu["pci_bus_id"]
            normalized = pci_bus_id.lower()
            if len(normalized.split(":")[0]) > 4:
                normalized = "0000:" + normalized.split(":", 1)[1]
            pci_name = "pci_" + normalized.replace(":", "_").replace(".", "_")
            card_id = f"auto-{hyper_id}-{pci_name}"

            with app.app_context():
                existing_card = r.table("gpus").get(card_id).run(db.conn)

            if existing_card and existing_card.get("model"):
                gpu["_resolved_model"] = existing_card["model"]
            else:
                # First-time: use discovery-computed model or derive fresh
                gpu["_resolved_model"] = gpu.get("model") or self._normalize_gpu_model(
                    gpu["name"], gpu.get("vgpu_profiles")
                )

    def _diff_pci_devices(self, old_map, new_map):
        """Log PCI device changes between two hypervisor registrations.

        Detects new devices, removed devices, and GPU moves (via gpu_uuid).
        Informational only — does not modify any database state.
        """
        old_addrs = set(old_map.keys())
        new_addrs = set(new_map.keys())

        for addr in sorted(new_addrs - old_addrs):
            dev = new_map[addr]
            log.info(
                f"PCI device added at {addr}: "
                f"vendor={dev.get('vendor')} device={dev.get('device_id')} "
                f"driver={dev.get('driver')}"
            )

        for addr in sorted(old_addrs - new_addrs):
            dev = old_map[addr]
            log.info(
                f"PCI device removed from {addr}: "
                f"vendor={dev.get('vendor')} device={dev.get('device_id')}"
            )

        # Detect GPU moves via gpu_uuid
        old_uuid_to_addr = {}
        for addr, dev in old_map.items():
            uuid = dev.get("gpu_uuid")
            if uuid:
                old_uuid_to_addr[uuid] = addr

        for addr, dev in new_map.items():
            uuid = dev.get("gpu_uuid")
            if uuid and uuid in old_uuid_to_addr:
                old_addr = old_uuid_to_addr[uuid]
                if old_addr != addr:
                    log.warning(
                        f"GPU {uuid} moved from PCI slot {old_addr} " f"to {addr}"
                    )

    def ensure_gpu_profiles(self, nvidia_gpus):
        """Create or update gpu_profiles entries from hypervisor-scanned GPU data.

        Every discovered GPU gets a gpu_profiles entry, even without vGPU driver.
        All entries include a 'passthrough' profile (whole GPU, 1 unit).
        """
        if not nvidia_gpus:
            return

        # Group by GPU model
        models = {}  # model -> {gpu_info, profiles}
        for gpu in nvidia_gpus:
            vgpu_profiles = gpu.get("vgpu_profiles", [])

            # Use PCI-anchored model if available, otherwise derive fresh
            model = gpu.get("_resolved_model") or gpu.get("model")
            if not model:
                model = self._normalize_gpu_model(gpu["name"], vgpu_profiles)

            if model not in models:
                models[model] = {"gpu": gpu, "profiles": []}

            # Add passthrough profile (always, 1 per model)
            if not any(
                p["profile"] == "passthrough" for p in models[model]["profiles"]
            ):
                models[model]["profiles"].append(
                    {
                        "id": f"NVIDIA-{model}-passthrough",
                        "name": f"NVIDIA {model} passthrough",
                        "profile": "passthrough",
                        "mode": "passthrough",
                        "memory": gpu["memory_total_mb"],
                        "units": 1,
                        "description": "Whole GPU passthrough",
                    }
                )

            # Add vGPU profiles (deduplicated across multiple physical cards)
            existing_suffixes = {p["profile"] for p in models[model]["profiles"]}
            for prof in vgpu_profiles:
                suffix = prof["name"].split("-", 1)[1]  # "4Q"
                if suffix not in existing_suffixes:
                    models[model]["profiles"].append(
                        {
                            "id": f"NVIDIA-{model}-{suffix}",
                            "name": f"NVIDIA {model} {suffix}",
                            "profile": suffix,
                            "mode": "vgpu",
                            "memory": prof.get("framebuffer_mb", 0),
                            "units": prof.get("max_instances", 0)
                            or prof.get("available_instances", 0),
                            "description": "",
                        }
                    )
                    existing_suffixes.add(suffix)

            # Add MIG profiles (deduplicated across multiple physical cards)
            for mig_prof in gpu.get("mig_profiles", []):
                suffix = mig_prof["name"]  # "1g.24gb", "2g.48gb+gfx", "1g.24gb_me"
                if suffix not in existing_suffixes:
                    models[model]["profiles"].append(
                        {
                            "id": f"NVIDIA-{model}-{suffix}",
                            "name": f"NVIDIA {model} MIG {suffix}",
                            "profile": suffix,
                            "mode": "mig",
                            "mig_profile_id": mig_prof["profile_id"],
                            "memory": int(mig_prof["memory_gib"] * 1024),
                            "units": mig_prof["max_instances"],
                            "description": f"MIG GPU Instance ({mig_prof['max_instances']}x)",
                        }
                    )
                    existing_suffixes.add(suffix)

        # Upsert each model into gpu_profiles
        for model, data in models.items():
            gpu = data["gpu"]
            gpu_profile_id = f"NVIDIA-{model}"
            memory_gb = gpu["memory_total_mb"] // 1024
            memory_str = f"{memory_gb} GB"

            new_entry = {
                "id": gpu_profile_id,
                "brand": "NVIDIA",
                "name": f"NVIDIA {model}",
                "model": model,
                "architecture": "",
                "description": f"Auto-discovered from {gpu['name']}",
                "memory": memory_str,
                "profiles": data["profiles"],
            }

            with app.app_context():
                existing = r.table("gpu_profiles").get(gpu_profile_id).run(db.conn)

            if existing:
                # Merge profiles: keep existing, add/update from scanned data
                existing_by_id = {p["id"]: p for p in existing.get("profiles", [])}
                for p in data["profiles"]:
                    existing_by_id[p["id"]] = p
                new_entry["profiles"] = list(existing_by_id.values())
                # Preserve existing metadata if it has real content
                if existing.get("architecture"):
                    new_entry["architecture"] = existing["architecture"]
                if existing.get("description") and not existing[
                    "description"
                ].startswith("Auto-discovered"):
                    new_entry["description"] = existing["description"]

            with app.app_context():
                r.table("gpu_profiles").insert(new_entry, conflict="update").run(
                    db.conn
                )

            log.info(
                f"GPU profile '{gpu_profile_id}' "
                f"{'updated' if existing else 'created'} "
                f"with {len(new_entry['profiles'])} profiles"
            )

    def ensure_gpu_cards(self, hyper_id, nvidia_gpus):
        """Auto-create GPU card entries in the 'gpus' table for discovered GPUs.

        Each physical GPU gets a deterministic card ID so re-discovery is idempotent.
        Only profiles_enabled (left empty) and physical_device are managed.
        """
        if not nvidia_gpus:
            return

        for gpu in nvidia_gpus:
            # Use PCI-anchored model if available, otherwise derive fresh
            model = gpu.get("_resolved_model") or gpu.get("model")
            if not model:
                model = self._normalize_gpu_model(gpu["name"], gpu.get("vgpu_profiles"))

            # Normalize PCI bus ID to libvirt pci_name format
            pci_bus_id = gpu["pci_bus_id"]
            normalized = pci_bus_id.lower()
            if len(normalized.split(":")[0]) > 4:
                normalized = "0000:" + normalized.split(":", 1)[1]
            pci_name = "pci_" + normalized.replace(":", "_").replace(".", "_")

            card_id = f"auto-{hyper_id}-{pci_name}"
            vgpu_id = f"{hyper_id}-{pci_name}"
            gpu_profile_id = f"NVIDIA-{model}"

            # Check if any card already has this physical_device assigned
            with app.app_context():
                already_assigned = list(
                    r.table("gpus")
                    .filter({"physical_device": vgpu_id})
                    .pluck("id")
                    .run(db.conn)
                )

            if already_assigned:
                log.info(
                    f"GPU physical_device {vgpu_id} already assigned to "
                    f"card '{already_assigned[0]['id']}', skipping"
                )
                continue

            # Check if auto-created card exists for this slot
            with app.app_context():
                existing_card = r.table("gpus").get(card_id).run(db.conn)

            if existing_card:
                # Update physical_device and sync model/gpu_uuid if changed
                update_fields = {"physical_device": vgpu_id}
                if existing_card.get("model") != model:
                    update_fields["model"] = model
                    log.info(
                        f"GPU card '{card_id}' model updated: "
                        f"{existing_card.get('model')} -> {model}"
                    )
                gpu_uuid = gpu.get("gpu_uuid")
                if gpu_uuid and existing_card.get("gpu_uuid") != gpu_uuid:
                    update_fields["gpu_uuid"] = gpu_uuid
                with app.app_context():
                    r.table("gpus").get(card_id).update(update_fields).run(db.conn)
                log.info(f"GPU card '{card_id}' updated physical_device -> {vgpu_id}")
                continue

            # Look for an existing unassigned card with matching brand/model
            with app.app_context():
                unassigned = list(
                    r.table("gpus")
                    .filter(
                        {
                            "brand": "NVIDIA",
                            "model": model,
                            "physical_device": None,
                        }
                    )
                    .pluck("id")
                    .run(db.conn)
                )

            if unassigned:
                # Assign physical_device to the existing manually-created card
                with app.app_context():
                    r.table("gpus").get(unassigned[0]["id"]).update(
                        {"physical_device": vgpu_id}
                    ).run(db.conn)
                log.info(
                    f"GPU card '{unassigned[0]['id']}' assigned "
                    f"physical_device -> {vgpu_id}"
                )
                continue

            # No existing card found — create a new auto-discovered one
            with app.app_context():
                gpu_profile = r.table("gpu_profiles").get(gpu_profile_id).run(db.conn)

            memory_gb = gpu["memory_total_mb"] // 1024
            new_card = {
                "id": card_id,
                "name": f"NVIDIA {model} ({pci_name})",
                "brand": "NVIDIA",
                "model": model,
                "memory": f"{memory_gb} GB",
                "description": f"Auto-discovered from {gpu['name']}",
                "architecture": (
                    gpu_profile.get("architecture", "") if gpu_profile else ""
                ),
                "profiles_enabled": [],
                "physical_device": vgpu_id,
                "gpu_uuid": gpu.get("gpu_uuid"),
            }

            with app.app_context():
                r.table("gpus").insert(new_card).run(db.conn)
            log.info(
                f"GPU card '{card_id}' created for {gpu['name']} "
                f"with physical_device={vgpu_id}"
            )

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

    def update_boot_progress(self, hyper_id, progress_data):
        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"boot_progress": progress_data}
            ).run(db.conn)

    def remove_hyper(self, hyper_id, restart=True):
        # Clear physical_device on auto-created GPU cards for this hypervisor
        try:
            prefix = f"auto-{hyper_id}-"
            with app.app_context():
                r.table("gpus").filter(
                    lambda gpu: gpu["id"].match(f"^{prefix}")
                ).update({"physical_device": None}).run(db.conn)
        except Exception as e:
            log.warning(f"Failed to clear GPU cards for {hyper_id}: {e}")

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
        desktops_stop(desktops_ids, force=True, update_accessed=False)

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
        try:
            validate_hostname_not_loopback_or_linklocal(hostname)
        except SSRFError:
            log.error(
                "Hostname %s resolves to a loopback or link-local address, refusing",
                hostname,
            )
            return False

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

        # Clean up backup files left behind by ssh-keygen -R
        for backup in glob.glob(path + ".*"):
            try:
                os.remove(backup)
            except OSError:
                pass

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

    @cached(
        cache=TTLCache(maxsize=25, ttl=10),
        key=lambda self, mac, data: f"{mac}:{data.get('viewer', {}).get('guest_ip', '')}",
    )
    def update_wg_address(self, mac, data):
        domain_id = get_domain_id_from_wg_mac(mac)
        if not domain_id:
            raise Error(
                "not_found",
                "Domain with mac " + mac + " not found in wireguard cache",
            )
        try:
            with app.app_context():
                r.table("domains").get(domain_id).update(data).run(db.conn)
            return domain_id
        except ReqlNonExistenceError:
            raise Error(
                "not_found",
                "Domain with ID " + domain_id + " not found in database",
            )
        except:
            raise Error(
                "internal_server",
                "Unable to update wireguard address",
                traceback.format_exc(),
            )

    def get_hypervisor_vpn(self, hyper_id):
        # Check if hypervisor uses geneve-only mode (no WireGuard VPN needed)
        with app.app_context():
            hyper = (
                r.table("hypervisors")
                .get(hyper_id)
                .pluck("id", {"vpn": "tunneling_mode"})
                .default(None)
                .run(db.conn)
            )

        if hyper is None:
            raise Error(
                "not_found",
                f"Hypervisor {hyper_id} not found",
                description_code="hypervisor_not_found",
            )

        vpn_tunneling_mode = hyper.get("vpn", {}).get(
            "tunneling_mode", "wireguard+geneve"
        )

        if vpn_tunneling_mode == "geneve":
            return {
                "vpn_required": False,
                "tunneling_mode": "geneve",
            }

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

        with app.app_context():
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
                .run(db.conn)
            )
        if furthest_shutdown:
            d = datetime.datetime.strptime(furthest_shutdown, "%Y-%m-%dT%H:%M%z")
        else:
            # If no runnng desktops in the hypervisor, we use as default desktops max timeout
            desktops_max_timeout = self.get_desktops_max_timeout()
            d = datetime.datetime.utcnow() + datetime.timedelta(
                minutes=desktops_max_timeout
            )

        dtz = d.replace(tzinfo=pytz.UTC).isoformat()

        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"only_forced": True, "destroy_time": dtz}
            ).run(db.conn)
        return {"destroy_time": dtz}

    @cached(cache=TTLCache(maxsize=200, ttl=100))
    def get_desktops_max_timeout(self):
        with app.app_context():
            return (
                r.table("desktops_priority")
                .has_fields({"shutdown": {"max": True}})
                .order_by(r.desc(lambda priority: priority["shutdown"]["max"]))
                .nth(0)["shutdown"]["max"]
                .default(720)  # Default to 12 hours if no max timeout found (12*60=720)
                .run(db.conn)
            )

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

    def get_hyper_virt_pools(self, hyper_id):
        with app.app_context():
            storage_pools = list(
                r.table("storage_pool")
                .merge(lambda sp: {"categories": sp["categories"].count()})
                .run(db.conn)
            )
        with app.app_context():
            hypervisor_pools = (
                r.table("hypervisors")
                .get(hyper_id)
                .pluck("virt_pools", "enabled_virt_pools")
                .run(db.conn)
            )
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

    def update_hyper_virt_pools(self, hyper_id, virt_pool_data):
        virt_pool_id = virt_pool_data["id"]
        enable_virt_pool = virt_pool_data["enable_virt_pool"]
        with app.app_context():
            virts = (
                r.table("hypervisors")
                .get(hyper_id)
                .pluck("virt_pools", "enabled_virt_pools")
                .run(db.conn)
            )
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
                with app.app_context():
                    r.table("hypervisors").get(hyper_id).update(
                        {"enabled_virt_pools": virt_pools}
                    ).run(db.conn)
        else:
            if virt_pool_id in enabled_virt_pools:
                enabled_virt_pools.remove(virt_pool_id)
            with app.app_context():
                r.table("hypervisors").get(hyper_id).update(
                    {
                        "enabled_virt_pools": enabled_virt_pools,
                    }
                ).run(db.conn)
        return True

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
def check_create_storage_pool_availability(category_id=None):
    # Check category storage pools for category. Will raise error if no storage pool available
    # Will return DEFAULT_STORAGE_POOL_ID if no category_id is found
    storage_pool_id = get_cached_available_category_storage_pool_id(category_id)

    # Hypervisors online
    ## NOTE_ default storage pool just for backward hypers compatibility, can be removed in future
    for hyper in get_cached_hypervisors_online():
        if storage_pool_id in hyper.get(
            "enabled_storage_pools", hyper.get("storage_pools", [])
        ):
            return True

    raise Error(
        "precondition_required",
        f"No hypervisors available for category {category_id} with storage pool {storage_pool_id}",
        description_code="no_storage_pool_available",
    )


@cached(cache=TTLCache(maxsize=50, ttl=10))
def check_virt_storage_pool_availability(domain_id):
    # Check category storage pools for category. Will raise error if no storage pool available
    virt_pool_id = get_cached_available_domain_storage_pool_id(domain_id)

    # Is that pool available in any hypervisor?
    ## NOTE_ default storage pool just for backward hypers compatibility, can be removed in future
    ##       storage_pools default is just for backward compatibility, can be removed in future
    for hyper in get_cached_hypervisors_online():
        if virt_pool_id in hyper.get(
            "enabled_virt_pools", hyper.get("storage_pools", [])
        ):
            return True
    raise Error(
        "precondition_required",
        f"No hypervisor available for domain {domain_id} with storage pool {virt_pool_id}",
        description_code="no_storage_pool_available",
    )
