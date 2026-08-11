#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The running-desktop size sweep must read the disks where they actually live.

A domain keeps its attached disks under ``create_dict.hardware.disks`` -- that is
what ``Domain.storages`` reads, and what the engine's own on-stop refresh walks.
There is no top-level ``hardware`` on a running desktop, so a sweep that plucks
one finds no disks, enqueues nothing, and reports success while doing nothing at
all. Verified against a live stack: a desktop genuinely running under libvirt
still produced ``{"enqueued": 0}``.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub(monkeypatch):
    from isardvdi_common.lib.storage import storage as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.StorageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.StorageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod.r, "table", MagicMock(name="r.table"))
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    disk = MagicMock(name="storage")
    disk.status = "ready"
    disk.readonly = False
    disk.task = None
    monkeypatch.setattr(mod.Storage, "exists", staticmethod(lambda sid: True))
    monkeypatch.setattr(
        mod, "Storage", MagicMock(return_value=disk, exists=lambda sid: True)
    )
    monkeypatch.setattr(mod, "Task", MagicMock(exists=lambda tid: False))
    return mod, disk


def _returns(mod, rows):
    (
        mod.r.table.return_value.get_all.return_value.pluck.return_value.run.return_value
    ) = rows


def test_sweep_finds_disks_under_create_dict(stub):
    """The real shape. Fails while the sweep plucks a top-level ``hardware``."""
    mod, disk = stub
    _returns(
        mod,
        [
            {
                "id": "desk-1",
                "user": "local-default-admin-admin",
                "create_dict": {"hardware": {"disks": [{"storage_id": "s-1"}]}},
            }
        ],
    )

    enqueued = mod.StorageProcessed.enqueue_running_desktops_size_refresh()

    assert enqueued == 1, "a running desktop's disk was not swept"
    disk.check_backing_chain.assert_called_once()


def test_sweep_skips_a_desktop_with_no_disks(stub):
    mod, disk = stub
    _returns(mod, [{"id": "desk-1", "user": "u", "create_dict": {"hardware": {}}}])

    assert mod.StorageProcessed.enqueue_running_desktops_size_refresh() == 0
    disk.check_backing_chain.assert_not_called()
