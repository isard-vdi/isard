# SPDX-License-Identifier: AGPL-3.0-or-later

"""The migration ledger's status compare-and-set and fresh read, on a real RethinkDB."""

from __future__ import annotations

import os
import uuid

import pytest

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

pytestmark = pytest.mark.real


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    db = os.environ.get("RETHINKDB_DB", "isard")
    try:
        return r.connect(host=host, port=port, db=db)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


@pytest.fixture
def conn():
    c = _connect()
    yield c
    c.close()


@pytest.fixture
def job(conn):
    """A throwaway ledger row (and its items), removed afterwards."""
    mid = f"e2e-cas-{uuid.uuid4()}"
    r.table("storage_migration").insert(
        {"id": mid, "status": "running", "pause_reason": None}
    ).run(conn)
    yield mid
    r.table("storage_migration_item").filter({"migration_id": mid}).delete().run(conn)
    r.table("storage_migration").get(mid).delete().run(conn)


def _status(conn, mid):
    return r.table("storage_migration").get(mid)["status"].run(conn)


def _runner(job):
    from isardvdi_common.lib.storage.migration_run import MigrationRunner
    from isardvdi_common.models.storage_migration import StorageMigration

    runner = object.__new__(MigrationRunner)
    runner.migration_id = job
    runner.migration = StorageMigration(job)
    return runner


def test_a_claim_applies_when_the_status_is_the_one_read(conn, job):
    runner = _runner(job)
    assert runner._claim_status("running", "scheduled") is True
    row = r.table("storage_migration").get(job).run(conn)
    assert row["status"] == "scheduled"
    assert row.get("status_time")


def test_an_admin_cancel_written_meanwhile_is_not_overwritten(conn, job):
    runner = _runner(job)
    assert str(runner.migration.status) == "running"  # the tick reads (and caches) it
    # the admin cancels from another process while the tick runs
    r.table("storage_migration").get(job).update({"status": "canceled"}).run(conn)
    assert runner._claim_status("running", "scheduled") is False
    assert _status(conn, job) == "canceled"
    # the lost claim refreshed the cache to the admin's status
    assert str(runner.migration.status) == "canceled"


def test_fresh_status_bypasses_the_attribute_cache(conn, job):
    from isardvdi_common.models.storage_migration import StorageMigration

    m = StorageMigration(job)
    assert str(m.status) == "running"
    r.table("storage_migration").get(job).update(
        {"status": "paused", "pause_reason": "manual"}
    ).run(conn)
    assert m.fresh_status() == ("paused", "manual")


def test_set_action_write_shape_applies_and_blocks(conn, job):
    """apiv4 set_action writes status + pause_reason + timestamps in one
    update_document_if, CAS-guarded on the status it read. It must apply when the
    row still reads that status and block (row intact) when it changed meanwhile.
    This gates the real CAS the apiv4 route suite can only emulate."""
    from isardvdi_common.models.storage_migration import StorageMigration

    now = 1234.0
    applied = StorageMigration.update_document_if(
        job,
        {
            "status": "finishing_tree",
            "pause_reason": None,
            "status_time": now,
            "updated_at": now,
            "last_activity_at": now,
        },
        field="status",
        values=("running",),
        validate=False,
    )
    assert applied is True
    row = r.table("storage_migration").get(job).run(conn)
    assert row["status"] == "finishing_tree" and row.get("status_time")
    # the admin's read is now stale: another writer moved it on first
    r.table("storage_migration").get(job).update({"status": "canceled"}).run(conn)
    blocked = StorageMigration.update_document_if(
        job,
        {"status": "paused", "pause_reason": "manual"},
        field="status",
        values=("finishing_tree",),
        validate=False,
    )
    assert blocked is False
    assert _status(conn, job) == "canceled"


def test_pause_cas_wins_over_a_load_resume_racing_in(conn, job):
    """apiv4 set_action's pause keys the CAS on status in
    {running, window_closed, paused}, so a load resume that flips the row
    paused->running between the admin's read and the write does NOT block the
    pause: it still lands as paused/manual (the original bug's core)."""
    from isardvdi_common.models.storage_migration import StorageMigration

    r.table("storage_migration").get(job).update(
        {"status": "paused", "pause_reason": "load"}
    ).run(conn)
    # admin read paused/load; before the write the reconciler resumes (load cleared)
    r.table("storage_migration").get(job).update(
        {"status": "running", "pause_reason": None}
    ).run(conn)
    applied = StorageMigration.update_document_if(
        job,
        {"status": "paused", "pause_reason": "manual", "status_time": 1.0},
        field="status",
        values=("running", "window_closed", "paused"),
        validate=False,
    )
    assert applied is True
    row = r.table("storage_migration").get(job).run(conn)
    assert row["status"] == "paused" and row["pause_reason"] == "manual"


@pytest.mark.parametrize(
    "states, moving",
    [
        (["pending", "released", "skipped"], False),
        (["pending", "moving"], True),
        (["db_updated"], True),
    ],
)
def test_a_paused_job_is_drivable_only_while_disks_are_moving(
    conn, job, states, moving
):
    from isardvdi_common.lib.storage.migration_run import _has_in_flight

    r.table("storage_migration_item").insert(
        [
            {
                "id": f"{job}--{i}",
                "migration_id": job,
                "state": s,
                "storage_id": f"s{i}",
            }
            for i, s in enumerate(states)
        ]
    ).run(conn)
    assert _has_in_flight(job) is moving
