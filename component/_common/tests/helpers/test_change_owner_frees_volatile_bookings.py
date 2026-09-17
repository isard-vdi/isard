#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Changing a desktop's owner frees the bookings of the volatiles it destroys.

Volatiles are not migrated, they are handed to the engine as ``ForceDeleting``
-- which drops the domain row without touching ``bookings``. A user migration
selects by ``kind_user`` with no ``persistent`` filter, so every volatile the
user held goes through this path.
"""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import helpers as mod

Helpers = mod.Helpers

USER_DATA = {
    "new_user": {"user": "u-2", "username": "two", "category": "c-1"},
    "payload": {},
}


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(Helpers, "_rdb_context", classmethod(lambda cls: nullcontext()))
    # Metaclass property: patching it on Helpers itself can't be undone.
    monkeypatch.setattr(type(Helpers), "_rdb_connection", property(lambda cls: None))

    def _domain(domain_id, persistent):
        return {
            "id": domain_id,
            "kind": "desktop",
            "name": domain_id,
            "category": "c-1",
            "create_dict": {},
            "persistent": persistent,
        }

    domains = [
        _domain("vol-1", False),
        _domain("vol-2", False),
        _domain("keep-1", True),
    ]
    table = MagicMock()
    table.get_all.return_value.pluck.return_value.run.return_value = domains
    rethink = MagicMock()
    rethink.table.return_value = table
    monkeypatch.setattr(mod, "r", rethink)

    monkeypatch.setattr(Helpers, "update_duplicated_names", staticmethod(MagicMock()))
    monkeypatch.setattr(
        Helpers, "revoke_hardware_permissions", staticmethod(MagicMock())
    )
    monkeypatch.setattr(Helpers, "change_storage_ownership", staticmethod(MagicMock()))

    released = MagicMock()
    import isardvdi_common.helpers.bookings as bookings_mod

    # Imported inside the method to dodge a circular import, so it has to be
    # patched where it lives rather than on the module under test.
    monkeypatch.setattr(
        bookings_mod.Bookings, "delete_item_bookings", staticmethod(released)
    )
    return {"table": table, "released": released}


def test_the_volatiles_bookings_are_freed(stub):
    Helpers.change_owner_domains(["vol-1", "vol-2", "keep-1"], USER_DATA, "desktop")

    assert [c.args for c in stub["released"].call_args_list] == [
        ("desktop", "vol-1"),
        ("desktop", "vol-2"),
    ]


def test_the_migrated_persistent_desktops_are_not_touched(stub):
    Helpers.change_owner_domains(["vol-1", "vol-2", "keep-1"], USER_DATA, "desktop")

    # A migrated desktop keeps existing; only the destroyed volatiles are freed.
    assert ("desktop", "keep-1") not in [
        c.args for c in stub["released"].call_args_list
    ]


def test_the_teardown_still_happens_when_a_booking_cannot_be_freed(stub):
    stub["released"].side_effect = RuntimeError("rethink down")

    Helpers.change_owner_domains(["vol-1"], USER_DATA, "desktop")

    # Best-effort: a reservation we could not release must not block the
    # ownership change.
    assert stub["table"].get_all.return_value.update.called
