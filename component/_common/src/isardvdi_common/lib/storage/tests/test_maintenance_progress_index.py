# SPDX-License-Identifier: AGPL-3.0-or-later

"""Maintenance-disk progress must come from the task index, not the scalar.

The ``task`` scalar is retired: nothing on the create path writes it, so a
reader that still consults ``storage['task']`` sees ``None`` and shows no
progress for a disk whose task lives in the per-owner index. This pins the
maintenance-progress lookup against the index, so a scalar read fails here
instead of going quiet in production.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mod(monkeypatch):
    from isardvdi_common.lib.storage import storage as m

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        m.StorageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(m.StorageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(m.r, "table", MagicMock(name="r.table"))
    monkeypatch.setattr(m.r, "args", lambda x: x)
    return m


def test_maintenance_progress_reads_the_index_not_the_scalar(mod, monkeypatch):
    """Progress for a maintenance disk is its indexed task's progress, not the
    retired scalar's. Fails while the read is ``storage['task']``."""
    query = MagicMock(name="query")
    for method in ("get_all", "pluck", "merge", "without", "filter", "eq_join"):
        getattr(query, method).return_value = query
    query.run.return_value = [{"id": "s-maint", "status": "maintenance"}]
    mod.r.table.return_value = query
    monkeypatch.setattr(
        mod, "current_task_id", lambda _c, sid, **k: "t-prog", raising=False
    )
    monkeypatch.setattr(
        mod, "Task", MagicMock(return_value=MagicMock(to_dict=lambda: {"progress": 42}))
    )

    rows = mod.StorageProcessed.get_storages(status="maintenance")

    assert (
        rows[0].get("progress") == 42
    ), "maintenance progress not resolved via the index"
