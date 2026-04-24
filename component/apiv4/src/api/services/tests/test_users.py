# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for UsersService — façade over CommonUser, IsardVpn, Quotas
and CommonUserPolicies. Tests pin the not-found dispatch + the simple
delegate patterns.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.users import UsersService


class TestCheckUserExists:
    @patch("api.services.users.CommonUser.check_user_exists", return_value=True)
    def test_forwards_uid_category_provider(self, mock_check):
        UsersService.check_user_exists("uid1", "default", "local")
        mock_check.assert_called_once_with(
            uid="uid1", category_id="default", provider="local"
        )


class TestGetUserVpn:
    @patch(
        "api.services.users.IsardVpn.vpn_data",
        return_value={"interface": "wg0"},
    )
    def test_calls_users_config_with_user_id(self, mock_vpn):
        UsersService.get_user_vpn("u1")
        mock_vpn.assert_called_once_with("users", "config", False, "u1")


class TestResetUserVpn:
    @patch("api.services.users.CommonUser.reset_vpn", return_value="task-1")
    def test_returns_task_id(self, mock_reset):
        assert UsersService.reset_user_vpn("u1") == "task-1"
        mock_reset.assert_called_once_with("u1")


class TestGetAllowedHardware:
    @patch(
        "api.services.users.Quotas.get_hardware_allowed",
        return_value={"vcpus": 4},
    )
    @patch(
        "api.services.users.Helpers.gen_payload_from_user",
        return_value={"user_id": "u1", "category_id": "default"},
    )
    @patch("api.services.users.RethinkUser.exists", return_value=True)
    def test_returns_quota_data(self, _exists, _payload, mock_get):
        result = UsersService.get_allowed_hardware("u1")
        mock_get.assert_called_once_with(
            {"user_id": "u1", "category_id": "default"}, domain_id=None
        )
        assert result == {"vcpus": 4}

    @patch("api.services.users.RethinkUser.exists", return_value=False)
    def test_raises_not_found_for_missing_user(self, _exists):
        with pytest.raises(Error):
            UsersService.get_allowed_hardware("ghost")


class TestGetUserInfo:
    @patch(
        "api.services.users.CommonUser.get_user_info",
        return_value={"id": "u1", "name": "alice"},
    )
    @patch("api.services.users.RethinkUser.exists", return_value=True)
    def test_delegates_to_common(self, _exists, mock_info):
        result = UsersService.get_user_info("u1")
        assert result == {"id": "u1", "name": "alice"}
        mock_info.assert_called_once_with("u1")

    @patch("api.services.users.RethinkUser.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            UsersService.get_user_info("ghost")


class TestGetUserConfig:
    @patch(
        "api.services.users.CommonUser.user_config",
        return_value={"language": "en"},
    )
    def test_passes_payload_through(self, mock_cfg):
        payload = {"user_id": "u1", "category_id": "default"}
        result = UsersService.get_user_config(payload)
        mock_cfg.assert_called_once_with(payload)
        assert result == {"language": "en"}
