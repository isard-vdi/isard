# SPDX-License-Identifier: AGPL-3.0-or-later

"""The running-size sweep's idempotency must read the task index, not the scalar.

The ``task`` scalar is retired: nothing on the create path writes it, so the
sweep's "already in flight?" skip that consulted ``storage.task`` saw ``None``
for every row and could dogpile a disk already being refreshed. This pins the
skip against the per-owner index, so a scalar read fails here instead of going
quiet in production.
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


def test_refresh_idempotency_reads_the_index_not_the_scalar(mod, monkeypatch):
    """A ready disk whose live task is only in the index (scalar is ``None``)
    must be skipped. Fails while the sweep reads ``storage.task``."""
    disk = MagicMock(name="storage", status="ready", readonly=False, task=None)
    monkeypatch.setattr(
        mod, "Storage", MagicMock(return_value=disk, exists=lambda sid: True)
    )
    (
        mod.r.table.return_value.get_all.return_value.pluck.return_value.run.return_value
    ) = [
        {
            "id": "d-1",
            "user": "u",
            "create_dict": {"hardware": {"disks": [{"storage_id": "s-1"}]}},
        }
    ]
    # live, pending task in the INDEX; the scalar stays None
    monkeypatch.setattr(
        mod, "current_task_id", lambda _c, sid, **k: "t-live", raising=False
    )
    monkeypatch.setattr(mod, "Task", MagicMock(return_value=MagicMock(pending=True)))

    enqueued = mod.StorageProcessed.enqueue_running_desktops_size_refresh()

    assert enqueued == 0, "a disk with a live indexed task was swept anyway"
    disk.check_backing_chain.assert_not_called()
