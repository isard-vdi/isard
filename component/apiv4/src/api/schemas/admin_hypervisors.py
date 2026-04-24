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

from typing import List, Optional

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
