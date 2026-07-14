#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.schemas.hypervisor import (
    CapStatus,
    MountPoint,
    Stats,
    Viewer,
    ViewerStatus,
    Vpn,
)
from pydantic import BaseModel
from rethinkdb import r


class HypervisorModel(BaseModel):
    buffering_hyper: bool
    cap_status: CapStatus = CapStatus()
    capabilities: CapStatus
    description: str
    detail: str = ""
    enabled: bool = False
    enabled_storage_pools: List[str] = []
    enabled_virt_pools: List[str] = []
    force_get_hyp_info: bool
    gpu_only: bool
    hostname: str
    hypervisors_pools: List[str] = []
    id: str
    info: Dict[str, Any] = {}
    isard_hyper_vpn_host: str
    kvm_module: Optional[str] = None
    min_free_gpu_mem_gb: int
    min_free_mem_gb: int
    mountpoints: List[MountPoint] = []
    nested: Optional[bool] = None
    nvidia_enabled: bool
    only_forced: bool
    port: str
    prev_status: List[Dict[str, Any]] = []
    stats: Optional[Stats] = None
    status: str = "Offline"
    status_time: Optional[float] = None
    storage_pools: List[str] = []
    uri: str = ""
    user: str = ""
    viewer: Optional[Viewer] = None
    viewer_status: Optional[ViewerStatus] = None
    virt_pools: List[str] = []
    vpn: Optional[Vpn] = None


class Hypervisor(RethinkCustomBase):
    """
    Manage Hypervisor Objects

    Use constructor with keyword arguments to create new Hypervisor Objects or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Hypervisor Object.
    """

    _rdb_table = "hypervisors"

    @classmethod
    def get_hypervisor(cls, hypervisor_id):
        with cls._rdb_context():
            hypervisor = (
                r.table("hypervisors")
                .get(hypervisor_id)
                .merge(
                    lambda hyper: {
                        "gpus": r.table("vgpus")
                        .filter({"hyp_id": hyper["id"]})["id"]
                        .coerce_to("array"),
                        "physical_gpus": r.table("gpus")
                        .filter(lambda gpu: gpu["physical_device"].ne(None))[
                            "physical_device"
                        ]
                        .coerce_to("array"),
                        "desktops_started": r.table("domains")
                        .get_all(hyper["id"], index="hyp_started")
                        .count(),
                    }
                )
                .run(cls._rdb_connection)
            )
        return hypervisor

    @classmethod
    def count_started_desktops(cls, hypervisor_id):
        with cls._rdb_context():
            return (
                r.table("domains")
                .get_all(hypervisor_id, index="hyp_started")
                .count()
                .run(cls._rdb_connection)
            )
