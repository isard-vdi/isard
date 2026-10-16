# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest


@pytest.fixture(autouse=True)
def system_delete_action_is_move(monkeypatch):
    """The release reads the recycle bin's global delete action from the DB;
    pin it to the park so a suite with no DB behind it never depends on what a
    mock answers. A test about the resolution sets its own on the instance."""
    from isardvdi_common.lib.storage import migration_run as mr

    monkeypatch.setattr(
        mr.MigrationRunner, "_system_delete_action", staticmethod(lambda: "move")
    )


@pytest.fixture(autouse=True)
def ledger_reads_use_the_stubbed_rows(monkeypatch):
    """The suites stub ``dicts_by_migration``; serve the runner's projected read
    and its audit append from those same in-memory rows."""
    from isardvdi_common.models.storage_migration import StorageMigrationItem

    monkeypatch.setattr(
        StorageMigrationItem,
        "ledger_rows",
        classmethod(lambda cls, mid: cls.dicts_by_migration(mid)),
        raising=False,
    )
    monkeypatch.setattr(
        StorageMigrationItem,
        "append_audit",
        classmethod(lambda cls, item_id, record: None),
        raising=False,
    )
