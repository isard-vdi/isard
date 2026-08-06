# SPDX-License-Identifier: AGPL-3.0-or-later

"""Authorization / precondition guards on ``AdminUsersService``.

The highest-value guard here is impersonation: a caller must not be able to
impersonate a role above their own (a manager must not become an admin). A
guard that stops firing does not error — it hands over an admin session. So
the rank rule and its reject code are pinned, plus the group-create
preconditions.

Each is pinned to BOTH HTTP status and description_code. The service runs
unmocked; only its Rethink/user-lookup collaborators are patched.
"""

from unittest.mock import patch

import pytest
from api.services.admin.users import AdminUsersService
from api.services.error import Error

MOD = "api.services.admin.users."


def _payload(role_id, user_id="caller", category_id="cat1"):
    return {"user_id": user_id, "role_id": role_id, "category_id": category_id}


class TestGetImpersonateJwtGuards:
    def test_unknown_target_404(self):
        with patch(MOD + "RethinkUser.exists", return_value=False):
            with pytest.raises(Error) as exc:
                AdminUsersService.get_impersonate_jwt(_payload("admin"), "ghost")
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "not_found"

    def test_manager_cannot_impersonate_admin_403(self):
        with patch(MOD + "RethinkUser.exists", return_value=True), patch(
            MOD + "CommonUsers.get_user", return_value={"role": "admin"}
        ):
            with pytest.raises(Error) as exc:
                AdminUsersService.get_impersonate_jwt(_payload("manager"), "target")
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_unknown_target_role_403(self):
        # a target whose role is not in the rank table -> rank < 0 -> rejected
        with patch(MOD + "RethinkUser.exists", return_value=True), patch(
            MOD + "CommonUsers.get_user", return_value={"role": "wizard"}
        ):
            with pytest.raises(Error) as exc:
                AdminUsersService.get_impersonate_jwt(_payload("admin"), "target")
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_admin_can_impersonate_manager(self):
        with patch(MOD + "RethinkUser.exists", return_value=True), patch(
            MOD + "CommonUsers.get_user", return_value={"role": "manager"}
        ), patch(
            MOD + "CommonUsers.gen_impersonate_jwt", return_value={"jwt": "tok"}
        ) as gen:
            result = AdminUsersService.get_impersonate_jwt(_payload("admin"), "target")
        assert result == {"jwt": "tok"}
        gen.assert_called_once_with("target")

    def test_equal_rank_allowed(self):
        with patch(MOD + "RethinkUser.exists", return_value=True), patch(
            MOD + "CommonUsers.get_user", return_value={"role": "manager"}
        ), patch(MOD + "CommonUsers.gen_impersonate_jwt", return_value={"jwt": "tok"}):
            # manager impersonating a manager (equal rank) is allowed
            assert AdminUsersService.get_impersonate_jwt(
                _payload("manager"), "target"
            ) == {"jwt": "tok"}


class TestCreateGroupGuards:
    def test_admin_without_parent_category_400(self):
        with pytest.raises(Error) as exc:
            AdminUsersService.create_group(_payload("admin"), {"name": "g"})
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "parent_category_required"

    def test_unknown_parent_category_404(self):
        with patch(MOD + "Caches.get_document", return_value=None):
            with pytest.raises(Error) as exc:
                AdminUsersService.create_group(
                    _payload("admin"), {"name": "g", "parent_category": "nope"}
                )
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "category_not_found"
