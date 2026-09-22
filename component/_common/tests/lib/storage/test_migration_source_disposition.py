# SPDX-License-Identifier: AGPL-3.0-or-later

"""What the release does with a migrated disk's source: mock-only, no DB, no redis."""

import pytest
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import MigrationConfig

SRC = "/pool-src/disk.qcow2"
DST = "/pool-dst/disk.qcow2"


def _runner(config, *, system_action="delete"):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = dict(config)
    r.user_id = "admin"
    r.lane_is_drainable = lambda conn, queue: True
    caps = {"enqueued": []}

    def _enqueue(task, queue, kwargs, timeout=None):
        caps["enqueued"].append((task, queue, kwargs))
        return "tid"

    def _set(item, **fields):
        item.update(fields)

    r._enqueue = _enqueue
    r._set = _set
    r._pool_queue = lambda path, action: f"storage.p-src.{action}"
    r._claim_storage_task = lambda item, task_id: None
    r._system_delete_action = lambda: system_action
    return r, caps


def _item():
    return {
        "id": "i1",
        "state": "db_updated",
        "storage_id": "s1",
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": SRC,
        "dst_path": DST,
        "size_bytes": 1024,
        "move_delete_task_id": None,
        "storage_orig_status": None,
    }


def test_the_default_follows_the_system_delete_action():
    assert MigrationConfig().source_disposition == "system"


@pytest.mark.parametrize(
    "disposition,system_action,expected",
    [
        ("system", "delete", "delete"),
        ("system", "move", "move_delete"),
        ("recycle_bin", "delete", "move_delete"),
        ("delete", "move", "delete"),
        # a job created before the knob existed keeps parking, whatever the
        # global says: upgrading must not start hard-deleting a running campaign
        (None, "delete", "move_delete"),
    ],
)
def test_release_enqueues_the_resolved_source_action(
    disposition, system_action, expected
):
    config = {"verify": True}
    if disposition is not None:
        config["source_disposition"] = disposition
    r, caps = _runner(config, system_action=system_action)
    item = _item()

    r._release(item)

    assert [(t, q) for t, q, _k in caps["enqueued"]] == [
        (expected, f"storage.p-src.{expected}")
    ]
    assert caps["enqueued"][0][2] == {"path": SRC}
    assert item["state"] == "released"
    assert item["move_delete_task_id"] == "tid"
    assert item["source_action"] == expected
    assert item.get("source_action_reason") is None
    assert (item["audit"] or [])[-1]["source_action"] == expected


@pytest.mark.parametrize("disposition", ["system", "delete"])
def test_a_hard_delete_without_verify_parks_the_source_instead(disposition):
    """Verify off never unlinks a source, whatever the job or the system says."""
    r, caps = _runner(
        {"verify": False, "source_disposition": disposition}, system_action="delete"
    )
    item = _item()

    r._release(item)

    assert [t for t, _q, _k in caps["enqueued"]] == ["move_delete"]
    assert item["source_action"] == "move_delete"
    assert item["source_action_reason"] == "verify_off"
    assert (item["audit"] or [])[-1]["source_action_reason"] == "verify_off"


def test_an_unreadable_system_action_parks_the_source():
    def _boom():
        raise RuntimeError("db down")

    r, caps = _runner({"verify": True, "source_disposition": "system"})
    r._system_delete_action = _boom
    item = _item()

    r._release(item)

    assert [t for t, _q, _k in caps["enqueued"]] == ["move_delete"]
    assert item["source_action_reason"] == "system_action_unreadable"


def test_the_delete_lane_is_governed_like_move_delete():
    """A hard delete trails on the same governed tier the park does."""
    from isardvdi_common.lib import queue_tiers

    assert queue_tiers.normalize_tier(mr.DEFAULT_PRIORITY, "delete") == (
        queue_tiers.normalize_tier(mr.DEFAULT_PRIORITY, "move_delete")
    )


def test_the_audit_record_carries_the_source_action():
    item = _item()
    item.update({"source_action": "delete", "source_action_reason": None})
    record = mig.build_audit_record(item, "moved_ok", "initial", 1.0)
    assert record["source_action"] == "delete"
    assert record["source_action_reason"] is None
