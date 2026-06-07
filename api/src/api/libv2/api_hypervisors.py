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
import re
import threading
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

# MIG-backed vGPU profile suffix: "<slices>_<framebuffer><series>" (e.g. "1_24Q",
# "2_48Q"). Groups: slices, framebuffer-GB, series-letter. Slice separator "_" or
# "-" (canonical uses "_"; legacy dash form "1-2Q" also matched). Used to keep
# only the full-memory (max framebuffer) variant per slice-tier as bookable.
_MIG_BACKED_SUFFIX_RE = re.compile(r"^(\d+)[-_](\d+)([ABCQ])$")

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

# GENEVE / WireGuard encapsulation overheads. Canonical arithmetic lives in
# docker/vpn/ovs/ovs_setup.sh (it physically sizes vlan-wg/ovsbr0); this is a
# faithful port. Keep both in sync.
_GENEVE_OH = 54  # 20 IP + 8 UDP + 8 geneve + 14 eth + 4 VLAN
_WG_OH = 60  # 20 IP + 8 UDP + 32 WG

# Canonical model token per PCI device — mirror of
# docker/hypervisor/src/lib/gpu_discovery.py::_MODEL_ALIASES. Physically
# identical cards (same vendor:device[:subsystem]) MUST resolve to one model
# token so they share a single reservable/profile pool. Unmapped devices fall
# through to the name/profile derivation unchanged (no-op for already-consistent
# cards). The GA107 die-id 10de:25b6 is shared by the A2 and A16 boards, so A16
# is subsystem-qualified to avoid mislabelling a real A2. Keep both in sync.
_MODEL_ALIASES = {
    "10de:2bb5": "RTXPro6000BlackwellDC",
    "10de:25b6|sub:10de:14a9": "A16",
}


def _model_alias(pci_device_id, pci_subsystem_id=None):
    """Canonical token for a PCI device, or None if unmapped.

    Tries the subsystem-qualified key first (so a shared die-id only matches the
    intended board), then the bare device-id.
    """
    if not pci_device_id:
        return None
    if pci_subsystem_id:
        alias = _MODEL_ALIASES.get(f"{pci_device_id}|sub:{pci_subsystem_id}")
        if alias:
            return alias
    return _MODEL_ALIASES.get(pci_device_id)


def _overlay_max(infrastructure_mtu, tunneling_mode):
    """Maximum payload MTU a guest NIC may use on the tenant overlay.

    This is the *ceiling* advertised to the guest virtio NIC (engine
    injects it as ``<mtu size=...>``) and the size the host datapath
    (ovsbr0/vlan-wg) is set to. dnsmasq separately serves
    ``min(overlay_max, 1500)`` as the safe DHCP default so ordinary
    guests stay at 1500 while a jumbo underlay lets a user raise the
    in-guest MTU up to this ceiling. Mirrors docker/vpn/ovs/ovs_setup.sh.
    """
    oh = _GENEVE_OH if tunneling_mode == "geneve" else _WG_OH + _GENEVE_OH
    raw = int(infrastructure_mtu) - oh
    return max(1280, min(raw, 9000))  # IPv6 floor .. sane jumbo cap


# Serializes the destructive section of reconcile_unrealizable_gpu_profiles so
# two hypervisors registering concurrently cannot both read "not the last card"
# and delete a reservable row without running its deassign/booking cleanup. The
# API runs single-process under gevent (startv3 monkey.patch_all), so this
# stdlib Lock is monkey-patched to a greenlet-safe lock.
_gpu_reconcile_lock = threading.Lock()


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
        gpu_apply_capable=False,
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
                gpu_apply_capable=gpu_apply_capable,
            )
            if not result:
                raise Error("not_found", "Unable to ssh-keyscan")
            elif not self.check(result, "inserted"):
                raise Error("not_found", "Unable to add hypervisor")
        else:
            # Re-registration: keep the hypervisor DISABLED for the whole boot.
            # The hypervisor re-enables itself (EnableHypervisor) only once it is
            # fully ready -- after the long GPU discovery/apply, the VPN/geneve
            # bring-up AND libvirtd are up. Registering it enabled here (its
            # previous state) made the engine start managing a half-booted host:
            # the worker's libvirt reconnect failed for minutes, flipping the
            # host to Error and stopping its desktops. With enabled=False the
            # engine's disable_hyper stops the worker cleanly (host -> Offline,
            # not Error); EnableHypervisor's later enabled=True fires enable_hyper
            # and spawns a fresh worker against a host that is actually ready.
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
                gpu_apply_capable=gpu_apply_capable,
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
            try:
                self.reconcile_unrealizable_gpu_profiles(hyper_id, nvidia_gpus)
            except Exception as e:
                log.warning(f"Failed to reconcile unrealizable gpu profiles: {e}")
            # For a gpu-apply-capable hypervisor, return the per-card target
            # profile it should apply locally (planning -> current -> passthrough
            # default). Computed AFTER the prune so a just-disabled profile is
            # never offered. Old hypervisors omit the flag -> no targets -> the
            # engine keeps applying as before.
            if gpu_apply_capable:
                try:
                    data["gpu_targets"] = self.compute_gpu_targets(
                        hyper_id, nvidia_gpus
                    )
                except Exception as e:
                    log.warning(f"Failed to compute gpu targets: {e}")

        data["certs"] = self.get_hypervisors_certs()

        # Return the tunneling mode and infrastructure MTU for hypervisor OVS setup
        geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
        vpn_tunneling_mode = "geneve" if geneve_only else "wireguard+geneve"
        infra_mtu = int(os.environ.get("INFRASTRUCTURE_MTU", "") or "1500")
        data["vpn"] = {
            "tunneling_mode": vpn_tunneling_mode,
            "infrastructure_mtu": infra_mtu,
            "guest_mtu": _overlay_max(infra_mtu, vpn_tunneling_mode),
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
        gpu_apply_capable=False,
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
        vpn_infra_mtu = int(os.environ.get("INFRASTRUCTURE_MTU", "") or "1500")

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
            # Persisted so the engine knows this host applies GPU profiles
            # itself (registration + runtime via gpu_apply_cli over SSH) and can
            # route runtime changes to the hypervisor instead of building the
            # host-command sequences itself. Old hosts omit it -> engine applies.
            "gpu_apply_capable": gpu_apply_capable,
            "nvidia_enabled": nvidia_enabled,
            "nvidia_gpus": nvidia_gpus if nvidia_gpus is not None else [],
            "min_free_mem_gb": min_free_mem_gb,
            "min_free_gpu_mem_gb": min_free_gpu_mem_gb,
            "storage_pools": storage_pools,
            "virt_pools": virt_pools,
            "buffering_hyper": buffering_hyper,
            "gpu_only": gpu_only,
            "vpn": {
                "tunneling_mode": vpn_tunneling_mode,
                "guest_mtu": _overlay_max(vpn_infra_mtu, vpn_tunneling_mode),
            },
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
        """Dash- and slash-free model derivation (mirror of gpu_discovery.normalize_gpu_model).

        Handles both classic time-sliced profile suffixes ("-4Q", "-96Q") and
        MIG-backed slot-notation suffixes ("-1-3Q", "-4-48Q") so GPUs like the
        RTX PRO 6000 Blackwell DC produce a dash-free model name. Slashes are
        stripped too: the BRAND-MODEL-PROFILE id is a URL path segment, so a
        '/' in the model (e.g. the A16 die "GA107GL [A2 / A16]") would 405 the
        reservables route. Must stay in lockstep with the canonical function.
        """
        if vgpu_profiles:
            profile_name = vgpu_profiles[0]["name"]
            match = re.match(r"^(.+?)(-\d+-\d+[ABCQ]|-\d+[ABCQ])$", profile_name)
            if match:
                model_part = match.group(1)
            else:
                model_part = profile_name.rsplit("-", 1)[0]
            # Strip vendor prefixes and normalize dash-free, same as the
            # nvidia-smi-name path below, so the two branches agree.
            return (
                model_part.replace("NVIDIA ", "")
                .replace("GRID ", "")
                .replace(" ", "")
                .replace("-", "")
                .replace("/", "")
            )
        return (
            gpu_name.replace("NVIDIA ", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("/", "")
        )

    @staticmethod
    def _canonical_gpu_model(
        gpu_name, vgpu_profiles=None, pci_device_id=None, pci_subsystem_id=None
    ):
        """Hardware-anchored model token (mirror of
        gpu_discovery.canonical_gpu_model).

        A mapped device-id takes PRECEDENCE over the name/profile derivation so
        every discovery path collapses to one token for identical hardware;
        unmapped devices (or callers without a device-id) fall back to
        ``_normalize_gpu_model``.
        """
        alias = _model_alias(pci_device_id, pci_subsystem_id)
        if alias:
            return alias
        return ApiHypervisors._normalize_gpu_model(gpu_name, vgpu_profiles)

    def _resolve_gpu_models(self, hyper_id, nvidia_gpus):
        """Resolve stable model names for discovered GPUs.

        Card identity is anchored on ``gpu_uuid`` (immutable BIOS asset id
        from nvidia-smi) so the persisted model survives any driver flip
        (vfio-pci ↔ nvidia) or naming-convention change in
        ``normalize_gpu_model``. Same card seen again (uuid match, regardless
        of slot) keeps its operator-curated catalog (gpu_profiles,
        reservables_vgpus, profiles_enabled). Card swap (slot reused with a
        different uuid) is detected explicitly and logged before resetting
        the model — operator can audit and re-curate.

        Resolution order:
          1. uuid match against any existing card -> reuse persisted model;
             backfill the card's pci slot if it moved.
          2. PCI-anchored card row exists with a persisted model -> trust it
             (legacy rows that pre-date uuid tracking). A new uuid in the same
             slot only forces a model reset + re-curation when the PCI
             **device-id changed** (genuinely different hardware); an identical
             card (same device-id, e.g. an RMA replacement) keeps the curated
             pool.
          3. Otherwise derive fresh from discovery and persist.

        The PCI ``device-id`` (+subsystem) is persisted on the card row and is
        what anchors the canonical model token, so two physically identical
        cards resolve to one token / one reservable pool. The fresh derivation
        uses ``_canonical_gpu_model`` (device-id alias > name/profile). This
        rewrites only ``model`` / ``pci_device_id`` / ``pci_subsystem_id`` /
        ``gpu_uuid`` — never the row ``id``, ``physical_device`` or ``category``.

        Modifies each GPU dict in-place, setting ``_resolved_model``.
        """
        for gpu in nvidia_gpus:
            pci_bus_id = gpu["pci_bus_id"]
            normalized = pci_bus_id.lower()
            if len(normalized.split(":")[0]) > 4:
                normalized = "0000:" + normalized.split(":", 1)[1]
            pci_name = "pci_" + normalized.replace(":", "_").replace(".", "_")
            card_id = f"auto-{hyper_id}-{pci_name}"
            new_uuid = gpu.get("gpu_uuid")
            new_device_id = gpu.get("pci_device_id")
            new_subsystem_id = gpu.get("pci_subsystem_id")
            # Persist the PCI ids on every write path so legacy rows get them
            # backfilled and the device-id is available for future swap checks.
            pci_id_fields = {}
            if new_device_id:
                pci_id_fields["pci_device_id"] = new_device_id
            if new_subsystem_id:
                pci_id_fields["pci_subsystem_id"] = new_subsystem_id

            with app.app_context():
                existing_card = r.table("gpus").get(card_id).run(db.conn)

            # 1) uuid match wins, even across slot moves: same physical card,
            # keep its catalog. Skip lookup when discovery did not report a
            # uuid (older nvidia-smi or a card under vfio-pci with no uuid in
            # sysfs) — fall through to PCI-anchored matching.
            uuid_match = None
            if new_uuid:
                with app.app_context():
                    uuid_match = (
                        r.table("gpus")
                        .filter({"gpu_uuid": new_uuid})
                        .limit(1)
                        .run(db.conn)
                    )
                    uuid_match = list(uuid_match)
                uuid_match = uuid_match[0] if uuid_match else None

            if uuid_match and uuid_match.get("model"):
                gpu["_resolved_model"] = uuid_match["model"]
                # Slot move: same uuid, different card_id. Migrate the row id
                # so PCI-keyed lookups elsewhere keep finding the card.
                if uuid_match["id"] != card_id:
                    log.warning(
                        f"GPU {new_uuid!r} moved slot: "
                        f"{uuid_match['id']!r} -> {card_id!r}; "
                        f"migrating row, model={uuid_match['model']!r}"
                    )
                    with app.app_context():
                        new_row = dict(uuid_match)
                        new_row["id"] = card_id
                        new_row.update(pci_id_fields)
                        r.table("gpus").insert(new_row).run(db.conn)
                        r.table("gpus").get(uuid_match["id"]).delete().run(db.conn)
                        # Repoint plannings keyed on the OLD card id to the new
                        # one (resource_planner.item_id IS the physical card id),
                        # else the planner joins against a now-deleted gpus row.
                        r.table("resource_planner").get_all(
                            uuid_match["id"], index="item_id"
                        ).update({"item_id": card_id}).run(db.conn)
                elif pci_id_fields and any(
                    uuid_match.get(k) != v for k, v in pci_id_fields.items()
                ):
                    # Same slot/uuid: backfill PCI ids if missing or stale.
                    with app.app_context():
                        r.table("gpus").get(card_id).update(pci_id_fields).run(db.conn)
                continue

            # 2) PCI-anchored card with a persisted model: legacy row (no uuid
            # tracked yet) OR same slot, same uuid. Either way the model is
            # the source of truth; do not re-derive.
            if existing_card and existing_card.get("model"):
                persisted_uuid = existing_card.get("gpu_uuid")
                persisted_device_id = existing_card.get("pci_device_id")
                uuid_changed = bool(
                    new_uuid and persisted_uuid and persisted_uuid != new_uuid
                )
                fresh = gpu.get("model") or self._canonical_gpu_model(
                    gpu["name"],
                    gpu.get("vgpu_profiles"),
                    new_device_id,
                    new_subsystem_id,
                )
                # A different physical card sits in the slot only if its
                # device-id differs. For legacy rows with no persisted
                # device-id, fall back to a model-change check as the swap
                # signal so an identical card is not needlessly re-curated.
                if persisted_device_id and new_device_id:
                    hardware_changed = persisted_device_id != new_device_id
                else:
                    hardware_changed = fresh != existing_card["model"]

                if uuid_changed and hardware_changed:
                    # 2b) Card swap to DIFFERENT hardware: reset model so the
                    # catalog tracks it. Operator must re-curate gpu_profiles /
                    # reservables_vgpus / profiles_enabled — not auto-migrated,
                    # because the previous card's bookings should not silently
                    # bind to a different model.
                    log.warning(
                        f"GPU card {card_id!r}: physical card swapped to "
                        f"different hardware (uuid {persisted_uuid!r} -> "
                        f"{new_uuid!r}, device {persisted_device_id!r} -> "
                        f"{new_device_id!r}); resetting model "
                        f"{existing_card['model']!r} -> {fresh!r}. Operator must "
                        f"re-curate gpu_profiles, reservables_vgpus, and "
                        f"profiles_enabled."
                    )
                    gpu["_resolved_model"] = fresh
                    with app.app_context():
                        r.table("gpus").get(card_id).update(
                            {"model": fresh, "gpu_uuid": new_uuid, **pci_id_fields}
                        ).run(db.conn)
                    continue

                # Same card, or an identical replacement (same device-id, new
                # uuid e.g. RMA): keep the curated model + pool. Backfill uuid
                # and PCI ids as needed.
                gpu["_resolved_model"] = existing_card["model"]
                update_fields = dict(pci_id_fields)
                if uuid_changed:
                    update_fields["gpu_uuid"] = new_uuid
                    log.info(
                        f"GPU card {card_id!r}: identical card replacement "
                        f"(uuid {persisted_uuid!r} -> {new_uuid!r}, device "
                        f"{new_device_id!r}); pool retained."
                    )
                elif new_uuid and not persisted_uuid:
                    update_fields["gpu_uuid"] = new_uuid
                    log.info(f"GPU card {card_id!r}: backfilled gpu_uuid={new_uuid!r}")
                # Drop pci-id keys that already match to avoid a no-op write.
                update_fields = {
                    k: v for k, v in update_fields.items() if existing_card.get(k) != v
                }
                if update_fields:
                    with app.app_context():
                        r.table("gpus").get(card_id).update(update_fields).run(db.conn)
                continue

            # 3) First sight (no row, or row with no model): derive and persist.
            resolved = gpu.get("model") or self._canonical_gpu_model(
                gpu["name"],
                gpu.get("vgpu_profiles"),
                new_device_id,
                new_subsystem_id,
            )
            gpu["_resolved_model"] = resolved
            if existing_card:
                update_fields = {"model": resolved, **pci_id_fields}
                if new_uuid:
                    update_fields["gpu_uuid"] = new_uuid
                with app.app_context():
                    r.table("gpus").get(card_id).update(update_fields).run(db.conn)
                log.info(f"GPU card {card_id!r} bound model={resolved!r} (was empty)")

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
            # `or []` (not a get-default): the discovery-failed sentinel sets
            # vgpu_profiles to None (key present), and a brand-new card now
            # flows through registration, so guard against iterating None. A
            # profile-less card still gets its passthrough catalog entry below.
            vgpu_profiles = gpu.get("vgpu_profiles") or []

            # Card-anchored model (set by _resolve_gpu_models). Never re-derive
            # here: a fresh derivation that disagrees with the existing card's
            # model would create a duplicate gpu_profiles entry for the same
            # physical card.
            model = gpu.get("_resolved_model")
            if not model:
                raise RuntimeError(
                    f"ensure_gpu_profiles: missing _resolved_model on GPU "
                    f"{gpu.get('pci_bus_id')!r}; _resolve_gpu_models must run first"
                )

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

            # Add vGPU profiles (deduplicated across multiple physical cards).
            # MIG-backed vGPU profiles ("<slices>_<fb>Q") come in several
            # framebuffer sizes per slice-tier (e.g. 1_2Q..1_24Q all on the 1g
            # GI). Only the LARGEST framebuffer per tier uses the GI's full
            # memory; the smaller ones strand the rest of the GI (one vGPU per
            # GI), so they are not full utilization and are excluded. Time-sliced
            # vGPU ("<fb>Q") and whole-card "passthrough" partition the card's
            # memory fully and are kept.
            mig_max_fb = {}  # (slices, series-letter) -> max framebuffer
            for prof in vgpu_profiles:
                mm = _MIG_BACKED_SUFFIX_RE.match(prof["name"].split("-", 1)[1])
                if mm:
                    key = (mm.group(1), mm.group(3))
                    mig_max_fb[key] = max(mig_max_fb.get(key, 0), int(mm.group(2)))

            existing_suffixes = {p["profile"] for p in models[model]["profiles"]}
            for prof in vgpu_profiles:
                suffix = prof["name"].split("-", 1)[1]  # "4Q" or "1_24Q"
                mm = _MIG_BACKED_SUFFIX_RE.match(suffix)
                if mm and int(mm.group(2)) < mig_max_fb[(mm.group(1), mm.group(3))]:
                    continue  # non-max MIG-backed fb -> strands GI memory, skip
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

            # Plain GI-name MIG profiles ("1g.24gb", "2g.48gb", "4g.96gb" and
            # their "+gfx"/"+me"/"+me.all"/"-me" variants) are deliberately NOT
            # exposed as bookable reservables. A plain GI carve creates a single
            # GPU-instance and wastes the rest of the card, and the plain compute
            # GIs do not expose a usable vGPU mdev at all (only the "+gfx"
            # variants do, and those serve only as carve targets). The bookable
            # GPU modes are restricted to full-utilization profiles: whole-card
            # "passthrough", time-sliced vGPU ("<mem>Q"), and the
            # fully-splitting MIG-backed vGPU profiles ("<slices>_<mem>Q", e.g.
            # "1_24Q"/"2_48Q"/"4_96Q") — the latter enter the catalog via the
            # vGPU loop above (discovered as Q-series mdev types). So the former
            # "mig_profiles" loop is intentionally dropped.

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

    def _recompute_total_units(self, profiles_enabled):
        """Recompute reservables_vgpus.total_units for each enabled profile id.
        Used to RESTORE capacity when a card is re-attached, symmetric to the
        detach-side recompute in remove_hyper / cleanup_hypervisor_gpus (the
        count is filtered to physical_device != None, so a re-bound card now
        counts again)."""
        if not profiles_enabled:
            return
        from .bookings.api_reservables import Reservables

        api_ri = Reservables()
        for reservable_id in profiles_enabled:
            try:
                api_ri.recompute_reservable_total_units("gpus", reservable_id)
            except Exception as e:
                log.warning(
                    f"ensure_gpu_cards: total_units recompute {reservable_id}: {e}"
                )

    def ensure_gpu_cards(self, hyper_id, nvidia_gpus):
        """Auto-create GPU card entries in the 'gpus' table for discovered GPUs.

        Each physical GPU gets a deterministic card ID so re-discovery is idempotent.
        Only profiles_enabled (left empty) and physical_device are managed.
        """
        if not nvidia_gpus:
            return

        for gpu in nvidia_gpus:
            # Card-anchored model (set by _resolve_gpu_models). Same contract
            # as ensure_gpu_profiles: never re-derive here.
            model = gpu.get("_resolved_model")
            if not model:
                raise RuntimeError(
                    f"ensure_gpu_cards: missing _resolved_model on GPU "
                    f"{gpu.get('pci_bus_id')!r}; _resolve_gpu_models must run first"
                )

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
                # Update physical_device only.  The model is bound by
                # _resolve_gpu_models on first sight and treated as immutable
                # thereafter — we never overwrite it here, so a future change
                # in normalize_gpu_model output (driver upgrade, code change)
                # cannot drift the catalog away from desktops that already
                # reference the card's reservables.
                update_fields = {"physical_device": vgpu_id}
                gpu_uuid = gpu.get("gpu_uuid")
                if gpu_uuid and existing_card.get("gpu_uuid") != gpu_uuid:
                    update_fields["gpu_uuid"] = gpu_uuid
                # companion_pci_bdfs reflects current sysfs/IOMMU-group state;
                # always re-sync so a displaymodeselector flip or hardware
                # change shows up in the row without a re-curation step.
                companion_pci_bdfs = gpu.get("companion_pci_bdfs") or []
                if existing_card.get("companion_pci_bdfs", []) != companion_pci_bdfs:
                    update_fields["companion_pci_bdfs"] = companion_pci_bdfs
                with app.app_context():
                    r.table("gpus").get(card_id).update(update_fields).run(db.conn)
                log.info(f"GPU card '{card_id}' updated physical_device -> {vgpu_id}")
                # Capacity restore: if the card was detached and is now re-bound,
                # recompute total_units for its enabled profiles (the detach path
                # in remove_hyper/cleanup drove them down). Symmetric to detach.
                if existing_card.get("physical_device") != vgpu_id:
                    self._recompute_total_units(
                        existing_card.get("profiles_enabled") or []
                    )
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
                    .pluck("id", "profiles_enabled")
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
                # Capacity restore (was physical_device=None -> now bound).
                self._recompute_total_units(unassigned[0].get("profiles_enabled") or [])
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
                "pci_device_id": gpu.get("pci_device_id"),
                "pci_subsystem_id": gpu.get("pci_subsystem_id"),
                "companion_pci_bdfs": gpu.get("companion_pci_bdfs") or [],
            }

            with app.app_context():
                r.table("gpus").insert(new_card).run(db.conn)
            log.info(
                f"GPU card '{card_id}' created for {gpu['name']} "
                f"with physical_device={vgpu_id}"
            )

    def reconcile_unrealizable_gpu_profiles(self, hyper_id, nvidia_gpus):
        """Remove vGPU profiles a card can no longer realize -- the removal half
        that complements :meth:`ensure_gpu_profiles`' additive merge.

        SAFETY (decisions live in the pure :mod:`gpu_realizability` module): a
        profile is dropped from a card ONLY when THIS registration carries a
        trustworthy reading for that card (discovery succeeded; not the SR-IOV
        discovery-incomplete / vgpud-down signature) that positively shows the
        profile is unavailable. The prune is PER PHYSICAL CARD / PER SERVER --
        each ``gpus`` row is one physical card on one hypervisor and is pruned
        only against its own reading. Cards not in this POST, or with an
        ambiguous reading, are never touched, so the model-level reservable
        survives until EVERY card has dropped the profile (i.e. no card in the
        whole infrastructure can realize that brand-model-profile). At that
        point the supported ``delete_subitem`` + ``enable_subitems(False)``
        sequence (mirroring ``ReservablesView.api_v3_reservable_items``) tears
        down the profile's bookings, every ``domains``/``deployments``
        reservable reference, its plannings and the reservable row. Because a
        running desktop can only exist on a card that is currently realizing the
        profile, that destructive cleanup never reaches an in-flight session.

        Best-effort and idempotent: a partial/failed cycle self-heals on the
        next registration.
        """
        if not nvidia_gpus:
            return
        from .bookings.api_reservables import Reservables
        from .bookings.api_reservables_planner import ReservablesPlanner
        from .gpu_realizability import plan_card_prunes

        api_ri = Reservables()
        api_rp = ReservablesPlanner()

        # Build per-model card entries from THIS registration's payload. Only a
        # card we just read (with a trustworthy reading) can drive its own
        # prune; the pure planner skips everything else.
        by_model = {}
        for gpu in nvidia_gpus:
            model = gpu.get("_resolved_model")
            if not model:
                continue
            normalized = gpu["pci_bus_id"].lower()
            if len(normalized.split(":")[0]) > 4:
                normalized = "0000:" + normalized.split(":", 1)[1]
            pci_name = "pci_" + normalized.replace(":", "_").replace(".", "_")
            vgpu_id = f"{hyper_id}-{pci_name}"
            with app.app_context():
                card_rows = list(
                    r.table("gpus")
                    .filter({"physical_device": vgpu_id})
                    .pluck("id", "profiles_enabled")
                    .run(db.conn)
                )
            if not card_rows:
                continue
            with app.app_context():
                vgpu_row = r.table("vgpus").get(vgpu_id).run(db.conn)
            sriov = ((vgpu_row or {}).get("info") or {}).get("sriov_totalvfs", 0)
            for card in card_rows:
                by_model.setdefault(model, []).append(
                    {
                        "id": card["id"],
                        "profiles_enabled": card.get("profiles_enabled") or [],
                        "gpu_payload": gpu,
                        "sriov_totalvfs": sriov,
                    }
                )

        for model, cards in by_model.items():
            for card_id, reservable_id in plan_card_prunes(model, cards):
                # Serialize the last-card decision + disable + row-deletion.
                # delete_subitem reads "is this the last card?" and enable_subitem
                # decides the row deletion AFTER mutating profiles_enabled -- two
                # separate reads. Two hypervisors registering concurrently could
                # otherwise each read "not last", both disable, and delete the
                # reservable row with NEITHER running the deassign/booking
                # cleanup, stranding domain/deployment/planning/booking refs. The
                # API is single-process gevent, so this monkey-patched lock is
                # greenlet-safe and keeps the critical section atomic.
                with _gpu_reconcile_lock:
                    self._prune_card_reservable(
                        api_ri, api_rp, model, card_id, reservable_id
                    )

    def _prune_card_reservable(self, api_ri, api_rp, model, card_id, reservable_id):
        """Disable one unrealizable profile on one card via the supported
        ``delete_subitem`` + ``enable_subitems(False)`` sequence, then either fix
        the surviving reservable's ``total_units`` or, when this was the last
        card, drop the dead catalog entry. Must run under ``_gpu_reconcile_lock``
        so ``delete_subitem``'s last-card read and ``enable_subitem``'s
        row-deletion read stay mutually consistent."""
        try:
            api_rp.delete_subitem("gpus", card_id, reservable_id)
        except Exception as e:
            log.warning(
                f"reconcile_unrealizable_gpu_profiles: delete_subitem "
                f"{reservable_id} on {card_id}: {e}"
            )
        try:
            api_ri.enable_subitems("gpus", card_id, reservable_id, False)
        except Exception as e:
            log.warning(
                f"reconcile_unrealizable_gpu_profiles: disable "
                f"{reservable_id} on {card_id}: {e}"
            )
            return
        with app.app_context():
            survives = r.table("reservables_vgpus").get(reservable_id).run(db.conn)
        if not survives:
            # Last card: the profile is unrealizable across the whole install ->
            # also drop the now-dead nested entry from the gpu_profiles model
            # catalog so it cannot be re-offered. ensure_gpu_profiles re-adds it
            # if a driver ever exposes it again. (total_units on a surviving
            # non-last reservable is kept correct centrally in enable_subitem.)
            self._remove_catalog_profile_entry(model, reservable_id)
        log.info(
            f"Pruned unrealizable vGPU profile '{reservable_id}' from card "
            f"'{card_id}' on a verified reading"
        )

    def _remove_catalog_profile_entry(self, model, profile_id):
        """Drop a single nested profile entry from the ``gpu_profiles`` model
        catalog (never the model row itself, never the passthrough entry).
        Used when a profile became unrealizable across the whole install."""
        gpu_profile_id = f"NVIDIA-{model}"
        with app.app_context():
            catalog = r.table("gpu_profiles").get(gpu_profile_id).run(db.conn)
        if not catalog:
            return
        profiles = catalog.get("profiles", [])
        kept = [
            p
            for p in profiles
            if p.get("id") != profile_id or p.get("profile") == "passthrough"
        ]
        if len(kept) == len(profiles):
            return
        with app.app_context():
            r.table("gpu_profiles").get(gpu_profile_id).update({"profiles": kept}).run(
                db.conn
            )
        log.info(
            f"Removed unrealizable profile '{profile_id}' from catalog "
            f"'{gpu_profile_id}'"
        )

    @staticmethod
    def _vgpu_id_for(hyper_id, pci_bus_id):
        """The vgpus/physical_device id for a discovered card. Mirrors the
        normalization in ensure_gpu_cards / reconcile_unrealizable_gpu_profiles
        (single source so the three stay in lockstep)."""
        normalized = pci_bus_id.lower()
        if len(normalized.split(":")[0]) > 4:
            normalized = "0000:" + normalized.split(":", 1)[1]
        pci_name = "pci_" + normalized.replace(":", "_").replace(".", "_")
        return f"{hyper_id}-{pci_name}"

    def get_vgpu_scheduled_profile_now(self, card_id):
        """The profile suffix scheduled by an active booking for this card right
        now, or None. Mirrors the engine's get_vgpu_actual_profile (query
        resource_planner by item_id, now-overlap) but canonicalizes the suffix
        via canonical_profile_id so a dash-form MIG id parses correctly (the
        engine's split('-')[-1] would mis-split it)."""
        from .gpu_realizability import canonical_profile_id

        now = datetime.datetime.now(pytz.utc)
        with app.app_context():
            plans = list(
                r.table("resource_planner")
                .get_all(card_id, index="item_id")
                .filter(lambda p: (p["start"] <= now) & (p["end"] >= now))
                .pluck("subitem_id")
                .run(db.conn)
            )
        if not plans:
            return None
        parts = canonical_profile_id(plans[0]["subitem_id"]).split("-", 2)
        # Guard a malformed/empty suffix (e.g. a trailing-hyphen subitem_id):
        # an empty string would be treated differently from None downstream.
        return parts[2] if len(parts) == 3 and parts[2].strip() else None

    def compute_gpu_targets(self, hyper_id, nvidia_gpus):
        """Per-card target profile to apply at registration, for a gpu-apply
        capable hypervisor. Uses the SAME policy as the engine reconcile
        (isardvdi_common.gpu_pool_policy.decide_reconcile_action): scheduled
        booking > operator intent > passthrough default. available_types comes
        from the freshly-POSTed discovery (vgpus.info may not exist yet on a
        first registration). Returns {pci_bus_id: {vgpu_id, card_id, action,
        target_profile}}."""
        from isardvdi_common.gpu_pool_policy import (
            canonical_suffix,
            decide_reconcile_action,
        )

        from .gpu_realizability import realizable_suffixes

        targets = {}
        for gpu in nvidia_gpus or []:
            pci_bus_id = gpu.get("pci_bus_id")
            if not pci_bus_id or not gpu.get("_resolved_model"):
                continue
            if gpu.get("vgpu_profiles") is None:
                continue  # DISCOVERY_FAILED -> no target, leave to the engine
            vgpu_id = self._vgpu_id_for(hyper_id, pci_bus_id)
            with app.app_context():
                cards = list(
                    r.table("gpus")
                    .filter({"physical_device": vgpu_id})
                    .pluck("id", "operator_requested_profile", "operator_passthrough")
                    .run(db.conn)
                )
            if not cards:
                continue
            card = cards[0]
            card_id = card["id"]
            with app.app_context():
                vrow = r.table("vgpus").get(vgpu_id).run(db.conn) or {}
            # Operator intent: prefer the live vgpus row, but fall back to the
            # PERSISTENT gpus catalog when the row is fresh -- a hypervisor
            # restart deletes+recreates the vgpus row, dropping operator intent,
            # so without this the operator's forced passthrough/profile is lost
            # and the card has to be re-forced by hand after every reboot. The
            # catalog mirror (update_requested_profile / update_operator_passthrough)
            # is the durable copy; re-seeding here re-applies it automatically.
            requested_profile = vrow.get("requested_profile")
            operator_passthrough = bool(vrow.get("operator_passthrough"))
            if requested_profile is None and not operator_passthrough:
                requested_profile = card.get("operator_requested_profile")
                operator_passthrough = bool(card.get("operator_passthrough"))
            available_types = {s: {} for s in (realizable_suffixes(gpu) or set())}
            # Default an un-booked, un-intented card to the profile it is ALREADY
            # running (keep_current, ephemeral -- no requested_profile write)
            # instead of forcing passthrough, but ONLY for a real non-passthrough
            # carve the card can still expose. passthrough/uncarved keep the
            # seed_and_apply default so a fresh card still seeds operator intent.
            live = gpu.get("current_profile")
            realizable = {canonical_suffix(s) for s in available_types}
            if live and live != "passthrough" and canonical_suffix(live) in realizable:
                fallback_default, keep_current = live, True
            else:
                fallback_default, keep_current = "passthrough", False
            decision = decide_reconcile_action(
                requested_profile=requested_profile,
                scheduled_profile=self.get_vgpu_scheduled_profile_now(card_id),
                available_types=available_types,
                sriov_totalvfs=(vrow.get("info") or {}).get("sriov_totalvfs", 0),
                operator_passthrough=operator_passthrough,
                fallback_default=fallback_default,
                keep_current=keep_current,
            )
            targets[pci_bus_id] = {
                "vgpu_id": vgpu_id,
                "card_id": card_id,
                "action": decision["action"],
                "target_profile": decision.get("profile"),
            }
        return targets

    def ingest_gpu_applied(self, hyper_id, applied):
        """Persist the hypervisor's applied-state report (from the gpu_applied
        endpoint) into the vgpus rows so the DB reflects reality and the engine
        reconcile confirms instead of re-applying. Only 'applied' results carry
        a rebuilt mdev pool worth persisting; everything else is left alone."""
        from isardvdi_common.vgpu_state import build_applied_state_patch

        if not isinstance(applied, dict):
            return
        for pci_bus_id, rep in applied.items():
            if not isinstance(rep, dict):
                continue
            result = rep.get("result")
            # noop / skipped_busy / skipped_advisory: nothing was applied, but
            # the card's existing pool is still valid (a live desktop's mdev
            # survives discovery's reset). Re-pin ONLY mdevs_last_synced_at to
            # this discovery's mdevs_reset_at so the engine reconcile CONFIRMS
            # instead of running the authoritative rebuild that would stop the
            # still-alive desktop. Never touch the pool/profile here. An 'error'
            # result is NOT re-pinned (the state is uncertain -> let reconcile
            # decide).
            if result in ("noop", "skipped_busy", "skipped_advisory"):
                reset_at = rep.get("mdevs_reset_at")
                if reset_at is None:
                    continue
                vgpu_id = self._vgpu_id_for(hyper_id, pci_bus_id)
                with app.app_context():
                    r.table("vgpus").get(vgpu_id).update(
                        {"mdevs_last_synced_at": reset_at}
                    ).run(db.conn)
                continue
            if result != "applied":
                continue
            applied_profile = rep.get("applied_profile")
            if not applied_profile:
                continue
            vgpu_id = self._vgpu_id_for(hyper_id, pci_bus_id)
            with app.app_context():
                existing = r.table("vgpus").get(vgpu_id).run(db.conn)
            patch = build_applied_state_patch(
                existing,
                applied_profile,
                rep.get("mdevs"),
                rep.get("mdevs_reset_at"),
            )
            if not existing:
                # First registration: the vgpus row does not exist yet (the
                # engine normally creates it). Establish it from the
                # hypervisor's applied report so the engine relies on what the
                # hypervisor set at boot instead of re-deriving passthrough. The
                # engine's next discovery fills in info/model and PRESERVES this
                # applied state (update_db_hyp_nvidia_info). conflict="update"
                # guards the race where the engine created the row meanwhile.
                row = {"id": vgpu_id, "hyp_id": hyper_id, "brand": "NVIDIA"}
                if rep.get("mdevs_reset_at") is not None:
                    row["mdevs_reset_at"] = rep.get("mdevs_reset_at")
                row.update(patch)
                # On the no-row path this inserts `row` as-is. On the engine-won-
                # the-race path the conflict FUNCTION runs: merge onto the engine's
                # row (keeping its info/model/nvidia_uids) but REPLACE mdevs via
                # r.literal -- otherwise the default deep-merge would DOUBLE the
                # pool (host UUIDs + engine phantoms). r.literal is only legal
                # inside merge/update, never in a bare insert doc (that raises
                # "Stray literal keyword found"), which is why this is a conflict
                # function and `row` itself keeps a plain mdevs dict.
                with app.app_context():
                    r.table("vgpus").insert(
                        row,
                        conflict=lambda _id, old, new: old.merge(new).merge(
                            {"mdevs": r.literal(new["mdevs"])}
                        ),
                    ).run(db.conn)
                log.info(
                    f"Ingested hypervisor-applied profile '{applied_profile}' "
                    f"for new card {vgpu_id}"
                )
                continue
            # The host is authoritative for the pool: REPLACE mdevs wholesale.
            # Plain .update() deep-merges nested dicts, which would leave stale
            # per-profile pools and double a same-profile re-register, so wrap it
            # in r.literal().
            if "mdevs" in patch:
                patch["mdevs"] = r.literal(patch["mdevs"])
            with app.app_context():
                r.table("vgpus").get(vgpu_id).update(patch).run(db.conn)
            log.info(
                f"Ingested hypervisor-applied profile '{applied_profile}' for "
                f"{vgpu_id}"
            )

    def preview_force_profile(self, card_id, target_profile):
        """Read-only pre-flight for the admin force-profile dialog. Returns what
        forcing ``target_profile`` on this card WOULD do, so the admin is warned
        before confirming. Mutates nothing.

        - ``desktops_to_stop``: running desktops on the card that the change
          would stop (a profile change stops every desktop on the card; none if
          the target equals the current profile).
        - ``resources_to_remove``: enabled reservables this card would stop
          realizing under the target's mode AND for which NO OTHER card in the
          infrastructure is a provider -> the reservable + its bookings would be
          pruned. Admin-only; end users are not notified.
        """
        from .gpu_realizability import canonical_suffix

        with app.app_context():
            card = r.table("gpus").get(card_id).run(db.conn)
        if not card:
            return {"desktops_to_stop": [], "resources_to_remove": []}
        vgpu_id = card.get("physical_device")
        vgpu_row = {}
        if vgpu_id:
            with app.app_context():
                vgpu_row = r.table("vgpus").get(vgpu_id).run(db.conn) or {}
        current = canonical_suffix(vgpu_row.get("vgpu_profile"))
        info_types = (vgpu_row.get("info") or {}).get("types", {}) or {}

        def _suffix(reservable_id):
            # NVIDIA-<model>-<suffix>; model is dash-free by construction, so the
            # suffix is everything after the first two hyphens. Canonicalize so a
            # dash-form MIG id (NVIDIA-A16-1-2Q) maps to the same key the rest of
            # the system uses (1_2Q) -- a plain split("-")[-1] would wrongly yield
            # "2Q" and misclassify it (false reassurance on dash-form installs).
            parts = reservable_id.split("-", 2)
            return canonical_suffix(parts[2]) if len(parts) == 3 else reservable_id

        def _is_mig(suffix):
            # authoritative mig flag from the card's live info.types when the
            # suffix is realized in the current mode; otherwise recognise both
            # dot-form MIG ("1g.24gb") and the MIG-slice vGPU form ("1_2Q"/"1-2Q")
            # so a dash-form MIG-backed vGPU is not misclassified as plain vGPU.
            t = info_types.get(suffix)
            if isinstance(t, dict) and "mig" in t:
                return bool(t["mig"])
            return bool(re.match(r"\d+g\.", suffix) or re.match(r"\d+[_-]\d", suffix))

        target_suffix = _suffix(target_profile)
        target_pt = target_suffix == "passthrough"
        target_mig = (not target_pt) and _is_mig(target_suffix)

        desktops = set()
        if target_suffix != current:
            for pool in (vgpu_row.get("mdevs") or {}).values():
                if not isinstance(pool, dict):
                    continue
                for mdev in pool.values():
                    started = isinstance(mdev, dict) and mdev.get("domain_started")
                    if isinstance(started, str) and started:
                        desktops.add(started)

        resources = []
        for reservable_id in card.get("profiles_enabled", []) or []:
            suffix = _suffix(reservable_id)
            if suffix == target_suffix:
                continue  # still realized
            if target_pt:
                still_realized = False  # passthrough realizes no vGPU/MIG profile
            elif target_mig:
                still_realized = _is_mig(suffix)  # MIG mode -> MIG profiles
            else:
                still_realized = suffix != "passthrough" and not _is_mig(suffix)
            if still_realized:
                continue
            with app.app_context():
                others = (
                    r.table("gpus")
                    .filter(
                        lambda g: g["profiles_enabled"].contains(reservable_id)
                        & g["id"].ne(card_id)
                        & g["physical_device"].default(None).ne(None)
                    )
                    .count()
                    .run(db.conn)
                )
            if others == 0:
                resources.append(reservable_id)

        return {
            "current_profile": current,
            "target_profile": target_suffix,
            "desktops_to_stop": sorted(desktops),
            "resources_to_remove": sorted(resources),
        }

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

    def update_hyper_numa_topology(self, hyper_id, numa_topology):
        if not isinstance(numa_topology, dict):
            return
        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"numa_topology": numa_topology}
            ).run(db.conn)

    def update_boot_progress(self, hyper_id, progress_data):
        with app.app_context():
            r.table("hypervisors").get(hyper_id).update(
                {"boot_progress": progress_data}
            ).run(db.conn)

    def remove_hyper(self, hyper_id, restart=True):
        # Clear physical_device on auto-created GPU cards for this hypervisor and
        # keep vGPU capacity (reservables_vgpus.total_units) honest: a detached
        # card has no hardware so it must stop counting toward capacity. We do
        # NOT touch profiles_enabled or bookings -> when the hypervisor returns
        # and re-registers, physical_device is restored and capacity recovers.
        try:
            prefix = f"auto-{hyper_id}-"
            with app.app_context():
                affected = list(
                    r.table("gpus")
                    .filter(lambda gpu: gpu["id"].match(f"^{prefix}"))
                    .concat_map(lambda gpu: gpu["profiles_enabled"].default([]))
                    .distinct()
                    .run(db.conn)
                )
                r.table("gpus").filter(
                    lambda gpu: gpu["id"].match(f"^{prefix}")
                ).update({"physical_device": None}).run(db.conn)
            from .bookings.api_reservables import Reservables

            api_ri = Reservables()
            for reservable_id in affected:
                try:
                    api_ri.recompute_reservable_total_units("gpus", reservable_id)
                except Exception as e:
                    log.warning(
                        f"remove_hyper: total_units recompute {reservable_id}: {e}"
                    )
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
