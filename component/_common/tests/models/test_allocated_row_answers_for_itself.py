# SPDX-License-Identifier: AGPL-3.0-or-later

"""An allocated storage row carries a status clock and is named by its chain.

The reconcile's stuck-storage pass reads two things before it touches a row:
``status_time``, for the grace that keeps a just-parked row from being re-issued
work, and the per-owner task index, for whether the row's chain is still live.
Both were unavailable for a row ``recreate`` allocates. ``status_time`` is only
ever written by ``RethinkBase.__setattr__``, which a raw insert skips, so every
row born through ``new_dict`` had none and got no grace at all; and ``recreate``
named the OLD row as the chain's owner -- the one the chain ends by deleting --
so the new row answered to nobody and read as dead work from the moment it
existed.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


class TestNewDictStampsTheStatusClock:
    @pytest.fixture
    def inserted(self, monkeypatch):
        captured = {}

        def _init_document(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr(Storage, "exists", staticmethod(lambda _id: True))
        monkeypatch.setattr(Storage, "init_document", staticmethod(_init_document))
        monkeypatch.setattr(
            mod,
            "new_storage_directory_path",
            staticmethod(lambda *a, **k: "/isard/groups"),
        )
        Storage.new_dict("u-1", "desktop", "tmpl-1")
        return captured

    def test_the_insert_carries_a_numeric_status_time(self, inserted):
        assert isinstance(inserted.get("status_time"), (int, float))

    def test_it_is_the_clock_of_the_status_it_was_born_in(self, inserted, monkeypatch):
        assert inserted["status"] == "non_existing"
        assert inserted["status_time"] == pytest.approx(mod.time(), abs=60)


@pytest.fixture
def rec(monkeypatch):
    """An old disk whose recreate collaborators are stubbed, capturing the
    kwargs the chain hands to ``create_task``."""
    calls = []

    old = Storage.__new__(Storage)
    old.__dict__.update(
        {
            "id": "old-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": "tmpl-1",
            "path": "/isard/groups/old-1.qcow2",
            "directory_path": "/isard/groups",
            "status": "ready",
            "status_logs": [],
        }
    )

    monkeypatch.setattr(
        Storage,
        "__setattr__",
        lambda self, name, value: self.__dict__.__setitem__(name, value),
    )
    monkeypatch.setattr(Storage, "operational", True)
    monkeypatch.setattr(Storage, "pool_usage", "desktop")
    monkeypatch.setattr(Storage, "category", "cat-1")
    monkeypatch.setattr(Storage, "domains", [])
    monkeypatch.setattr(Storage, "exists", staticmethod(lambda _id: True))
    monkeypatch.setattr(Storage, "set_maintenance", lambda self, *a, **k: None)

    # ``recreate`` reads the domain's disk count before anything else, so a
    # fixture that leaves it real opens a database socket instead of testing.
    single_disk = MagicMock()
    single_disk.create_dict = {"hardware": {"disks": [{"storage_id": "disk-1"}]}}
    fake_domain = MagicMock()
    fake_domain.exists.return_value = True
    fake_domain.return_value = single_disk
    monkeypatch.setattr(mod.domain, "Domain", fake_domain)
    monkeypatch.setattr(mod.qcow2_geometry, "policy", staticmethod(lambda: {}))
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        staticmethod(lambda *a, **k: MagicMock(id="pool-1")),
    )
    monkeypatch.setattr(
        mod, "new_storage_directory_path", staticmethod(lambda *a, **k: "/isard/groups")
    )
    monkeypatch.setattr(mod.queue_coverage, "check_shed", lambda *a, **k: None)

    def _init(self, sid=None, *a, **k):
        self.__dict__.update(
            {
                "id": sid,
                "type": "qcow2",
                "directory_path": "/isard/templates",
                "parent": None,
            }
        )

    monkeypatch.setattr(Storage, "__init__", _init)

    def _new_dict(user_id, pool_usage, parent_id=None, format="qcow2"):
        new = Storage.__new__(Storage)
        new.__dict__.update(
            {
                "id": "new-1",
                "user_id": user_id,
                "type": format,
                "status": "non_existing",
                "parent": parent_id,
                "directory_path": "/isard/groups",
                "status_logs": [],
            }
        )
        return new

    monkeypatch.setattr(Storage, "new_dict", staticmethod(_new_dict))

    def _create_task(self, *a, **k):
        calls.append(k)
        return "task-1"

    monkeypatch.setattr(Storage, "create_task", _create_task)
    return SimpleNamespace(old=old, calls=calls)


class TestRecreateNamesTheRowItAllocates:
    def test_both_rows_own_the_chain(self, rec):
        rec.old.recreate("u-1", "dom-1")
        assert rec.calls[0]["index_owners"] == ["old-1", "new-1"]

    def test_the_allocated_row_is_named_at_all(self, rec):
        """The regression itself: the default is ``[self.id]``, which names the
        row the chain DELETES and leaves the new one owned by nobody."""
        rec.old.recreate("u-1", "dom-1")
        assert "new-1" in rec.calls[0].get("index_owners", ["old-1"])
