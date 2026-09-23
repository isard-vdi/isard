# SPDX-License-Identifier: AGPL-3.0-or-later

"""Parking a disk carries the status test that authorised it, so only one caller wins.

``set_maintenance`` read the row's status, then walked the domains and children of
the disk -- several round trips -- and only then wrote ``maintenance``. Two callers
that both read ``ready`` in that window both parked the same disk and both went on
to allocate a replacement. Measured under load: four concurrent recreates on one
desktop were accepted 1.6 times on average.

The write now carries the test, so of N racers exactly one replaces the document.
Actions with no status precondition (create, delete, download) keep the plain
write they had: there is no observed status to carry.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models.storage import Storage


@pytest.fixture
def row(monkeypatch):
    """One shared row with an in-memory compare-and-set, and callers that each
    snapshot the status while it still reads ``ready`` -- the stale read that is
    the bug."""
    shared = {"status": "ready"}
    guarded = []

    def _update_document_if(doc_id, update_data, *, field, values, validate=True):
        guarded.append((doc_id, dict(update_data), tuple(values)))
        if shared.get(field) not in values:
            return False
        shared.update(update_data)
        return True

    monkeypatch.setattr(
        Storage, "update_document_if", staticmethod(_update_document_if)
    )
    monkeypatch.setattr(Storage, "_update_cache", lambda self, **kw: None)
    monkeypatch.setattr(Storage, "children", [])
    monkeypatch.setattr(Storage, "domains", [])

    def _caller(observed="ready"):
        s = Storage.__new__(Storage)
        s.__dict__.update({"id": "disk-1", "status": observed})
        monkeypatch.setattr(
            Storage,
            "__setattr__",
            lambda self, name, value: self.__dict__.__setitem__(name, value),
        )
        return s

    return MagicMock(shared=shared, guarded=guarded, caller=_caller)


class TestOnlyOneCallerParksTheDisk:
    def test_the_second_caller_is_refused(self, row):
        first, second = row.caller(), row.caller()
        first.set_maintenance("recreate")
        assert row.shared["status"] == "maintenance"
        with pytest.raises(Error) as exc:
            second.set_maintenance("recreate")
        assert exc.value.error["description_code"] == "storage_not_ready"

    def test_the_write_carries_the_status_it_was_authorised_from(self, row):
        row.caller().set_maintenance("recreate")
        doc_id, update, values = row.guarded[-1]
        assert doc_id == "disk-1"
        assert update["status"] == "maintenance"
        assert values == ("ready",)

    def test_a_move_may_be_claimed_from_recycled_too(self, row):
        row.shared["status"] = "recycled"
        mover = row.caller("recycled")
        mover.set_maintenance("move")
        assert row.shared["status"] == "maintenance"
        assert row.guarded[-1][2] == ("ready", "recycled")

    def test_a_lost_move_keeps_the_move_refusal(self, row):
        row.caller().set_maintenance("recreate")
        with pytest.raises(Error) as exc:
            row.caller("ready").set_maintenance("move")
        assert exc.value.error["description_code"] == "storage_invalid_status_for_move"


class TestTheUnguardedActionsAreUnchanged:
    @pytest.mark.parametrize("action", ["create", "delete", "download"])
    def test_they_never_reach_the_guarded_write(self, row, action, monkeypatch):
        def _boom(*a, **k):
            raise AssertionError("an unguarded action must not take the claim path")

        monkeypatch.setattr(Storage, "update_document_if", staticmethod(_boom))
        caller = row.caller("deleted")
        caller.set_maintenance(action)
        assert caller.status == "maintenance"
