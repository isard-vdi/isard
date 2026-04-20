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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ── Hypervisor CRUD ──────────────────────────────────────────────────────


class AdminHypervisorCreateData(BaseModel):
    """Request body for creating/registering a hypervisor."""

    hyper_id: str
    hostname: str
    user: str = "root"
    port: str = "2022"
    cap_disk: bool = True
    cap_hyper: bool = True
    enabled: bool = False
    browser_port: str = "443"
    spice_port: str = "80"
    isard_static_url: Optional[str] = None
    isard_video_url: Optional[str] = None
    isard_proxy_hyper_url: str = "isard-hypervisor"
    isard_hyper_vpn_host: Optional[str] = None
    description: str = "Added via api"
    only_forced: bool = False
    nvidia_enabled: bool = False
    force_get_hyp_info: bool = False
    min_free_mem_gb: int = 0
    storage_pools: Optional[str] = None
    virt_pools: Optional[str] = None
    buffering_hyper: bool = False
    gpu_only: bool = False


class AdminHypervisorEnableData(BaseModel):
    """Request body for enabling/disabling a hypervisor."""

    enabled: bool = True
    numa_topology: Optional[Dict[str, Any]] = None


# ── Hypervisor Internal (hyper-to-api) ───────────────────────────────────


class AdminHypervisorWgAddrData(BaseModel):
    """Request body for updating wireguard address."""

    mac: str
    ip: str


class AdminHypervisorMediaFoundData(BaseModel):
    """Request body for reporting media found on hypervisor."""

    medias: list


class AdminHypervisorDisksFoundData(BaseModel):
    """Request body for reporting disks found on hypervisor."""

    disks: list


class AdminHypervisorMediaDeleteData(BaseModel):
    """Request body for deleting media paths."""

    medias_paths: list


# ── Virt Pools ───────────────────────────────────────────────────────────


class AdminHypervisorVirtPoolUpdateData(BaseModel):
    """Request body for updating hypervisor virt pool assignment."""

    id: str = Field(description="Virt pool ID")
    enable_virt_pool: bool = Field(description="Enable or disable the virt pool")


# -- Response models --


class OrchestratorHypervisorStatsCPU(BaseModel):
    idle: float
    iowait: float
    kernel: float
    used: float
    user: float


class OrchestratorHypervisorStatsMem(BaseModel):
    available: int
    buffers: int
    cached: int
    free: int
    total: int
    used: int
    hugepages_total_kb: Optional[int] = None
    hugepages_free_kb: Optional[int] = None
    hugepages_used_kb: Optional[int] = None


class OrchestratorHypervisorStats(BaseModel):
    cpu_current: OrchestratorHypervisorStatsCPU
    cpu_5min: OrchestratorHypervisorStatsCPU
    cpu_15min: OrchestratorHypervisorStatsCPU
    cpu_1min: OrchestratorHypervisorStatsCPU
    mem_stats: OrchestratorHypervisorStatsMem
    mem_stats_1min: OrchestratorHypervisorStatsMem
    mem_stats_5min: OrchestratorHypervisorStatsMem
    mem_stats_15min: OrchestratorHypervisorStatsMem
    time: float
    positioned_items: list = []


class OrchestratorHypervisorGPU(BaseModel):
    id: str
    total_units: int
    used_units: int
    free_units: int
    brand: str
    model: str
    profile: str


class OrchestratorHypervisor(BaseModel):
    id: str
    status: str
    only_forced: bool = False
    buffering_hyper: bool = False
    destroy_time: Optional[str] = None
    stats: dict = {}
    orchestrator_managed: bool = False
    min_free_mem_gb: int = 0
    gpu_only: bool = False
    desktops_started: int = 0
    bookings_end_time: Optional[str] = None
    gpus: list[OrchestratorHypervisorGPU] = []


class OrchestratorManagedHypervisor(BaseModel):
    id: str
    info: Optional[dict] = None
    stats: Optional[dict] = None
    status: str
    destroy_time: Optional[str] = None
    status_time: Optional[str] = None
    desktops_started: int = 0


class DeadRowSetResponse(BaseModel):
    destroy_time: str


class AdminHypervisorCapabilities(BaseModel):
    disk_operations: bool
    hypervisor: bool


class AdminHypervisorViewer(BaseModel):
    static: Optional[str] = None
    proxy_video: Optional[str] = None
    spice_ext_port: Optional[str] = None
    html5_ext_port: Optional[str] = None
    proxy_hyper_host: Optional[str] = None


class AdminHypervisor(BaseModel):
    id: str
    hostname: str
    port: str
    description: str
    capabilities: AdminHypervisorCapabilities
    only_forced: bool
    min_free_mem_gb: int
    min_free_gpu_mem_gb: int
    nvidia_enabled: bool
    force_get_hyp_info: bool
    buffering_hyper: bool
    gpu_only: bool
    isard_hyper_vpn_host: str
    status: str = "Offline"
    user: str = ""
    enabled: bool = False
    detail: str = ""
    uri: str = ""
    status_time: int = 0
    info: dict = {}
    cap_status: dict = {}
    hypervisors_pools: list[str] = []
    storage_pools: list[str] = []
    enabled_storage_pools: list[str] = []
    virt_pools: list[str] = []
    enabled_virt_pools: list[str] = []
    prev_status: list = []
    mountpoints: list = []
    stats: Optional[dict] = None
    viewer: Optional[AdminHypervisorViewer] = None
    viewer_status: Optional[dict] = None
    vpn: Optional[dict] = None
    desktops_started: int = 0
    gpus: list[str] = []
    physical_gpus: list[str] = []
    orchestrator_managed: Optional[bool] = None
    boot_progress: Optional[dict] = None
    degraded: Optional[dict] = None
    libvirt_warning: Optional[dict] = None
    icon: Optional[str] = None
    isard_static_url: Optional[str] = None
    isard_video_url: Optional[str] = None
    isard_proxy_hyper_url: Optional[str] = None


# ── Admin-internal bodies ────────────────────────────────────────────────


class AdminRegisterVlansRequest(BaseModel):
    """Body for ``POST /admin/vlans``.

    Sent by ``docker/hypervisor/src/vlans/vlans-db.py``: the hypervisor
    reports the set of VLAN identifiers it has discovered so the API
    can upsert the corresponding ``interfaces`` entries.
    """

    vlans: List[str]


class AdminBootProgressRequest(BaseModel):
    """Body for ``PUT /admin/hypervisor/{hyper_id}/boot_progress``.

    Carries a structured ``{step, total, label, error, timestamp}``
    payload. Stored verbatim in RethinkDB (``hypervisors.boot_progress``)
    and consumed by the changefeed / webapp for live progress reporting.
    """

    boot_progress: Dict[str, Any]
