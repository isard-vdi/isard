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

from pydantic import BaseModel, ConfigDict, Field


class LabOptsModel(BaseModel):
    """Per-interface "lab options" for network laboratory use. Each flag, when
    True, relaxes one OVS port protection in the hypervisor
    (docker/hypervisor/src/ovs/ovs-worker.py); all default False so the
    hypervisor emits the strict anti-MAC-spoofing flow set (identical to legacy
    behaviour). Every flag is restricted at the service layer to
    kind=ovs/personal and never on VLAN 4095 (wireguard infra). Legacy rows
    without this field default to all-False -> strict (backward compatible, no
    DB migration). Pydantic is the schema source of truth in apiv4 and
    normalises the raw admin-table dict to a canonical four-bool document
    before write, so the engine always reads a definite value.

      mac_spoofing        accept arbitrary source MACs + same-port hairpin
      stp_bpdu            tunnel guest STP BPDUs over the VLAN/geneve overlay
      broadcast_unlimited raise the per-port broadcast meter to the lab ceiling
      multicast_unlimited raise the per-port multicast meter to the lab ceiling
    """

    model_config = ConfigDict(extra="forbid")

    mac_spoofing: bool = Field(default=False)
    stp_bpdu: bool = Field(default=False)
    broadcast_unlimited: bool = Field(default=False)
    multicast_unlimited: bool = Field(default=False)
