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
from typing import Optional, Union

from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.hypervisors.hypervisors import HypervisorsProcessed

# GENEVE / WireGuard encapsulation overheads. Canonical arithmetic lives in
# docker/vpn/ovs/ovs_setup.sh (it physically sizes vlan-wg/ovsbr0); this is a
# faithful port. Keep both in sync.
_GENEVE_OH = 54  # 20 IP + 8 UDP + 8 geneve + 14 eth + 4 VLAN
_WG_OH = 60  # 20 IP + 8 UDP + 32 WG


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


class AdminHypervisorsService:
    """
    Service for admin hypervisor management operations.
    """

    # ── List / Get ───────────────────────────────────────────────────────

    @staticmethod
    def get_hypervisors(status: Optional[str] = None) -> list[dict]:
        """List hypervisors, optionally filtered by status."""
        if status and status not in ["Online", "Offline", "Error"]:
            raise Error(
                "bad_request",
                "Hypervisor status incorrect",
            )
        return HypervisorsProcessed.get_hypervisors(status)

    @staticmethod
    def get_hyper_status(hyper_id: str) -> dict:
        """Get hypervisor status and only_forced flag."""
        return HypervisorsProcessed.get_hyper_status(hyper_id)

    # ── Create / Update / Delete ─────────────────────────────────────────

    @staticmethod
    def create_or_update_hypervisor(data: dict) -> dict:
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
            nvidia_gpus=data.get("nvidia_gpus"),
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
            pci_devices=data.get("pci_devices"),
            kvm_module=data.get("kvm_module"),
            nested=data.get("nested"),
        )
        if not result["status"]:
            raise Error("internal_server", "Failed hypervisor: " + result["msg"])
        # Persist tunneling mode to DB so VPN container knows which mode to use
        geneve_only = os.environ.get("GENEVE_ONLY_INFRA", "false").lower() == "true"
        tunneling_mode = "geneve" if geneve_only else "wireguard+geneve"
        vpn_update = {"tunneling_mode": tunneling_mode}
        # Always publish the derived tenant-overlay guest-MTU ceiling so the
        # engine can enforce it on the guest virtio NIC (VIRTIO_NET_F_MTU);
        # INFRASTRUCTURE_MTU defaults to 1500 when unset. guest_mtu mirrors
        # the canonical arithmetic in docker/vpn/ovs/ovs_setup.sh.
        infra_mtu = int(os.environ.get("INFRASTRUCTURE_MTU", "") or "1500")
        vpn_update["infrastructure_mtu"] = infra_mtu
        vpn_update["guest_mtu"] = _overlay_max(infra_mtu, tunneling_mode)
        HypervisorsProcessed.update_vpn_field(hyper_id, vpn_update)
        result["data"]["vpn"] = result["data"].get("vpn", {})
        result["data"]["vpn"].update(vpn_update)
        return result["data"]

    @staticmethod
    def _normalize_gpu_model(
        gpu_name: str, vgpu_profiles: Optional[list[dict]] = None
    ) -> str:
        """Dash- and slash-free model name (same logic as hypervisor gpu_discovery).

        Must stay in lockstep with the hypervisor-side ``normalize_gpu_model``
        and the ``_common`` mirror: the BRAND-MODEL-PROFILE id is used verbatim
        as a URL path segment, so a '/' in the model (e.g. the A16 die name
        "GA107GL [A2 / A16]") would inject an extra path segment and 405 the
        reservables route.
        """
        if vgpu_profiles:
            return vgpu_profiles[0]["name"].split("-")[0].replace("/", "")
        return (
            gpu_name.replace("NVIDIA ", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("/", "")
        )

    @staticmethod
    def update_hyper_numa_topology(hyper_id: str, numa_topology: dict) -> None:
        """Refresh hypervisor numa_topology (libvirt-validated, sent at enable time)."""
        HypervisorsProcessed.update_hyper_numa_topology(hyper_id, numa_topology)

    @staticmethod
    def update_hyper_boot_progress(hyper_id: str, boot_progress: dict) -> None:
        """Refresh hypervisor boot_progress payload (called from monitoring agents)."""
        HypervisorsProcessed.update_hyper_boot_progress(hyper_id, boot_progress)

    @staticmethod
    def register_vlans(vlans: list[str]) -> None:
        """Insert or update bridge interfaces for VLANs discovered on a hypervisor."""
        HypervisorsProcessed.register_vlans(vlans)

    @staticmethod
    def enable_hyper(hyper_id: str, enable: bool = True) -> dict:
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
    def remove_hyper(hyper_id: str) -> dict:
        """Remove a hypervisor."""
        result = HypervisorsProcessed.remove_hyper(hyper_id)
        if not result["status"]:
            raise Error(
                "bad_request",
                result["msg"],
            )
        return result["data"]

    @staticmethod
    def stop_hyper_domains(hyper_id: str) -> None:
        """Stop all domains running on a hypervisor."""
        HypervisorsProcessed.stop_hyper_domains(hyper_id)

    # ── VPN ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_hypervisor_vpn(hyper_id: str) -> dict:
        """Get VPN config for a hypervisor."""
        return HypervisorsProcessed.get_hypervisor_vpn(hyper_id)

    # ── Wireguard Address ────────────────────────────────────────────────

    @staticmethod
    def update_wg_address(mac: str, ip: str) -> dict:
        """Update wireguard guest address for a domain by MAC."""
        domain_id = HypervisorsProcessed.update_wg_address(
            mac, {"viewer": {"guest_ip": ip}}
        )
        return {"domain_id": domain_id}

    # ── Media / Disks Discovery ──────────────────────────────────────────

    @staticmethod
    def update_media_found(medias: list) -> None:
        """Register media found on hypervisor."""
        HypervisorsProcessed.update_media_found(medias)

    @staticmethod
    def update_disks_found(disks: list) -> None:
        """Register disks found on hypervisor."""
        HypervisorsProcessed.update_disks_found(disks)

    @staticmethod
    def delete_media(medias_paths: list) -> None:
        """Delete media by paths."""
        HypervisorsProcessed.delete_media(medias_paths)

    # ── GPU Management ───────────────────────────────────────────────────

    @staticmethod
    def assign_gpus() -> None:
        """Assign physical GPUs to GPU profiles."""
        HypervisorsProcessed.assign_gpus()

    # ── Orchestrator ─────────────────────────────────────────────────────

    @staticmethod
    def get_orchestrator_hypervisors(
        hyp_id: Optional[str] = None,
    ) -> Union[dict, list[dict]]:
        """Get hypervisors with orchestrator pluck fields."""
        return HypervisorsProcessed.get_orchestrator_hypervisors(hyp_id=hyp_id)

    @staticmethod
    def get_orchestrator_managed_hypervisors() -> list[dict]:
        """Get only orchestrator-managed hypervisors."""
        return HypervisorsProcessed.get_orchestrator_managed_hypervisors()

    @staticmethod
    def set_hyper_deadrow_time(hyper_id: str, reset: bool = False) -> Union[dict, bool]:
        """Set or reset dead row timeout for a hypervisor."""
        return HypervisorsProcessed.set_hyper_deadrow_time(hyper_id, reset=reset)

    @staticmethod
    def set_hyper_orchestrator_managed(hyper_id: str, reset: bool = False) -> None:
        """Mark or unmark a hypervisor for orchestrator management."""
        HypervisorsProcessed.set_hyper_orchestrator_managed(hyper_id, reset=reset)

    # ── Virt Pools ───────────────────────────────────────────────────────

    @staticmethod
    def get_hyper_virt_pools(hyper_id: str) -> list[dict]:
        """Get virt pools for a hypervisor."""
        return HypervisorsProcessed.get_hyper_virt_pools(hyper_id)

    @staticmethod
    def update_hyper_virt_pools(hyper_id: str, data: dict) -> None:
        """Update virt pool assignment for a hypervisor."""
        HypervisorsProcessed.update_hyper_virt_pools(hyper_id, data)

    # ── Mountpoints & Started Domains ────────────────────────────────────

    @staticmethod
    def get_hyper_mountpoints(hyper_id: str) -> list[dict]:
        """Get mountpoints for a hypervisor."""
        return HypervisorsProcessed.get_hyper_mountpoints(hyper_id)["mountpoints"]

    @staticmethod
    def get_hyper_started_domains(hyper_id: str) -> list[dict]:
        """Get started domains on a hypervisor."""
        return HypervisorsProcessed.get_hyper_started_domains(hyper_id)
