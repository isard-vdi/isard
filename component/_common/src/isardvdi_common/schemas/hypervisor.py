#
#   Copyright © 2025 Pau Abril Iranzo
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


from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from rethinkdb import r


class HypervisorStatus(str, Enum):
    """Closed status set enforced by the engine's ``update_hyp_status``
    whitelist (plus the ``Offline``/``Deleting`` writes in
    ``HypervisorsProcessed``)."""

    online = "Online"
    offline = "Offline"
    error = "Error"
    deleting = "Deleting"


class MountPoint(BaseModel):
    mount: str
    usage: int


class CPUStats(BaseModel):
    idle: float
    iowait: float
    kernel: float
    used: float
    user: float


class MemStats(BaseModel):
    available: int
    buffers: int
    cached: int
    free: int
    total: int


class LastAction(BaseModel):
    action: str
    action_time: float
    intervals: List[Dict[str, float]]
    timestamp: float


class Stats(BaseModel):
    cpu_15min: CPUStats
    cpu_1min: CPUStats
    cpu_5min: CPUStats
    cpu_current: CPUStats
    last_action: LastAction
    mem_stats: MemStats
    mem_stats_15min: MemStats
    mem_stats_1min: MemStats
    mem_stats_5min: MemStats
    positioned_items: List[Any]
    time: float


class ThreadStatus(BaseModel):
    disk_operations: str
    worker: str


class Viewer(BaseModel):
    html5_ext_port: str
    proxy_hyper_host: str
    proxy_video: str
    spice_ext_port: str
    static: str


class ViewerStatus(BaseModel):
    html5: bool
    spice: bool
    static: bool


class Wireguard(BaseModel):
    Address: str
    AllowedIPs: str
    connected: bool
    extra_client_nets: Optional[Any]
    keys: Dict[str, str]
    remote_ip: str
    remote_port: int


class Vpn(BaseModel):
    iptables: List[Any]
    wireguard: Wireguard


class CapStatus(BaseModel):
    disk_operations: bool = False
    hypervisor: bool = False
