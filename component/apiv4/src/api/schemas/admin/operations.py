#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

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
