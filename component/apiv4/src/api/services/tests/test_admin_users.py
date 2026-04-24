# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminUsersService — large façade. Covers the simple
ownership checks, impersonation gate, raw delegates, and a few of
the admin-list/get methods. Full create/edit-flow tests live in
the routes/tests/ layer where MockThink is set up.
"""

from unittest.mock import patch

import pytest
from api.services.admin_users import AdminUsersService
from api.services.error import Error

JWT_PAYLOAD = {"user_id": "u-admin", "category_id": "default", "role_id": "admin"}


class TestOwnership:
    @patch("api.services.admin_users.Helpers.owns_user_id")
    def test_owns_user_id_delegates(self, mock_owns):
        AdminUsersService.owns_user_id(JWT_PAYLOAD, "u1")
        mock_owns.assert_called_once_with(JWT_PAYLOAD, "u1")

    @patch("api.services.admin_users.Helpers.owns_category_id")
    def test_owns_category_id_delegates(self, mock_owns):
        AdminUsersService.owns_category_id(JWT_PAYLOAD, "cat1")
        mock_owns.assert_called_once_with(JWT_PAYLOAD, "cat1")


class TestGetImpersonateJwt:
    @patch(
        "api.services.admin_users.CommonUsers.gen_impersonate_jwt",
        return_value="jwt-string",
    )
    @patch("api.services.admin_users.RethinkUser.exists", return_value=True)
    def test_returns_jwt(self, _exists, mock_gen):
        assert AdminUsersService.get_impersonate_jwt("u1") == "jwt-string"
        mock_gen.assert_called_once_with("u1")

    @patch("api.services.admin_users.RethinkUser.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            AdminUsersService.get_impersonate_jwt("ghost")


class TestUserExists:
    @patch("api.services.admin_users.RethinkUser.exists", return_value=True)
    def test_returns_true(self, _exists):
        assert AdminUsersService.user_exists("u1") is True

    @patch("api.services.admin_users.RethinkUser.exists", return_value=False)
    def test_returns_false(self, _exists):
        assert AdminUsersService.user_exists("ghost") is False


class TestRawDelegates:
    @patch(
        "api.services.admin_users.CommonUsers.get_user_full_data",
        return_value={"id": "u1"},
    )
    def test_full_data_delegates(self, mock_get):
        assert AdminUsersService.get_user_full_data("u1") == {"id": "u1"}
        mock_get.assert_called_once_with("u1")

    @patch(
        "api.services.admin_users.CommonUsers.get_user",
        return_value={"id": "u1"},
    )
    def test_raw_user_delegates(self, mock_get):
        assert AdminUsersService.get_user_raw("u1") == {"id": "u1"}

    @patch(
        "api.services.admin_users.CommonUsers.admin_list_users",
        return_value=[{"id": "u1"}, {"id": "u2"}],
    )
    def test_list_users_forwards_filters(self, mock_list):
        AdminUsersService.list_users(nav="admin", category_id="default")
        mock_list.assert_called_once_with("admin", "default")
