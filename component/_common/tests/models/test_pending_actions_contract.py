# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every pending action a disk can carry is declared once, with who flags it and
what clears it, and the model refuses one that is not."""

import pytest
from isardvdi_common.models.storage import PENDING_ACTIONS, Storage
from isardvdi_common.schemas.storage import StoragePendingAction


def test_the_enum_and_the_table_name_the_same_actions():
    assert {a.value for a in StoragePendingAction} == set(PENDING_ACTIONS)


@pytest.mark.parametrize("action", sorted(PENDING_ACTIONS))
def test_every_action_says_who_flags_it_and_what_clears_it(action):
    entry = PENDING_ACTIONS[action]
    assert entry["flagged_by"], f"{action}: nobody is declared to flag it"
    assert entry["cleared_by"], f"{action}: nothing is declared to clear it"


def test_an_unknown_action_is_refused_before_any_write(monkeypatch):
    called = []
    monkeypatch.setattr(
        Storage, "_rdb_context", classmethod(lambda cls: called.append(1))
    )
    with pytest.raises(ValueError):
        Storage.flag_pending("s1", "polish", "test")
    assert called == []
