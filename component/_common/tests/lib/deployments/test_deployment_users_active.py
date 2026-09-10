#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``get_users_info`` reports whether each allowed user is enabled.

A recreate resolves its users through ``get_selected_users``, which keeps only
``active == True``. The deployment view lists the *allowed* users instead, so
without this flag a disabled user is indistinguishable from one the recreate
will serve.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.deployments import deployment_users as mod

DU = mod.DeploymentUsers


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def users(monkeypatch):
    """``state['rows']`` is what the users table returns."""
    state = {"rows": []}

    monkeypatch.setattr(DU, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DU), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(DU, "get_users", classmethod(lambda cls, did: ["u-1"]))
    monkeypatch.setattr(
        mod.DeploymentDesktopsProcessed,
        "get_deployment_desktops_grouped_by_user_status",
        classmethod(lambda cls, did: []),
    )

    tbl = MagicMock(name="r.table")
    tbl.get_all.return_value.pluck.return_value.run.side_effect = lambda _c: state[
        "rows"
    ]
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    return state


def _row(**extra):
    return {"id": "u-1", "name": "One", "username": "one", **extra}


class TestGetUsersInfoActive:
    def test_enabled_user_is_active(self, users):
        users["rows"] = [_row(active=True)]
        assert DU.get_users_info("dep-1")[0]["active"] is True

    def test_disabled_user_is_not_active(self, users):
        users["rows"] = [_row(active=False)]
        assert DU.get_users_info("dep-1")[0]["active"] is False

    def test_missing_flag_is_not_active(self, users):
        # get_selected_users filters on ``active == True``, and a row without
        # the field does not match it either: report the same answer.
        users["rows"] = [_row()]
        assert DU.get_users_info("dep-1")[0]["active"] is False
