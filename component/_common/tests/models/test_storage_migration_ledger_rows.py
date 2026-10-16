# SPDX-License-Identifier: AGPL-3.0-or-later

"""The migration runner reads its ledger without the growing audit and checkpoints."""

from unittest.mock import MagicMock

from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models import storage_migration as sm


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_the_runner_read_leaves_audit_and_checkpoints_out(monkeypatch):
    item_cls = sm.StorageMigrationItem
    monkeypatch.setattr(item_cls, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(item_cls),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    table = MagicMock(name="r.table")
    monkeypatch.setattr(sm.r, "table", table)

    runner = object.__new__(mr.MigrationRunner)
    runner.migration_id = "m"
    runner._items()

    projections = [
        (name.rsplit(".", 1)[-1], set(args))
        for name, args, _ in table.mock_calls
        if name.rsplit(".", 1)[-1] in ("pluck", "without")
    ]
    assert projections, "the ledger read carries every field"
    for method, fields in projections:
        if method == "without":
            assert {"audit", "checkpoints"} <= fields
        else:
            assert not fields & {"audit", "checkpoints"}
