# SPDX-License-Identifier: AGPL-3.0-or-later

"""Three settle-path writes that decide from a row they read a moment earlier.

Each reads a row, decides from what it read, and then writes — so anything that
changed the row in between is overwritten. The decision has to travel with the
write instead, which is what the recycle bin's ``update_task_status`` already
does with a server-side guard.

The fakes here keep the two apart on purpose: the object a handler holds is the
row AS IT WAS READ, and ``store`` is the row AS IT IS when the write lands. A
handler that decides locally cannot tell them apart; one that guards its write
consults the store and can.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _task():
    return SimpleNamespace(id="t1", task="whatever", depending_status="finished")


# --- domain.handle_domain_change_storage — replay must not wire a failed disk


def test_domain_change_storage_writes_nothing_when_replayed_after_it_failed():
    """The redelivery the reclaim path makes routine must stay a no-op.

    The first delivery finds the storage not ready and fails both rows. The
    second finds the domain in ``Failed``, which is not one of the create
    statuses the guard tests, so the guard does not fire and the handler goes
    on to wire a Failed storage's id and path into the domain.
    """
    from isardvdi_change_handler.task_results import domain

    fake_domain = MagicMock()
    fake_domain.status = "Creating"
    fake_domain.create_dict = {"hardware": {"disks": [{}]}}
    fake_storage = MagicMock()
    fake_storage.status = "broken_chain"
    fake_storage.path = "/isard/groups/s1.qcow2"

    with (
        patch.object(domain, "Domain") as domain_cls,
        patch.object(domain, "Storage") as storage_cls,
    ):
        domain_cls.build.return_value = fake_domain
        storage_cls.build.return_value = fake_storage

        domain.handle_domain_change_storage(_task(), domain_id="d1", storage_id="s1")
        assert fake_domain.status == "Failed", "the first delivery must fail the rows"
        assert fake_storage.status == "Failed"

        domain_cls.reset_mock()
        domain.handle_domain_change_storage(_task(), domain_id="d1", storage_id="s1")

    disk = fake_domain.create_dict["hardware"]["disks"][0]
    assert disk == {}, (
        "the replay wired the failed storage into the domain's first disk: " f"{disk}"
    )
    assert not domain_cls.update_document.called, (
        "the replay wrote to the domain row: "
        f"{domain_cls.update_document.call_args_list}"
    )


# --- row_progress — a tick must not resurrect a download that has since aborted


class _FakeRow:
    """A row read a moment ago, over a store that has since moved on."""

    def __init__(self, store, read_status):
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "id", "m1")
        object.__setattr__(self, "_read_status", read_status)

    @property
    def status(self):
        return self._read_status

    def __setattr__(self, name, value):
        # What the model does: an unguarded write of whatever was decided.
        self._store[name] = value

    @classmethod
    def update_document_if(cls, doc_id, update_data, *, field, values, validate=True):
        raise AssertionError("the fake class is replaced per test")


def _row_over(store, read_status):
    """A ``_FakeRow`` whose class carries a guarded update over the same store."""

    class _Row(_FakeRow):
        @classmethod
        def update_document_if(
            cls, doc_id, update_data, *, field, values, validate=True
        ):
            if store.get(field) not in values:
                return False
            store.update(update_data)
            return True

    return _Row(store, read_status)


def test_a_progress_tick_does_not_revive_a_download_that_has_since_aborted():
    """The tick was in flight while the user aborted.

    ``row.status`` was ``DownloadStarting`` when the tick's row was read, and
    the row says ``DownloadAborting`` by the time the write lands. Writing
    ``Downloading`` from the stale read puts a cancelled transfer back into a
    running state, and the download keeps going.
    """
    from isardvdi_change_handler.task_results import row_progress

    store = {"status": "DownloadAborting"}
    row = _row_over(store, read_status="DownloadStarting")
    resolved = ("media", "download_url", row, {"received": 1})

    row_progress._persist(resolved, final=False)

    assert store["status"] == "DownloadAborting", (
        "a tick read before the abort overwrote it and the row is running "
        f"again: {store}"
    )


def test_a_progress_tick_still_moves_a_row_that_is_genuinely_starting():
    """The control: the ordinary transition must keep happening."""
    from isardvdi_change_handler.task_results import row_progress

    store = {"status": "DownloadStarting"}
    row = _row_over(store, read_status="DownloadStarting")
    resolved = ("media", "download_url", row, {"received": 1})

    assert row_progress._persist(resolved, final=False) is True
    assert store["status"] == "Downloading"


# --- storage.handle_storage_delete — check-then-act on a row that can come back


def test_storage_delete_does_not_drop_a_row_that_came_back_after_the_read():
    """``deleted`` when it was read, ``ready`` when the delete lands.

    A cancel, a heal or a redelivery can revive the row in that window, and
    dropping it then leaves the qcow2 on disk with no row pointing at it.
    """
    from isardvdi_change_handler.task_results import storage

    store = {"status": "ready"}
    deleted = []

    class _Storage:
        @staticmethod
        def exists(_storage_id):
            return True

        def __init__(self, _storage_id):
            # The row as it was read: still marked deleted.
            self.status = "deleted"

        @staticmethod
        def delete(storage_id):
            deleted.append(storage_id)

        @staticmethod
        def delete_document_if(storage_id, *, field, values):
            if store.get(field) in values:
                deleted.append(storage_id)
                return True
            return False

    with patch.object(storage, "Storage", _Storage):
        storage.handle_storage_delete(_task(), "s1")

    assert deleted == [], (
        "the row was revived between the read and the delete and was dropped " "anyway"
    )


def test_storage_delete_still_drops_a_row_that_is_really_deleted():
    """The control: the intended path must keep working."""
    from isardvdi_change_handler.task_results import storage

    store = {"status": "deleted"}
    deleted = []

    class _Storage:
        @staticmethod
        def exists(_storage_id):
            return True

        def __init__(self, _storage_id):
            self.status = store["status"]

        @staticmethod
        def delete(storage_id):
            deleted.append(storage_id)

        @staticmethod
        def delete_document_if(storage_id, *, field, values):
            if store.get(field) in values:
                deleted.append(storage_id)
                return True
            return False

    with patch.object(storage, "Storage", _Storage):
        storage.handle_storage_delete(_task(), "s1")

    assert deleted == ["s1"]
