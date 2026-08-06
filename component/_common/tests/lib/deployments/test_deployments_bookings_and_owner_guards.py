#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``check_deployment_bookings`` and ``_change_owner_deployments``.

* ``check_deployment_bookings``: a future booking that reserved fewer units
  than the deployment now needs blocks recreate (L614)
  deployment_recreate_booking_not_enough_units.
* ``_change_owner_deployments``: a ``user``-role target cannot own
  deployments (L772) — and, being on the destructive owner-change path, the
  guard must fire *before* any ownership write.

Both run unmocked; rethink and the user/name collaborators are stubbed.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.deployments import deployments as mod

DP = mod.DeploymentsProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rdb(monkeypatch):
    monkeypatch.setattr(DP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(DP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    return tbl


def _deployment():
    return {"id": "dep-1", "allowed": {}, "create_dict": [{"name": "recipe"}]}


class TestCheckDeploymentBookings:
    def test_booking_with_too_few_units_rejected(self, rdb, monkeypatch):
        rdb.get_all.return_value.filter.return_value.run.return_value = [
            {"units": 1, "start": "s", "end": "e"}
        ]
        monkeypatch.setattr(
            mod.DeploymentUsers,
            "get_selected_users",
            classmethod(lambda cls, *a, **k: ["u-1", "u-2"]),  # needs 2 units
        )
        with pytest.raises(Error) as exc:
            DP.check_deployment_bookings({"user_id": "u-1"}, _deployment())
        assert (
            exc.value.error["description_code"]
            == "deployment_recreate_booking_not_enough_units"
        )

    def test_booking_with_enough_units_passes(self, rdb, monkeypatch):
        rdb.get_all.return_value.filter.return_value.run.return_value = [
            {"units": 5, "start": "s", "end": "e"}
        ]
        monkeypatch.setattr(
            mod.DeploymentUsers,
            "get_selected_users",
            classmethod(lambda cls, *a, **k: ["u-1", "u-2"]),
        )
        assert DP.check_deployment_bookings({"user_id": "u-1"}, _deployment()) is None


class TestChangeOwnerRoleGuard:
    def test_role_user_cannot_own_and_nothing_is_written(self, rdb, monkeypatch):
        monkeypatch.setattr(
            mod.Helpers,
            "update_duplicated_names",
            classmethod(lambda cls, *a, **k: None),
        )
        rdb.get_all.return_value.pluck.return_value.run.return_value = []
        user_data = {
            "payload": {"role_id": "user"},
            "new_user": {"user": "u-new"},
        }
        with pytest.raises(Error) as exc:
            DP._change_owner_deployments(["dep-1"], user_data, "u-old")
        assert exc.value.error["error"] == "bad_request"
        # destructive path: no ownership write happened before the reject
        rdb.get_all.return_value.update.assert_not_called()
        rdb.get.return_value.update.assert_not_called()
