# SPDX-License-Identifier: AGPL-3.0-or-later

"""The last reconcile report is stored per pool and read back aggregated by category."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.storage.storage_pools import storage_pools as mod

    pools_cls = mod.StoragePoolsProcessed

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(pools_cls, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(pools_cls), "_rdb_connection", property(lambda self: MagicMock())
    )
    tables: dict = {}
    monkeypatch.setattr(
        mod.r, "table", lambda name: tables.setdefault(name, MagicMock())
    )
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", list(x)))
    return mod, pools_cls, tables


def test_store_writes_the_pool_entry(stub):
    _mod, pools_cls, tables = stub
    pools_cls.store_reconcile_report(
        "pool-1", {"size_drift_files": 2}, [{"id": "a", "drift": 5}]
    )
    tables["config"].update.assert_called_once()
    written = tables["config"].update.call_args.args[0]
    entry = written[pools_cls.RECONCILE_REPORT_KEY]["pool-1"]
    assert entry["metrics"] == {"size_drift_files": 2}
    assert entry["size_drift"] == [{"id": "a", "drift": 5}]
    assert "updated_at" in entry


def test_report_aggregates_absolute_drift_bytes_per_category(stub):
    mod, pools_cls, _tables = stub
    pools = {
        "pool-1": {
            "metrics": {"size_drift_bytes": 150},
            "size_drift": [{"id": "a", "drift": 100}, {"id": "b", "drift": -50}],
        }
    }
    mod.r.table(
        "config"
    ).nth.return_value.__getitem__.return_value.default.return_value.run.return_value = (
        pools
    )
    mod.r.table("storage").get_all.return_value.pluck.return_value.run.return_value = [
        {"id": "a", "user_id": "u1"},
        {"id": "b", "user_id": "u2"},
    ]
    mod.r.table("users").get_all.return_value.pluck.return_value.run.return_value = [
        {"id": "u1", "category": "cat-a"},
        {"id": "u2", "category": "cat-a"},
    ]
    out = pools_cls.reconcile_report()
    assert out["pools"] == pools
    # |100| + |-50|, both owners in cat-a
    assert out["bytes_per_category"] == {"cat-a": 150}


def test_report_is_empty_without_stored_runs(stub):
    mod, pools_cls, _tables = stub
    mod.r.table(
        "config"
    ).nth.return_value.__getitem__.return_value.default.return_value.run.return_value = (
        {}
    )
    out = pools_cls.reconcile_report()
    assert out == {"pools": {}, "bytes_per_category": {}}
