#
#   Copyright © 2026 IsardVDI
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

"""Pydantic models for the admin storage-disk migration endpoints."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #
class MigrationWindowData(BaseModel):
    start: Optional[str] = None  # "HH:MM"
    end: Optional[str] = None  # "HH:MM"
    tz: str = "UTC"
    #: weekdays the window is active, Mon=0 … Sun=6. Empty == every day.
    days: list[int] = Field(default_factory=list)


class MigrationSelectionData(BaseModel):
    """What a migration job moves and where to."""

    #: HOW the source disks are selected, not what type they are — see
    #: `item_kinds` for that.
    kind: Literal["pool", "path", "category"] = "pool"
    src_pool_id: Optional[str] = None
    dst_pool_id: Optional[str] = None
    category_id: Optional[str] = None
    path_prefix: Optional[str] = None
    tree_ids: list[str] = Field(default_factory=list)
    #: Which disk KINDS actually move. Empty or absent == all of them. The rest
    #: of the chain is still walked, to know what backs what, but stays put.
    item_kinds: list[Literal["desktop", "template", "media"]] = Field(
        default_factory=list
    )


class MigrationConfigData(BaseModel):
    """Admin-set per-job knobs."""

    # 0 == unlimited (rsync --bwlimit, KB/s); negative would emit
    # --bwlimit=-N and fail every move.
    bwlimit_kbs: int = Field(default=0, ge=0)
    # concurrent independent trees; an unbounded value defeats the throttle and
    # mass-flips storage rows to maintenance.
    parallelism: int = Field(default=1, ge=1, le=64)
    window: Optional[MigrationWindowData] = None
    verify: bool = True  # qemu_img_check after move/rebase
    force_stop_desktops: bool = False
    #: one-shot (False) vs recurring re-scan (True). Recurring requires a window.
    recurring: bool = False
    #: recurring re-scan cadence (edge | edge_on_drain | continuous).
    rescan_cadence: Literal["edge", "edge_on_drain", "continuous"] = "edge_on_drain"
    #: disk-failure policy (retry_quarantine | pause | retry_forever).
    failure_policy: Literal["retry_quarantine", "pause", "retry_forever"] = (
        "retry_quarantine"
    )
    #: consecutive-occurrence failure budget before quarantine (retry_quarantine).
    quarantine_after: int = Field(default=3, ge=1)
    #: Per-occurrence volume budget in bytes; 0 = unlimited. Operator-set on
    #: purpose: on a thin-provisioned pool (VDO) the filesystem reports LOGICAL
    #: free space while the real limit is physical fill, so no probe can size
    #: this safely. Gates only the START of a tree, so the last one may overshoot.
    max_bytes_per_occurrence: int = Field(default=0, ge=0)
    #: Order in which trees are STARTED. Only observable under a byte budget,
    #: where the tail of the list does not move this occurrence.
    order: Literal["none", "oldest_first", "newest_first"] = "none"
    #: Filesystem-level free-space floor on the destination, in bytes; 0 = off.
    #: Enforced by the worker immediately before each copy (the only place the
    #: number is true, and the only process that can see the pool mounts).
    #: NOT valid on thin-provisioned (VDO) pools -- see max_bytes_per_occurrence.
    min_free_bytes: int = Field(default=0, ge=0)


class MigrationPlanData(BaseModel):
    """Dry-run plan preview request — nothing is persisted.

    The config is optional and only two of its knobs change the preview
    (`order` and `max_bytes_per_occurrence`), but they change it decisively:
    without them the preview cannot say which trees would fall outside this
    occurrence's budget, and an admin would be approving a job whose actual
    effect is invisible until it runs.
    """

    selection: MigrationSelectionData
    config: MigrationConfigData = Field(default_factory=MigrationConfigData)


class MigrationCreateData(BaseModel):
    selection: MigrationSelectionData
    config: MigrationConfigData = Field(default_factory=MigrationConfigData)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #
class MigrationTreeSummary(BaseModel):
    tree_id: str
    root_storage_id: str
    #: usage key this tree was ordered by (epoch seconds); None == no usage data
    order_key: Optional[int] = None
    #: whether this tree fits inside `max_bytes_per_occurrence` in plan order.
    #: True everywhere when no budget is set.
    within_budget: bool = True
    derivative_templates: int = 0
    desktops: int = 0
    media: int = 0
    items_total: int = 0
    bytes_total: int = 0
    # live progress (present on status / socket; absent on dry-run plan)
    done: int = 0
    bytes_done: int = 0
    state_counts: dict = Field(default_factory=dict)


class MigrationItemSummary(BaseModel):
    """One disk in the per-job ledger, for the UI's per-tree expand."""

    id: Optional[str] = None
    storage_id: str
    tree_id: str
    topo_index: int = 0
    kind: Optional[str] = None
    state: str
    size_bytes: int = 0
    error: Optional[str] = None
    dst_path: Optional[str] = None


class MigrationTotalsResponse(BaseModel):
    trees: int = 0
    derivative_templates: int = 0
    desktops: int = 0
    media: int = 0
    items_total: int = 0
    #: count of disks grouped by item kind (template/desktop/media); these sum to
    #: items_total, unlike `trees` (a standalone desktop is its own tree root).
    items_by_kind: dict = Field(default_factory=dict)
    bytes_total: int = 0
    #: size in bytes grouped by item kind (template/desktop/media) so the UI
    #: can show a size next to each item-type count. Empty on older payloads.
    bytes_by_kind: dict = Field(default_factory=dict)
    bytes_done: int = 0
    #: live count of disks past the saga (released/skipped) — drives the UI's
    #: aggregate progress bar; 0 on the dry-run plan totals.
    done: int = 0
    state_counts: dict = Field(default_factory=dict)
    #: disks the selection walks but leaves in place. They carry no ledger row,
    #: so the plan preview is the only place they are ever visible.
    not_moving_total: int = 0
    not_moving_by_kind: dict = Field(default_factory=dict)
    #: the tree-start order this plan was built with (`none` unless asked for).
    order: str = "none"
    #: trees whose moving disks carry no usage date. They sort LAST in both
    #: directions, so a budget reaches them last either way.
    order_trees_without_usage: int = 0
    #: bytes/trees that fit in `max_bytes_per_occurrence`; equal to the totals
    #: when there is no budget.
    bytes_within_budget: int = 0
    trees_within_budget: int = 0


class MigrationPlanResponse(BaseModel):
    """Dry-run preview: what would move, grouped by root tree."""

    trees: list[MigrationTreeSummary] = Field(default_factory=list)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)


class PoolPlanResponse(BaseModel):
    """Pool-scoped aggregation for the admin overview."""

    pool_id: str
    trees: list[MigrationTreeSummary] = Field(default_factory=list)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)


class MigrationResponse(BaseModel):
    id: str
    status: str
    selection: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)
    created_by: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class MigrationListResponse(BaseModel):
    migrations: list[MigrationResponse] = Field(default_factory=list)


class MigrationStatusResponse(BaseModel):
    id: str
    status: str
    #: what this job moves and where to (src/dst pool ids, kind, path/category) so
    #: the admin table + detail can show the origin → destination route.
    selection: dict = Field(default_factory=dict)
    totals: MigrationTotalsResponse = Field(default_factory=MigrationTotalsResponse)
    state_counts: dict = Field(default_factory=dict)
    trees: list[MigrationTreeSummary] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)
    current_window: Optional[dict] = None
    eta_seconds: Optional[int] = None
    #: schedule surface for the admin table (recurring badge + days + next-run)
    recurring: bool = False
    days: list[int] = Field(default_factory=list)
    #: seconds until the next window opens on a selected weekday (None == always
    #: open / no schedule / cannot be computed)
    next_run_seconds: Optional[int] = None
    items: list[MigrationItemSummary] = Field(default_factory=list)


class MigrationPathPrefixesResponse(BaseModel):
    """Real, selectable source path-prefixes for the ``path`` selection kind —
    the distinct ``storage.directory_path`` values, optionally scoped to a source
    pool. Drives the UI dropdown (no free text)."""

    prefixes: list[str] = Field(default_factory=list)
