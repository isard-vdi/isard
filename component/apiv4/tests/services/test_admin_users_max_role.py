# SPDX-License-Identifier: AGPL-3.0-or-later

"""The apiv4 user writes check the per-provider max_role before writing."""

from unittest.mock import MagicMock, patch

import pytest
from api.services.admin.users import AdminUsersService
from isardvdi_common.helpers.error_factory import Error as CommonError

MOD = "api.services.admin.users."


def _payload(role_id="admin"):
    return {"user_id": "caller", "role_id": role_id, "category_id": "cat1"}


class TestCreateUserHonoursMaxRole:
    @patch(MOD + "Caches.get_document", return_value={"parent_category": "cat1"})
    @patch(MOD + "RethinkGroup.exists", return_value=True)
    @patch(MOD + "RethinkCategory.exists", return_value=True)
    @patch(MOD + "RethinkUser.init_document")
    @patch(MOD + "AdminUsersService.owns_category_id")
    @patch(MOD + "CommonUsers.check_user_exists", return_value=False)
    def test_rejected_before_insert(
        self, _exists, _owns, init_document, _cat, _grp, _doc
    ):
        data = {
            "username": "u1",
            "name": "u1",
            "provider": "local",
            "category": "cat1",
            "group": "g1",
            "role": "manager",
            "password": "x",
        }
        with patch(
            MOD + "CommonUsers.check_max_role",
            side_effect=CommonError("forbidden", "cap"),
        ) as gate:
            with pytest.raises(CommonError):
                AdminUsersService.create_user(_payload(), data)
        gate.assert_called_once_with("cat1", "local", "manager")
        init_document.assert_not_called()


class TestUpdateUserHonoursMaxRole:
    @patch(MOD + "CommonUsers.update_user")
    @patch(MOD + "CommonMigrations.enable_users_check")
    @patch(MOD + "Caches.get_document")
    def test_role_change_rejected_before_write(self, get_doc, _mig, update_user):
        get_doc.return_value = {
            "role": "user",
            "category": "cat1",
            "provider": "local",
            "name": "u2",
        }
        with patch(
            MOD + "CommonUsers.check_max_role",
            side_effect=CommonError("forbidden", "cap"),
        ) as gate:
            with pytest.raises(CommonError):
                AdminUsersService.update_user(_payload(), "u2", {"role": "manager"})
        gate.assert_called_once_with("cat1", "local", "manager")
        update_user.assert_not_called()

    @patch(MOD + "CommonUsers.update_user")
    @patch(MOD + "CommonMigrations.enable_users_check")
    @patch(MOD + "Caches.get_document")
    def test_category_move_checks_the_target_cap(self, get_doc, _mig, update_user):
        get_doc.return_value = {
            "role": "manager",
            "category": "cat1",
            "provider": "local",
            "name": "u3",
        }
        with patch(
            MOD + "CommonUsers.check_max_role",
            side_effect=CommonError("forbidden", "cap"),
        ) as gate:
            with pytest.raises(CommonError):
                AdminUsersService.update_user(_payload(), "u3", {"category": "cat2"})
        gate.assert_called_once_with("cat2", "local", "manager")
        update_user.assert_not_called()
