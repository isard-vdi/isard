#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A logs ``old_entries`` config stored with an action and no ``max_time``."""

import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.lib.api_admin import ApiAdmin


@pytest.mark.parametrize(
    "table,getter",
    [
        ("logs_desktops", "get_logs_desktops_old_entries_config"),
        ("logs_users", "get_logs_users_old_entries_config"),
    ],
)
@pytest.mark.parametrize(
    "method", ["get_old_entry_cutoff", "get_older_than_old_entry_max_time"]
)
def test_an_action_stored_without_a_window_is_a_precondition(
    monkeypatch, table, getter, method
):
    monkeypatch.setattr(ApiAdmin, getter, classmethod(lambda cls: {"action": "delete"}))
    with pytest.raises(ErrorBase) as exc:
        getattr(ApiAdmin, method)(table)
    assert exc.value.error["error"] == "precondition_required"
