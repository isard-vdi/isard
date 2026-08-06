# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for UsersService — façade over CommonUser, IsardVpn, Quotas
and CommonUserPolicies. Tests pin the not-found dispatch + the simple
delegate patterns.
"""

import base64
import struct
from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.users import UsersService, validate_ssh_public_key


def _valid_ed25519(seed: bytes = b"\x01" * 32, comment: str = "test@host") -> str:
    """Build a structurally valid ssh-ed25519 public key string."""
    blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + seed
    key = "ssh-ed25519 " + base64.b64encode(blob).decode()
    return f"{key} {comment}" if comment else key


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


class TestValidateSshPublicKey:
    def test_accepts_valid_ed25519_and_trims(self):
        key = _valid_ed25519()
        assert validate_ssh_public_key("  " + key + "  ") == key

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "   ",
            "not-a-key",
            "ssh-ed25519",
            "ssh-rsa not-base64!!!",
            "rsa-sha2 AAAA",  # unknown type token
        ],
    )
    def test_rejects_invalid(self, bad):
        with pytest.raises(Error):
            validate_ssh_public_key(bad)

    def test_rejects_multiple_keys(self):
        two = _valid_ed25519() + "\n" + _valid_ed25519(seed=b"\x02" * 32)
        with pytest.raises(Error):
            validate_ssh_public_key(two)

    def test_rejects_type_mismatch(self):
        # Token says ssh-rsa but the blob embeds ssh-ed25519.
        blob = (
            struct.pack(">I", 11)
            + b"ssh-ed25519"
            + struct.pack(">I", 32)
            + b"\x01" * 32
        )
        key = "ssh-rsa " + base64.b64encode(blob).decode()
        with pytest.raises(Error):
            validate_ssh_public_key(key)


class TestGetUserBastionSshKey:
    @patch("api.services.users.RethinkUser")
    def test_returns_key(self, mock_user):
        mock_user.exists.return_value = True
        mock_user.return_value.bastion_ssh_key = "ssh-ed25519 AAAA test"
        assert UsersService.get_user_bastion_ssh_key("u1") == {
            "ssh_key": "ssh-ed25519 AAAA test"
        }

    @patch("api.services.users.RethinkUser")
    def test_returns_none_when_blank(self, mock_user):
        mock_user.exists.return_value = True
        mock_user.return_value.bastion_ssh_key = "   "
        assert UsersService.get_user_bastion_ssh_key("u1") == {"ssh_key": None}

    @patch("api.services.users.RethinkUser")
    def test_not_found(self, mock_user):
        mock_user.exists.return_value = False
        with pytest.raises(Error):
            UsersService.get_user_bastion_ssh_key("u1")


class TestSetUserBastionSshKey:
    @patch("api.services.users.CommonUser.update_user")
    @patch("api.services.users.RethinkUser.exists", return_value=True)
    def test_validates_and_stores(self, _exists, mock_update):
        key = _valid_ed25519()
        UsersService.set_user_bastion_ssh_key("u1", "  " + key + "  ")
        mock_update.assert_called_once_with(
            "u1", {"bastion_ssh_key": key}, revoke=False
        )

    @patch("api.services.users.RethinkUser.exists", return_value=True)
    def test_rejects_invalid_key(self, _exists):
        with pytest.raises(Error):
            UsersService.set_user_bastion_ssh_key("u1", "garbage")

    @patch("api.services.users.RethinkUser.exists", return_value=False)
    def test_not_found(self, _exists):
        with pytest.raises(Error):
            UsersService.set_user_bastion_ssh_key("u1", _valid_ed25519())


class TestDeleteUserBastionSshKey:
    @patch("api.services.users.CommonUser.update_user")
    @patch("api.services.users.RethinkUser.exists", return_value=True)
    def test_clears_key(self, _exists, mock_update):
        UsersService.delete_user_bastion_ssh_key("u1")
        mock_update.assert_called_once_with(
            "u1", {"bastion_ssh_key": None}, revoke=False
        )

    @patch("api.services.users.RethinkUser.exists", return_value=False)
    def test_not_found(self, _exists):
        with pytest.raises(Error):
            UsersService.delete_user_bastion_ssh_key("u1")
