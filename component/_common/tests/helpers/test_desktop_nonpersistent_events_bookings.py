#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deleting a temporal desktop frees the vGPU units it had reserved.

Nothing downstream does it: the engine's ``force_deleting`` drops the domain
row without touching ``bookings``, and the planner measures capacity from the
bookings table alone, so the booking would keep a unit reserved until its
natural end long after the desktop is gone.
"""

from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import desktop_nonpersistent_events as mod

DNE = mod.DesktopNonpersistentEvents


@pytest.fixture
def stub(monkeypatch):
    monkeypatch.setattr(DNE, "_rdb_context", classmethod(lambda cls: nullcontext()))
    # Metaclass property: patching it on DNE itself can't be undone on teardown.
    monkeypatch.setattr(type(DNE), "_rdb_connection", property(lambda cls: None))

    table = MagicMock()
    rethink = MagicMock()
    rethink.table.return_value = table
    monkeypatch.setattr(mod, "r", rethink)

    delete_bookings = MagicMock()
    # Imported inside the method to dodge a circular import, so it has to be
    # patched where it lives rather than on this module.
    import isardvdi_common.helpers.bookings as bookings_mod

    monkeypatch.setattr(
        bookings_mod.Bookings, "delete_item_bookings", staticmethod(delete_bookings)
    )
    return {"table": table, "delete_bookings": delete_bookings}


def test_deleting_one_desktop_frees_its_bookings(stub):
    DNE.desktop_non_persistent_delete("d-1")

    stub["delete_bookings"].assert_called_once_with("desktop", "d-1")
    stub["table"].get.return_value.update.assert_called_once_with(
        {"status": "ForceDeleting"}
    )


def test_the_desktop_is_still_deleted_when_the_bookings_cannot_be_freed(stub):
    stub["delete_bookings"].side_effect = RuntimeError("rethink down")

    DNE.desktop_non_persistent_delete("d-1")

    # Best-effort: a reservation we failed to release must not strand the
    # desktop it belonged to.
    stub["table"].get.return_value.update.assert_called_once()


def test_deleting_a_templates_desktops_frees_each_of_their_bookings(stub):
    stub[
        "table"
    ].get_all.return_value.filter.return_value.get_field.return_value.run.return_value = [
        "d-1",
        "d-2",
    ]

    DNE.desktops_non_persistent_delete("u-1", "t-1")

    assert [c.args for c in stub["delete_bookings"].call_args_list] == [
        ("desktop", "d-1"),
        ("desktop", "d-2"),
    ]
