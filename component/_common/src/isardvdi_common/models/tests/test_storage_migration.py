# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for isardvdi_common.models.storage_migration.

These cover the *pure* layer of the migration ledger: the Pydantic models
(field defaults + JSON serialisation) and the module-level state-machine
helpers. They never touch RethinkDB — the DB-bound classmethods are exercised
live against the running stack (P1.1 gate: tables survive an engine restart).
"""

import json
from contextlib import nullcontext

import pytest
from isardvdi_common.models import storage_migration as sm
from isardvdi_common.models.storage_migration import (
    DONE_ITEM_STATES,
    MIGRATION_ITEM_STATE_ORDER,
    MigrationItemKind,
    MigrationItemState,
    MigrationStatus,
    StorageMigration,
    StorageMigrationItem,
    StorageMigrationItemModel,
    StorageMigrationModel,
    build_totals,
    compute_bytes_done,
    compute_state_counts,
    item_is_done,
)


# --------------------------------------------------------------------------- #
# Table wiring
# --------------------------------------------------------------------------- #
def test_table_names():
    assert StorageMigration._rdb_table == "storage_migration"
    assert StorageMigrationItem._rdb_table == "storage_migration_item"


# --------------------------------------------------------------------------- #
# StorageMigrationModel defaults + serialisation
# --------------------------------------------------------------------------- #
def test_migration_model_defaults():
    m = StorageMigrationModel()
    assert m.status == MigrationStatus.DRAFT
    # nested defaults are present and empty
    assert m.totals.trees == 0
    assert m.totals.bytes_total == 0
    assert m.totals.state_counts == {}
    assert m.config.bwlimit_kbs == 0
    assert m.config.parallelism == 1
    assert m.config.verify is True
    assert m.config.force_stop_desktops is False
    assert m.selection.kind == "pool"
    assert m.selection.tree_ids == []
    assert m.throughput_ewma == {}
    assert m.logs == []
    # auto id is a uuid string
    assert isinstance(m.id, str) and len(m.id) == 36


def test_migration_model_distinct_nested_defaults():
    """default_factory (not a shared mutable) — two instances must not alias."""
    a = StorageMigrationModel()
    b = StorageMigrationModel()
    a.selection.tree_ids.append("x")
    assert b.selection.tree_ids == []
    assert a.id != b.id


def test_migration_model_json_serialises_enum_to_str():
    m = StorageMigrationModel(status=MigrationStatus.RUNNING)
    dumped = m.model_dump(mode="json")
    assert dumped["status"] == "running"
    assert isinstance(dumped["status"], str)
    # round-trips through JSON cleanly (rethink stores plain JSON)
    parsed = json.loads(m.model_dump_json())
    assert parsed["status"] == "running"
    assert parsed["config"]["parallelism"] == 1


# --------------------------------------------------------------------------- #
# StorageMigrationItemModel defaults + serialisation
# --------------------------------------------------------------------------- #
def test_item_model_defaults():
    it = StorageMigrationItemModel(
        migration_id="mig1", storage_id="s1", tree_id="root1"
    )
    assert it.state == MigrationItemState.PENDING
    assert it.attempts == 0
    assert it.size_bytes == 0
    assert it.bytes_done == 0
    assert it.checkpoints == []
    assert it.move_task_id is None
    assert it.rebase_task_id is None
    assert it.kind == MigrationItemKind.DESKTOP
    assert isinstance(it.id, str) and len(it.id) == 36


def test_item_model_requires_keys():
    with pytest.raises(Exception):
        StorageMigrationItemModel()  # missing migration_id/storage_id/tree_id


def test_item_model_json_serialises_enums():
    it = StorageMigrationItemModel(
        migration_id="m",
        storage_id="s",
        tree_id="t",
        kind=MigrationItemKind.TEMPLATE,
        state=MigrationItemState.MOVING,
    )
    dumped = it.model_dump(mode="json")
    assert dumped["kind"] == "template"
    assert dumped["state"] == "moving"
    assert isinstance(dumped["kind"], str)


# --------------------------------------------------------------------------- #
# State-machine helpers
# --------------------------------------------------------------------------- #
def test_state_order_is_canonical():
    assert MIGRATION_ITEM_STATE_ORDER == [
        MigrationItemState.PENDING,
        MigrationItemState.PREFLIGHT_OK,
        MigrationItemState.MOVING,
        MigrationItemState.MOVED,
        MigrationItemState.REBASED,
        MigrationItemState.DB_UPDATED,
        MigrationItemState.RELEASED,
    ]


def test_done_states():
    assert DONE_ITEM_STATES == {
        MigrationItemState.RELEASED,
        MigrationItemState.SKIPPED,
    }
    assert item_is_done(MigrationItemState.RELEASED) is True
    assert item_is_done("skipped") is True
    assert item_is_done(MigrationItemState.MOVING) is False
    assert item_is_done("failed") is False  # failed is NOT done (needs attention)


def test_compute_state_counts_accepts_dicts_and_objects():
    items = [
        {"state": "pending"},
        {"state": "moving"},
        {"state": "moving"},
        {"state": "released"},
    ]
    counts = compute_state_counts(items)
    assert counts == {"pending": 1, "moving": 2, "released": 1}


def test_compute_state_counts_enum_values_normalised_to_str():
    items = [
        {"state": MigrationItemState.RELEASED},
        {"state": MigrationItemState.RELEASED},
    ]
    assert compute_state_counts(items) == {"released": 2}


def test_compute_bytes_done_sums_only_done_items():
    items = [
        {"state": "released", "size_bytes": 100},
        {"state": "skipped", "size_bytes": 50},  # skipped not counted as moved bytes
        {"state": "moving", "size_bytes": 999},
        {"state": "released", "size_bytes": 25},
    ]
    # only RELEASED bytes count as physically-moved-and-committed
    assert compute_bytes_done(items) == 125


# --------------------------------------------------------------------------- #
# build_totals — ledger-1: totals.done is populated; static fields preserved
# --------------------------------------------------------------------------- #
def test_build_totals_includes_done_and_preserves_static():
    items = [
        {"state": "released", "size_bytes": 10},
        {"state": "skipped", "size_bytes": 5},
        {"state": "moving", "size_bytes": 7},
    ]
    t = build_totals({"trees": 2, "desktops": 3, "bytes_total": 22}, items)
    # static plan fields carried through untouched
    assert t["trees"] == 2 and t["desktops"] == 3 and t["bytes_total"] == 22
    # recomputed dynamic fields
    assert t["items_total"] == 3
    assert t["done"] == 2  # released + skipped (ledger-1: used to be missing -> 0)
    assert t["bytes_done"] == 10  # only released
    assert t["state_counts"] == {"released": 1, "skipped": 1, "moving": 1}


# --------------------------------------------------------------------------- #
# recompute_totals — ledger-0: persisted with r.literal so emptied state_counts
# keys are REPLACED, not deep-merged (no stale phantom pending/moving counts).
# --------------------------------------------------------------------------- #
def test_recompute_totals_persists_with_literal(monkeypatch):
    captured = {}

    class _Q:
        def get(self, _id):
            return self

        def update(self, doc):
            captured["doc"] = doc
            return self

        def run(self, _conn):
            return None

    monkeypatch.setattr(sm.r, "table", lambda name: _Q())
    monkeypatch.setattr(StorageMigration, "_rdb_context", lambda self: nullcontext())
    monkeypatch.setattr(
        StorageMigration,
        "item_dicts",
        lambda self: [{"state": "released", "size_bytes": 10}],
    )

    m = object.__new__(StorageMigration)
    m.__dict__["id"] = "m1"
    m.__dict__["totals"] = {"trees": 1}
    m.__dict__["_rdb_connection"] = None  # instance-level: no DB needed

    totals = m.recompute_totals()
    assert totals["done"] == 1
    # the persisted totals must be wrapped in r.literal (whole-field replacement)
    assert type(captured["doc"]["totals"]).__name__ == "Literal"
