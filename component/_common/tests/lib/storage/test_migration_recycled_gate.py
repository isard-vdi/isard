# SPDX-License-Identifier: AGPL-3.0-or-later

"""A tree whose disk left ``ready`` after the plan is skipped before it starts."""

import pytest
from isardvdi_common.lib.storage import migration_run as mr


def _item(sid, kind="desktop"):
    return {
        "id": f"m--{sid}",
        "storage_id": sid,
        "tree_id": "r",
        "state": "pending",
        "kind": kind,
        "audit": [],
    }


def _runner(monkeypatch, statuses, domains=None):
    class _Storage:
        def __init__(self, sid):
            self.status = statuses[sid]

        @staticmethod
        def exists(sid):
            return sid in statuses

    monkeypatch.setattr(mr, "Storage", _Storage)
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = type("M", (), {"last_occurrence": None})()
    r.config = {}
    r._touch = lambda: None
    r._domains = lambda sid: (domains or {}).get(sid, [])
    monkeypatch.setattr(
        mr.StorageMigrationItem, "update_document", classmethod(lambda *a, **k: None)
    )
    return r


@pytest.mark.parametrize(
    "status, reason",
    [
        ("recycled", "disk c is in the recycle bin"),
        ("deleted", "disk c is deleted, not ready"),
        ("maintenance", "disk c is maintenance, not ready"),
    ],
)
def test_a_tree_with_a_disk_that_left_ready_is_skipped_untouched(
    monkeypatch, status, reason
):
    items = [_item("r"), _item("c")]
    r = _runner(monkeypatch, {"r": "ready", "c": status})
    assert r._gate_tree(items) is False
    assert [it["state"] for it in items] == ["skipped", "skipped"]
    assert all(it["error"] == reason for it in items)
    assert all(it["audit"][-1]["result"] == "skipped" for it in items)


def test_a_tree_whose_disk_row_is_gone_is_skipped(monkeypatch):
    items = [_item("r")]
    r = _runner(monkeypatch, {})
    assert r._gate_tree(items) is False
    assert items[0]["error"] == "disk r is gone, not ready"


def test_a_ready_tree_passes_the_gate(monkeypatch):
    items = [_item("r"), _item("m", kind="media")]
    r = _runner(monkeypatch, {"r": "ready"})
    assert r._gate_tree(items) is True
    assert items[0]["state"] == "pending"


def test_a_started_tree_is_not_gated_again(monkeypatch):
    items = [_item("r"), _item("c")]
    items[0]["state"] = "released"
    r = _runner(monkeypatch, {"r": "ready", "c": "recycled"})
    assert r._gate_tree(items) is True
    assert items[1]["state"] == "pending"
