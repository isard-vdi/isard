# SPDX-License-Identifier: AGPL-3.0-or-later

"""A desktop's disk problems, the quick fixes run for them and the costly ones left."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

FixName = Literal[
    "check",
    "check_backing_chain",
    "repair_leaks",
    "repair_all",
    "dig_holes",
    "sparsify",
]


class FixEstimate(BaseModel):
    tier: Optional[str] = None
    ahead: Optional[int] = Field(None, description="Jobs queued before this one")
    wait_seconds: Optional[int] = None
    run_seconds: Optional[int] = None
    basis: Optional[str] = Field(
        None, description="history, size or default: what run_seconds rests on"
    )
    has_consumer: Optional[bool] = None
    stranded: Optional[bool] = None


class StorageProblem(BaseModel):
    code: str
    fix: Optional[FixName] = None
    blocks_start: bool = True
    mode: Literal["wait", "quick", "costly", "admin"]
    allowed: bool = Field(
        False, description="The caller may run this problem's fix from the desktop"
    )
    pending_since: Optional[int] = None
    estimate: Optional[FixEstimate] = None


class RunningTask(BaseModel):
    id: str
    task: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    position: Optional[int] = None
    eta_seconds: Optional[float] = None
    stranded: Optional[bool] = None


class DiskProblems(BaseModel):
    storage_id: str
    status: Optional[str] = None
    size: Optional[int] = None
    problems: list[StorageProblem]
    task: Optional[RunningTask] = None


class QuickFixRun(BaseModel):
    storage_id: str
    fix: FixName
    task_id: Optional[str] = None
    refused: Optional[str] = Field(
        None, description="Why the fix could not be queued now"
    )
    recorded: Optional[str] = Field(
        None, description="The pending action recorded instead, for the sweep"
    )


class DesktopStorageProblemsResponse(BaseModel):
    desktop_id: str
    can_repair_costly: bool = Field(
        description="The caller may run the costly repairs of this desktop's disks"
    )
    disks: list[DiskProblems]
    quick_fixes: list[QuickFixRun] = Field(
        default_factory=list,
        description="The quick fixes this call queued or recorded",
    )


class StorageFixResponse(BaseModel):
    task_id: str
    estimate: Optional[FixEstimate] = None
