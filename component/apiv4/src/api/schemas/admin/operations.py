#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, List, Optional

from pydantic import BaseModel


class OperationsHypervisorResponse(BaseModel):
    """Operations hypervisor info"""

    id: str
    state: str
    isard_state: Optional[str] = None
    orchestrator_managed: Optional[Any] = None
    only_forced: Optional[Any] = None
    buffering_hyper: Optional[Any] = None
    destroy_time: Optional[Any] = None
    gpu_only: Optional[Any] = None
    desktops_started: Optional[Any] = None
    cpu: Optional[int] = None
    ram: Optional[int] = None
    capabilities: Optional[List[str]] = None
    gpus: Optional[List[str]] = None
    destroy_allowed: Optional[bool] = None


class HypervisorActionResponse(BaseModel):
    """Result of ``PUT /admin/item/operations/hypervisor/{id}`` (start) and
    ``DELETE /admin/item/operations/hypervisor/{id}`` (stop). The fields
    come straight from the operations gRPC ``CreateHypervisorResponse``
    / ``DestroyHypervisorResponse`` proto.
    """

    state: Optional[str] = None
    msg: Optional[str] = None
