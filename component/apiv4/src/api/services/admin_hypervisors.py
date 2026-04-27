#
#   Copyright © 2025 IsardVDI
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

import logging as log
import os

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed


class AdminHypervisorsService:
    """
    Service for admin hypervisor management operations.
    """

    # ── List / Get ───────────────────────────────────────────────────────

    @staticmethod
    def get_hypervisors(status=None):
        """List hypervisors, optionally filtered by status."""
        if status and status not in ["Online", "Offline", "Error"]:
            raise Error(
                "bad_request",
                "Hypervisor status incorrect",
            )
        return HypervisorsProcessed.get_hypervisors(status)

    @staticmethod
    def get_hyper_status(hyper_id):
        """Get hypervisor status and only_forced flag."""
        return HypervisorsProcessed.get_hyper_status(hyper_id)

    # ── Create / Update / Delete ─────────────────────────────────────────

    @staticmethod
    def create_or_update_hypervisor(data):
        """Create or update a hypervisor (register from hyper node)."""
        hyper_id = data["hyper_id"]
        hostname = data["hostname"]

        storage_pools_str = data.get("storage_pools") or DEFAULT_STORAGE_POOL_ID
        enabled_storage_pools = storage_pools_str.split(",")
        virt_pools_str = data.get("virt_pools") or storage_pools_str
        if virt_pools_str == "":
            virt_pools = enabled_virt_pools = storage_pools_str.split(",")
        else:
            virt_pools = virt_pools_str.split(",")
            enabled_virt_pools = virt_pools
        storage_pools = storage_pools_str.split(",")

        result = HypervisorsProcessed.hyper(
            hyper_id,
            hostname,
            port=data.get("port", "2022"),
            cap_disk=data.get("cap_disk", True),
            cap_hyper=data.get("cap_hyper", True),
            enabled=data.get("enabled", False),
            browser_port=data.get("browser_port", "443"),
            spice_port=data.get("spice_port", "80"),
            isard_static_url=data.get("isard_static_url")
            or os.environ.get("DOMAIN", ""),
            isard_video_url=data.get("isard_video_url") or os.environ.get("DOMAIN", ""),
            isard_proxy_hyper_url=data.get("isard_proxy_hyper_url", "isard-hypervisor"),
            isard_hyper_vpn_host=data.get("isard_hyper_vpn_host")
            or os.environ.get("DOMAIN", ""),
            nvidia_enabled=data.get("nvidia_enabled", False),
            force_get_hyp_info=data.get("force_get_hyp_info", False),
            description=data.get("description", "Added via api"),
            user=data.get("user", "root"),
            only_forced=data.get("only_forced", False),
            min_free_mem_gb=data.get("min_free_mem_gb", 0),
            storage_pools=storage_pools,
            enabled_storage_pools=enabled_storage_pools,
            virt_pools=virt_pools,
            enabled_virt_pools=enabled_virt_pools,
            buffering_hyper=data.get("buffering_hyper", False),
            gpu_only=data.get("gpu_only", False),
            hugepages_info=data.get("hugepages_info"),
        )
        if not result["status"]:
            raise Error("internal_server", "Failed hypervisor: " + result["msg"])
        # Persist tunneling mode to DB so VPN container knows which mode to use
        geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
        tunneling_mode = "geneve" if geneve_only else "wireguard+geneve"
        vpn_update = {"tunneling_mode": tunneling_mode}
        infra_mtu = os.environ.get("INFRASTRUCTURE_MTU")
        if infra_mtu:
            vpn_update["infrastructure_mtu"] = int(infra_mtu)
        HypervisorsProcessed.update_vpn_field(hyper_id, vpn_update)
        result["data"]["vpn"] = result["data"].get("vpn", {})
        result["data"]["vpn"].update(vpn_update)
        return result["data"]

    @staticmethod
    def _normalize_gpu_model(gpu_name, vgpu_profiles=None):
        """Dash-free model name (same logic as hypervisor gpu_discovery)."""
        if vgpu_profiles:
            return vgpu_profiles[0]["name"].split("-")[0]
        return gpu_name.replace("NVIDIA ", "").replace(" ", "").replace("-", "")

    @staticmethod
    def update_hyper_numa_topology(hyper_id, numa_topology):
        """Refresh hypervisor numa_topology (libvirt-validated, sent at enable time)."""
        HypervisorsProcessed.update_hyper_numa_topology(hyper_id, numa_topology)

    @staticmethod
    def update_hyper_boot_progress(hyper_id, boot_progress):
        """Refresh hypervisor boot_progress payload (called from monitoring agents)."""
        from isardvdi_common.connections.rethink_shared_connection import (
            RethinkSharedConnection,
        )
        from rethinkdb import r

        with RethinkSharedConnection._rdb_context():
            r.table("hypervisors").get(hyper_id).update(
                {"boot_progress": boot_progress}
            ).run(RethinkSharedConnection._rdb_connection)

    @staticmethod
    def register_vlans(vlans):
        """Insert or update bridge interfaces for VLANs discovered on a hypervisor."""
        from isardvdi_common.connections.rethink_shared_connection import (
            RethinkSharedConnection,
        )
        from rethinkdb import r

        with RethinkSharedConnection._rdb_context():
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
                r.db("isard").table("interfaces").insert(
                    new_vlan, conflict="update"
                ).run(RethinkSharedConnection._rdb_connection)

    @staticmethod
    def enable_hyper(hyper_id, enable=True):
        """Enable or disable a hypervisor."""
        if enable:
            log.warning("Enabling hypervisor: " + hyper_id)
        else:
            log.warning("Disabling hypervisor: " + hyper_id)
        result = HypervisorsProcessed.enable_hyper(hyper_id, enable)
        if not result["status"]:
            raise Error(
                "bad_request",
                "Hypervisor update bad data",
            )
        return result["data"]

    @staticmethod
    def remove_hyper(hyper_id):
        """Remove a hypervisor."""
        result = HypervisorsProcessed.remove_hyper(hyper_id)
        if not result["status"]:
            raise Error(
                "bad_request",
                result["msg"],
            )
        return result["data"]

    @staticmethod
    def stop_hyper_domains(hyper_id):
        """Stop all domains running on a hypervisor."""
        HypervisorsProcessed.stop_hyper_domains(hyper_id)

    # ── VPN ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_hypervisor_vpn(hyper_id):
        """Get VPN config for a hypervisor."""
        return HypervisorsProcessed.get_hypervisor_vpn(hyper_id)

    # ── Wireguard Address ────────────────────────────────────────────────

    @staticmethod
    def update_wg_address(mac, ip):
        """Update wireguard guest address for a domain by MAC."""
        domain_id = HypervisorsProcessed.update_wg_address(
            mac, {"viewer": {"guest_ip": ip}}
        )
        return {"domain_id": domain_id}

    # ── Media / Disks Discovery ──────────────────────────────────────────

    @staticmethod
    def update_media_found(medias):
        """Register media found on hypervisor."""
        HypervisorsProcessed.update_media_found(medias)

    @staticmethod
    def update_disks_found(disks):
        """Register disks found on hypervisor."""
        HypervisorsProcessed.update_disks_found(disks)

    @staticmethod
    def delete_media(medias_paths):
        """Delete media by paths."""
        HypervisorsProcessed.delete_media(medias_paths)

    # ── GPU Management ───────────────────────────────────────────────────

    @staticmethod
    def assign_gpus():
        """Assign physical GPUs to GPU profiles."""
        HypervisorsProcessed.assign_gpus()

    # ── Orchestrator ─────────────────────────────────────────────────────

    @staticmethod
    def get_orchestrator_hypervisors(hyp_id=None):
        """Get hypervisors with orchestrator pluck fields."""
        return HypervisorsProcessed.get_orchestrator_hypervisors(hyp_id=hyp_id)

    @staticmethod
    def get_orchestrator_managed_hypervisors():
        """Get only orchestrator-managed hypervisors."""
        return HypervisorsProcessed.get_orchestrator_managed_hypervisors()

    @staticmethod
    def set_hyper_deadrow_time(hyper_id, reset=False):
        """Set or reset dead row timeout for a hypervisor."""
        return HypervisorsProcessed.set_hyper_deadrow_time(hyper_id, reset=reset)

    @staticmethod
    def set_hyper_orchestrator_managed(hyper_id, reset=False):
        """Mark or unmark a hypervisor for orchestrator management."""
        HypervisorsProcessed.set_hyper_orchestrator_managed(hyper_id, reset=reset)

    # ── Virt Pools ───────────────────────────────────────────────────────

    @staticmethod
    def get_hyper_virt_pools(hyper_id):
        """Get virt pools for a hypervisor."""
        return HypervisorsProcessed.get_hyper_virt_pools(hyper_id)

    @staticmethod
    def update_hyper_virt_pools(hyper_id, data):
        """Update virt pool assignment for a hypervisor."""
        HypervisorsProcessed.update_hyper_virt_pools(hyper_id, data)

    # ── Mountpoints & Started Domains ────────────────────────────────────

    @staticmethod
    def get_hyper_mountpoints(hyper_id):
        """Get mountpoints for a hypervisor."""
        return HypervisorsProcessed.get_hyper_mountpoints(hyper_id)["mountpoints"]

    @staticmethod
    def get_hyper_started_domains(hyper_id):
        """Get started domains on a hypervisor."""
        return HypervisorsProcessed.get_hyper_started_domains(hyper_id)
