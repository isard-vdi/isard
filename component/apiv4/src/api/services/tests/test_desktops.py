# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for DesktopService — partial coverage of the highest-traffic
service in apiv4. Tests focus on dispatcher/forward methods that are
safe to mock; full creation-flow tests would require a live MockThink
DB and live up to the routes/tests/ layer.
"""

from unittest.mock import patch

import pytest
from api.services.desktops import DesktopService
from api.services.error import Error

JWT_PAYLOAD = {
    "user_id": "u1",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "user",
}


class TestGetUserAllowedReservables:
    @patch(
        "api.services.desktops.Alloweds.get_items_allowed",
        return_value=[{"id": "vgpu-1", "name": "T4"}],
    )
    def test_uses_reservables_vgpus_table_with_pluck(self, mock_alloweds):
        DesktopService.get_user_allowed_reservables(JWT_PAYLOAD)
        args, kwargs = mock_alloweds.call_args
        assert args[1] == "reservables_vgpus"
        assert kwargs["query_pluck"] == ["id", "name", "description"]
        assert kwargs["order"] == "name"
        assert kwargs["query_merge"] is False


class TestCreateDesktopGuards:
    @patch("api.services.desktops.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_unknown_user(self, _exists):
        # Build a minimal stand-in for the request body — only the
        # template_id field is touched before the user-existence guard
        # kicks in.
        from types import SimpleNamespace

        data = SimpleNamespace(
            template_id="t1",
            name="d1",
            description="",
            persistent=True,
            hardware=None,
            guest_properties=None,
            reservables=None,
            image=None,
            bastion_target=None,
        )
        with pytest.raises(Error):
            DesktopService.create_desktop("ghost", data)


class TestCreateNonpersistentDesktop:
    @patch("api.services.desktops.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_unknown_user(self, _exists):
        with pytest.raises(Error):
            DesktopService.create_nonpersistent_desktop({"user_id": "ghost"}, "t1")
