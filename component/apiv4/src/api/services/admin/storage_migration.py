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

"""Admin storage-disk migration service.

Thin orchestration over ``isardvdi_common.lib.storage.migration`` (the plan /
selection / aggregation logic) and the ``StorageMigration`` /
``StorageMigrationItem`` ledger models. No DB driver calls live here.
"""

import hashlib
import json
from datetime import datetime, timezone
from os.path import dirname
from time import time
from zoneinfo import ZoneInfo

from api.services.error import Error
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.lib import queue_coverage, queue_tiers
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage.migration_run import DEFAULT_PRIORITY
from isardvdi_common.models.storage import get_queue_from_storage_pools
from isardvdi_common.models.storage_migration import (
    MigrationStatus,
    StorageMigration,
    StorageMigrationItem,
)
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task

#: Dry-run plan cache. The plan walks the storage tree, so identical selections
#: — e.g. the admin panel re-estimating as options are toggled back and forth —
#: reuse a recent result instead of re-resolving. Short TTL keeps the estimate
#: fresh; ``create`` clears it because the "already-in-destination" set shifts
#: as disks actually move. Keyed by the canonical selection only (parallelism /
#: bwlimit do not affect what would move — the UI derives the ETA client-side).
_PLAN_CACHE = SynchronizedTTLCache(maxsize=256, ttl=30)


def _plan_cache_key(selection: dict) -> str:
    return hashlib.sha1(
        json.dumps(selection, sort_keys=True, default=str).encode()
    ).hexdigest()


#: admin-driven status transitions exposed through the `{action}` route
_ACTION_TARGET = {
    "start": MigrationStatus.RUNNING.value,
    "pause": MigrationStatus.PAUSED.value,
    "cancel": MigrationStatus.CANCELED.value,
}
#: a job in one of these terminal states can no longer be controlled
_TERMINAL = {
    MigrationStatus.COMPLETED.value,
    MigrationStatus.FAILED.value,
    MigrationStatus.CANCELED.value,
}


def _tree_summaries(items):
    by_tree = {}
    for it in items:
        by_tree.setdefault(it["tree_id"], []).append(it)
    out = []
    for tree_id, tit in by_tree.items():
        s = mig.summarize_plan(tit)
        out.append(
            {
                "tree_id": tree_id,
                "root_storage_id": tree_id,
                "derivative_templates": s["derivative_templates"],
                "desktops": s["desktops"],
                "media": s["media"],
                "items_total": s["items_total"],
                "bytes_total": s["bytes_total"],
            }
        )
    return out


def _serialize(m: StorageMigration) -> dict:
    """Shape a ``StorageMigration`` object as an API dict (attrs are cached on
    construction, so this is cheap)."""
    return {
        "id": m.id,
        "status": m.status,
        "selection": m.selection or {},
        "config": m.config or {},
        "totals": m.totals or {},
        "created_by": m.created_by,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


class AdminStorageMigrationService:
    """Admin storage-disk migration orchestration."""

    @staticmethod
    def _validate_recurring_schedule(config: dict) -> None:
        """A recurring migration is defined by its occurrences, so it MUST have a
        schedule (selected weekdays and/or a daily time range). Reject a
        recurring job with no window — otherwise "occurrence" is undefined."""
        if not config.get("recurring"):
            return
        window = config.get("window") or {}
        has_time = bool(window.get("start")) and bool(window.get("end"))
        has_days = bool(window.get("days"))
        if not (has_time or has_days):
            raise Error(
                "bad_request",
                "A recurring migration needs a schedule window "
                "(selected weekdays and/or a daily time range)",
            )

    @staticmethod
    def _descriptor_claims_for(selection: dict) -> set:
        """Content-independent reservation descriptor for a selection (whole
        pool / path-in-pool / category assigned-pool-set), resolving the pool for
        a path selection (explicit ``src_pool_id`` or by the prefix's mountpoint)
        and the assigned pools for a category."""
        kind = selection.get("kind", "pool")
        if kind == "category":
            pools = mig.pools_for_category(selection.get("category_id"))
            return mig.descriptor_claims("category", category_pools=pools)
        if kind == "path":
            pool_id = selection.get("src_pool_id")
            if not pool_id:
                pools = StoragePool.get_by_path(selection.get("path_prefix") or "")
                pool_id = pools[0].id if pools else None
            return mig.descriptor_claims(
                "path", src_pool_id=pool_id, path_prefix=selection.get("path_prefix")
            )
        return mig.descriptor_claims("pool", src_pool_id=selection.get("src_pool_id"))

    @classmethod
    def _check_no_overlap(cls, selection: dict, config: dict) -> None:
        """Reject a new selection whose scope overlaps any active (non-terminal)
        job — CROSS-MODE. Composes two reservations (see
        ``mig.scope_conflict``): the resolved disk-id closure (precise; the
        concrete cross-mode signal) and a content-independent descriptor (so a
        recurring job reserves its whole source scope for its entire non-terminal
        life, even between occurrences when it is migrating nothing). One-shot
        jobs reserve their persisted ledger disks; recurring jobs additionally
        reserve their re-resolved scope + descriptor. Prefers over-rejecting."""
        # Nothing active -> no possible overlap; skip resolving the new scope
        # (an empty pool/selection would otherwise pay a needless closure walk).
        active = [m for m in StorageMigration.get_all() if m.status not in _TERMINAL]
        if not active:
            return
        new_ids = mig.resolved_disk_ids(selection)
        new_claims = cls._descriptor_claims_for(selection)
        new_recurring = bool(config.get("recurring"))
        existing = []
        for m in active:
            recurring = bool((m.config or {}).get("recurring"))
            # one-shot reserves its ledger disks (read, never rebuilt); a
            # recurring job additionally reserves its live re-resolved scope.
            reserved = {
                it["storage_id"] for it in StorageMigrationItem.dicts_by_migration(m.id)
            }
            if recurring:
                reserved |= mig.resolved_disk_ids(m.selection or {})
            existing.append(
                {
                    "id": m.id,
                    "recurring": recurring,
                    "reserved_ids": reserved,
                    "claims": cls._descriptor_claims_for(m.selection or {}),
                }
            )
        conflict = mig.scope_conflict(new_ids, new_claims, new_recurring, existing)
        if conflict:
            raise Error(
                "conflict",
                f"Selection overlaps the scope of active migration {conflict}",
            )

    @staticmethod
    def _dst_pool(selection: dict) -> StoragePool:
        dst_id = selection.get("dst_pool_id")
        if not dst_id:
            raise Error("bad_request", "A destination storage pool is required")
        # Reject a same-pool migration up front: every disk would have dst == src,
        # making the move a no-op while the release move_deletes the live source
        # — a one-click total-data-loss path. The reconciler also guards per-disk
        # (mig.item_in_place), but this stops the job ever being created.
        if selection.get("src_pool_id") and selection.get("src_pool_id") == dst_id:
            raise Error(
                "bad_request",
                "Source and destination storage pools must differ",
            )
        if not StoragePool.exists(dst_id):
            raise Error("not_found", f"Destination storage pool {dst_id} not found")
        return StoragePool(dst_id)

    @classmethod
    def plan(cls, selection: dict) -> dict:
        """Dry-run preview — resolve the selection, build the plan, summarise
        per tree. Nothing is persisted. Result is briefly cached per selection
        (see ``_PLAN_CACHE``); an invalid selection raises before caching."""
        key = _plan_cache_key(selection)
        cached = _PLAN_CACHE.get(key)
        if cached is not None:
            return cached
        dst_pool = cls._dst_pool(selection)
        roots = mig.roots_for_selection(selection)
        items, totals = mig.build_plan_for_roots("__preview__", roots, dst_pool)
        result = {"trees": _tree_summaries(items), "totals": totals}
        _PLAN_CACHE[key] = result
        return result

    @staticmethod
    def _assert_move_lanes_served(preview, dst_pool):
        """Refuse a plan whose cross-pool move lane has no live consumer.

        Every move is enqueued on ``storage.<pool-key>.<tier>``, where the key is
        the SAME sorted ``src:dst`` join the runner uses. rq keeps a job queued
        on a lane nobody drains: no worker picks it up, nothing raises and no
        timeout fires, so the migration reports ``running`` indefinitely with a
        disk that never moves. Fail-open on a redis error, matching the shed
        gate's posture -- a broker blip must not block an otherwise valid job.
        """
        try:
            covered, opaque_pools = queue_coverage.served_coverage(Task._redis)
        except Exception:
            return
        unserved = set()
        for item in preview:
            pools = StoragePool.get_by_path(dirname(item.get("src_path") or ""))
            src_pool = pools[0] if pools else dst_pool
            key = get_queue_from_storage_pools(src_pool, dst_pool)
            if key in opaque_pools:
                continue
            # the tier the RUNNER lands on, resolved by the same rules it uses --
            # a guard that checks a different tier protects nothing
            tier = queue_tiers.normalize_tier(DEFAULT_PRIORITY, "move")
            if not covered[(key, tier)]:
                unserved.add(key)
        if unserved:
            raise Error(
                "bad_request",
                "No storage node serves the move queue(s) "
                + ", ".join(sorted(unserved))
                + "; add the destination pool to a node's "
                "CAPABILITIES_STORAGE_POOLS before migrating into it",
            )

    @classmethod
    def create(cls, payload: dict, selection: dict, config: dict) -> dict:
        """Resolve + build + persist a migration job (status ``planned``) and
        its per-disk ledger rows. Idempotent on re-plan (deterministic ids).

        Guards, in order: destination valid + differs (``_dst_pool``); a recurring
        job has a schedule; the scope does not overlap any active job; and — for
        path/category — the plan is not entirely in-place (origin == destination).
        A recurring job may legitimately start with an EMPTY scope (it drains
        disks as they appear at each occurrence); a one-shot may not.
        """
        dst_pool = cls._dst_pool(selection)
        cls._validate_recurring_schedule(config)
        cls._check_no_overlap(selection, config)
        recurring = bool(config.get("recurring"))
        roots = mig.roots_for_selection(selection)
        if not roots and not recurring:
            raise Error("bad_request", "Selection matched no migratable disks")
        # origin != destination for path/category: a plan that resolves entirely
        # in-place (every disk's dst == src) would move nothing while the release
        # move_deletes the live source. (Pool src==dst is rejected in _dst_pool.)
        preview, _ = mig.build_plan_for_roots("__preview__", roots, dst_pool)
        if mig.all_in_place(preview):
            raise Error(
                "bad_request",
                "Selection resolves entirely in-place (source pool equals "
                "destination); nothing would move",
            )
        cls._assert_move_lanes_served(preview, dst_pool)
        now = time()
        migration = StorageMigration.init_document(
            status=MigrationStatus.PLANNED.value,
            selection=selection,
            config=config,
            totals={},
            created_by=payload.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        items, totals = mig.build_plan_for_roots(migration.id, roots, dst_pool)
        for item in items:
            StorageMigrationItem.upsert(item)
        migration.totals = totals
        # Disks matched here will start leaving their source pool, so any cached
        # dry-run estimate is now stale — drop it (writer invalidates the cache).
        _PLAN_CACHE.clear()
        return cls.get(migration.id)

    @staticmethod
    def list() -> list:
        return [_serialize(m) for m in StorageMigration.get_all()]

    @staticmethod
    def get(migration_id: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        return _serialize(StorageMigration(migration_id))

    @classmethod
    def status(cls, migration_id: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        items = StorageMigrationItem.dicts_by_migration(migration_id)
        m.recompute_totals()  # keep the persisted ledger totals fresh (list view)
        # The full admin-view aggregate (totals + per-tree progress + ETA +
        # window + per-disk rows) is built by the shared helper so the status
        # endpoint and the storage:migration socket event render identically.
        payload = mig.aggregate_status(m, items, include_items=True)
        payload["state_counts"] = payload["totals"].get("state_counts", {})
        # Live next-run lookahead (needs now-in-tz) for the admin table.
        payload["next_run_seconds"] = cls._next_run_seconds(m)
        return payload

    @staticmethod
    def _next_run_seconds(m: StorageMigration):
        """Seconds until the schedule window next opens on a selected weekday, in
        the window's timezone. None when there is no schedule."""
        window = (m.config or {}).get("window") or {}
        if not window:
            return None
        tz = window.get("tz") or "UTC"
        try:
            now = datetime.now(ZoneInfo(tz))
        except Exception:
            now = datetime.now(timezone.utc)
        return mig.next_run_for_window(window, now)

    @classmethod
    def set_action(cls, migration_id: str, action: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        if m.status in _TERMINAL:
            raise Error(
                "precondition_required",
                f"Migration {migration_id} is {m.status} and can no longer be {action}ed",
            )
        # Cancel = finish-current-tree: a started job drains its in-flight tree
        # (and restores autostart) via finishing_tree before becoming canceled;
        # the reconciler performs that transition. See mig.cancel_target.
        if action == "cancel":
            m.status = mig.cancel_target(m.status)
        else:
            m.status = _ACTION_TARGET[action]
        m.updated_at = time()
        return cls.get(migration_id)

    @classmethod
    def update_config(cls, migration_id: str, config: dict) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        if m.status in _TERMINAL:
            raise Error(
                "precondition_required",
                f"Migration {migration_id} is {m.status}; config is immutable",
            )
        m.config = config
        m.updated_at = time()
        return cls.get(migration_id)

    @staticmethod
    def pool_plan(pool_id: str) -> dict:
        if not StoragePool.exists(pool_id):
            raise Error("not_found", f"Storage pool {pool_id} not found")
        return mig.pool_plan_summary(pool_id)

    #: audit columns, in the order they appear in the CSV export
    _AUDIT_COLUMNS = [
        "occurrence",
        "occurrence_time",
        "storage_id",
        "kind",
        "tree_id",
        "src_path",
        "dst_path",
        "result",
        "size_bytes",
        "error",
        "started_at",
        "finished_at",
    ]

    @classmethod
    def log(cls, migration_id: str) -> dict:
        """Build the downloadable migration report: every per-disk AUDIT record
        (flattened from the ledger, annotated by occurrence for a recurring job)
        plus a summary header (counts by result, bytes moved, duration, number of
        occurrences). Reflects the ledger, which the reconciler drives from
        on-disk/DB reality."""
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        items = StorageMigrationItem.dicts_by_migration(migration_id)
        records = []
        for it in items:
            records.extend(it.get("audit") or [])
        records.sort(
            key=lambda r: (r.get("occurrence_time") or 0, r.get("storage_id") or "")
        )
        return {
            "id": migration_id,
            "status": m.status,
            "summary": mig.summarize_audit(records),
            "records": records,
        }

    @classmethod
    def log_csv(cls, migration_id: str) -> str:
        """Admin-friendly CSV of the migration report: a commented summary header
        followed by one row per audit record."""
        import csv
        import io

        payload = cls.log(migration_id)
        s = payload["summary"]
        buf = io.StringIO()
        buf.write(f"# migration,{migration_id}\n")
        buf.write(f"# status,{payload['status']}\n")
        buf.write(f"# records,{s['records']}\n")
        buf.write(f"# bytes_moved,{s['bytes_moved']}\n")
        buf.write(f"# duration_seconds,{s['duration_seconds']}\n")
        buf.write(f"# occurrences,{s['occurrences']}\n")
        for result, count in sorted(s["counts"].items()):
            buf.write(f"# result:{result},{count}\n")
        writer = csv.DictWriter(
            buf, fieldnames=cls._AUDIT_COLUMNS, extrasaction="ignore"
        )
        writer.writeheader()
        for rec in payload["records"]:
            writer.writerow(rec)
        return buf.getvalue()

    @staticmethod
    def path_prefixes(src_pool_id: str = None) -> dict:
        """Distinct real source path-prefixes (``storage.directory_path``) for the
        ``path`` selection kind, optionally scoped to a source pool (matched by
        the prefix's mountpoint pool). Drives the UI dropdown — no free text."""
        rows = mig._enumerate_storages()
        dirs = sorted(
            {r.get("directory_path") for r in rows if r.get("directory_path")}
        )
        if src_pool_id:
            cache: dict = {}
            kept = []
            for d in dirs:
                if d not in cache:
                    pools = StoragePool.get_by_path(d)
                    cache[d] = pools[0].id if pools else None
                if cache[d] == src_pool_id:
                    kept.append(d)
            dirs = kept
        return {"prefixes": dirs}
