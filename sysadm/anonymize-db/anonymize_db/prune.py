"""Optional row-level trimming of the dump.

Two independent, opt-in policies, applied per-document during the streaming
scrub pass (a dropped row is never scrubbed or written, so it also saves work):

* prune-deleted: drop rows in a *deleted* state that became deleted more than N
  days ago — `recycle_bin`, `storage`, `media`.
* cap-history: drop time-series rows older than N days — `logs_desktops`,
  `logs_users`, `usage_consumption`.

Timestamps in a rethinkdb-dump are either bare unix numbers or reql TIME
wrappers (`{"$reql_type$": "TIME", "epoch_time": ...}`); both are handled.
"""

from __future__ import annotations

import time
from typing import Any

_DAY = 86400

# storage.status values that mean the qcow2 is gone
_STORAGE_DELETED = {"deleted", "recycled", "non_existing"}


def _epoch(v: Any) -> float | None:
    """Best-effort unix epoch from a reql TIME wrapper or a bare number."""
    if isinstance(v, dict) and v.get("$reql_type$") == "TIME":
        e = v.get("epoch_time")
        return e if isinstance(e, (int, float)) else None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return None


def _first_epoch(doc: dict, *fields: str) -> float | None:
    for f in fields:
        e = _epoch(doc.get(f))
        if e is not None:
            return e
    return None


def _storage_deleted_epoch(doc: dict) -> float | None:
    """When the storage became deleted: the time of the last status_logs entry."""
    sl = doc.get("status_logs")
    if isinstance(sl, list):
        times = [
            e["time"]
            for e in sl
            if isinstance(e, dict) and isinstance(e.get("time"), (int, float))
        ]
        if times:
            return max(times)
    return None


class Pruner:
    """Decides whether to drop a document before it is scrubbed/written."""

    # tables this pruner can affect (for help / dry reporting)
    DELETED_TABLES = ("recycle_bin", "storage", "media")
    HISTORY_TABLES = ("logs_desktops", "logs_users", "usage_consumption")

    def __init__(
        self,
        prune_deleted_days: int = 0,
        cap_history_days: int = 0,
        now: float | None = None,
    ):
        now = time.time() if now is None else now
        self.del_cutoff = (
            now - prune_deleted_days * _DAY if prune_deleted_days else None
        )
        self.hist_cutoff = now - cap_history_days * _DAY if cap_history_days else None
        self.counts: dict[str, int] = {}

    @property
    def active(self) -> bool:
        return self.del_cutoff is not None or self.hist_cutoff is not None

    def affects(self, table: str) -> bool:
        return (self.del_cutoff is not None and table in self.DELETED_TABLES) or (
            self.hist_cutoff is not None and table in self.HISTORY_TABLES
        )

    def should_drop(self, table: str, doc: Any) -> bool:
        if not isinstance(doc, dict):
            return False
        d = self.del_cutoff
        if d is not None:
            if table == "recycle_bin":
                e = _epoch(doc.get("accessed"))
                if e is not None and e < d:
                    return self._drop(table)
            elif table == "storage" and doc.get("status") in _STORAGE_DELETED:
                e = _storage_deleted_epoch(doc)
                if e is not None and e < d:
                    return self._drop(table)
            elif table == "media" and str(doc.get("status")).lower() == "deleted":
                e = _first_epoch(doc, "status_time", "accessed")
                if e is not None and e < d:
                    return self._drop(table)
        h = self.hist_cutoff
        if h is not None:
            if table in ("logs_desktops", "logs_users"):
                e = _first_epoch(doc, "started_time", "starting_time", "stopped_time")
                if e is not None and e < h:
                    return self._drop(table)
            elif table == "usage_consumption":
                e = _epoch(doc.get("date"))
                if e is not None and e < h:
                    return self._drop(table)
        return False

    def _drop(self, table: str) -> bool:
        self.counts[table] = self.counts.get(table, 0) + 1
        return True
