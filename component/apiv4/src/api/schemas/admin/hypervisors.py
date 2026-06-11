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

from pydantic import BaseModel, Field, field_validator

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
    # Hypervisor-side discovery payload. Each list element is a dict with
    # the shape produced by ``docker/hypervisor/src/lib/gpu_discovery.py::
    # discover_gpus`` (pci_bus_id, name, gpu_uuid, memory_total_mb,
    # vgpu_profiles, mig_profiles, ...). When present, the api auto-
    # populates ``gpu_profiles`` and ``gpus`` rows via
    # ``HypervisorsProcessed.{resolve_gpu_models, ensure_gpu_profiles,
    # ensure_gpu_cards}`` so newly discovered hardware appears in the
    # admin GPU catalog without manual curation.
    nvidia_gpus: Optional[List[Dict[str, Any]]] = None
    force_get_hyp_info: bool = False
    min_free_mem_gb: int = 0
    storage_pools: Optional[str] = None
    virt_pools: Optional[str] = None
    buffering_hyper: bool = False
    gpu_only: bool = False
    # Self-reported KVM capability (replaces engine SSH probes for the same)
    kvm_module: Optional[str] = None
    nested: Optional[bool] = None
    # Per-NUMA hugepages availability discovered from /sys/devices/system/node/
    # at registration. Used by the engine balancer to pick the NUMA node with
    # most free hugepages for non-GPU desktops, and by ``add_memory_backing``
    # / ``add_numa_pinning`` to emit ``<numatune>`` + ``<cputune>`` XML.
    hugepages_info: Optional[Dict[str, Any]] = None
    # Sysfs-keyed PCI device inventory (``{"0000:41:00.0": {numa_node: 0,
    # vendor: "10de", ...}, ...}``). Used by the engine balancer to look up
    # ``gpu_numa_node`` for the NUMA-local placement of GPU passthrough
    # desktops; also drives the IO-thread pinning for virtio disks.
    pci_devices: Optional[Dict[str, Dict[str, Any]]] = None


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
    stats: Optional[OrchestratorHypervisorStats] = None
    orchestrator_managed: bool = False
    min_free_mem_gb: int = 0
    gpu_only: bool = False
    desktops_started: int = 0
    bookings_end_time: Optional[str] = None
    gpus: list[OrchestratorHypervisorGPU] = []

    @field_validator("stats", mode="before")
    @classmethod
    def _empty_stats_to_none(cls, v):
        # rdb seeds new hypervisor records with ``stats: {}`` until the
        # engine pushes the first sample; the empty dict would otherwise
        # fail the required cpu_*/mem_stats_* sub-field validation and
        # 500 the whole listing. Treat empty dict as "no stats yet".
        if isinstance(v, dict) and not v:
            return None
        return v


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
    kvm_module: Optional[str] = None
    nested: Optional[bool] = None
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
    """Body for ``POST /admin/items/vlans``.

    Sent by ``docker/hypervisor/src/vlans/vlans-db.py``: the hypervisor
    reports the set of VLAN identifiers it has discovered so the API
    can upsert the corresponding ``interfaces`` entries.
    """

    vlans: List[str]


class AdminBootProgressRequest(BaseModel):
    """Body for ``PUT /admin/item/hypervisor/{hyper_id}/boot_progress``.

    Carries a structured ``{step, total, label, error, timestamp}``
    payload. Stored verbatim in RethinkDB (``hypervisors.boot_progress``)
    and consumed by the changefeed / webapp for live progress reporting.
    """

    boot_progress: Dict[str, Any]


class AdminGpuAppliedRequest(BaseModel):
    """Body for ``PUT /admin/item/hypervisor/{hyper_id}/gpu_applied``.

    A gpu-apply-capable hypervisor reports back, after registration, the
    per-card profile it actually applied locally (+ the created mdev
    pool): ``{pci_bus_id: {result, profile, mdevs, ...}}``. Persisted
    into ``vgpus`` so the DB reflects reality and the engine reconcile
    confirms instead of re-applying.
    """

    applied: Dict[str, Any]


class AdminGpuForceProfilePreviewRequest(BaseModel):
    """Body for ``POST /admin/item/hypervisor/gpus/{card_id}/force_profile_preview``."""

    target_profile: str


class AdminGpuForceProfilePreviewResponse(BaseModel):
    """Read-only pre-flight for the admin force-profile dialog: which
    running desktops would be stopped and which reservables would be
    removed (no other card provides them) if this card is forced to
    ``target_profile``. ``current_profile``/``target_profile`` are absent
    when the card row does not exist."""

    current_profile: Optional[str] = None
    target_profile: Optional[str] = None
    desktops_to_stop: List[str]
    resources_to_remove: List[str]


class AdminHypervisorWgAddrResponse(BaseModel):
    """Response for ``GET /admin/item/hypervisor/vm/wg_addr`` — the wireguard
    table lookup result for the hypervisor host."""

    model_config = {"extra": "allow"}


class AdminHypervisorMediaFoundResponse(BaseModel):
    """Response for ``POST /admin/item/hypervisor/media_found`` — the
    matched media list returned to the hypervisor."""

    model_config = {"extra": "allow"}


class AdminHypervisorDisksFoundResponse(BaseModel):
    """Response for ``POST /admin/item/hypervisor/disks_found`` — the
    matched disks list returned to the hypervisor."""

    model_config = {"extra": "allow"}


class AdminHypervisorMediaDeleteResponse(BaseModel):
    """Response for ``POST /admin/item/hypervisor/media_delete``."""

    model_config = {"extra": "allow"}


class AdminHypervisorVirtPool(BaseModel):
    """One row of ``GET /admin/items/hypervisor/{hyper_id}/virt_pools``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = None


class AdminHypervisorMountpoint(BaseModel):
    """One row of ``GET /admin/items/hypervisor/mountpoints/{hyper_id}``."""

    model_config = {"extra": "allow"}


class AdminHypervisorStartedDomain(BaseModel):
    """One row of ``GET /admin/items/hypervisor/started_domains/{hyper_id}``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    name: Optional[str] = None
    user: Optional[str] = None


class AdminHypervisorGpu(BaseModel):
    """One row of ``GET /admin/items/hypervisors/gpus``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None


class AdminVlanRegistration(BaseModel):
    """Response for ``POST /admin/items/vlans`` — interface upsert result."""

    model_config = {"extra": "allow"}


class AdminBootProgressResponse(BaseModel):
    """Response for ``PUT /admin/item/hypervisor/{hyper_id}/boot_progress``."""

    model_config = {"extra": "allow"}


class AdminHypervisorStatusResponse(BaseModel):
    """Response for ``GET /admin/item/hypervisor/status/{hyper_id}`` —
    the trimmed status row (id, status, only_forced).
    """

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    status: Optional[str] = None
    only_forced: Optional[bool] = None


class AdminHypervisorCreateResponse(BaseModel):
    """Response for ``POST /admin/item/hypervisor``."""

    model_config = {"extra": "allow"}


class AdminHypervisorEnableResponse(BaseModel):
    """Response for ``PUT /admin/item/hypervisor/{hyper_id}``."""

    model_config = {"extra": "allow"}


class AdminHypervisorVpnResponse(BaseModel):
    """Response for ``GET /admin/item/hypervisor_vpn/{hyper_id}``."""

    model_config = {"extra": "allow"}
