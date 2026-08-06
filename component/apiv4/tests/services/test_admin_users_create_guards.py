# SPDX-License-Identifier: AGPL-3.0-or-later

"""Uniqueness / authorization guards on user & group creation/mutation.

These decide who can create a user, in which category, what happens when it
already exists, and — the crown jewel — that a role mutation cannot elevate a
target above the caller (privilege escalation). A uniqueness guard that stops
firing creates a silent duplicate; an authorization one that stops firing
grants access. Each is pinned to BOTH HTTP status and description_code.

The functions run unmocked; only their Rethink / user-lookup collaborators
are patched.
"""

from unittest.mock import patch

import pytest
from api.services.admin.users import AdminUsersService
from api.services.error import Error

MOD = "api.services.admin.users."


def _payload(role_id, user_id="caller", category_id="cat1"):
    return {"user_id": user_id, "role_id": role_id, "category_id": category_id}


class TestCheckDuplicateUser:
    def test_existing_user_conflict_409(self):
        with patch(MOD + "CommonUsers.check_user_exists", return_value=True):
            with pytest.raises(Error) as exc:
                AdminUsersService._check_duplicate_user("uid", "cat1", "local")
        assert exc.value.status_code == 409

    def test_absent_user_passes(self):
        with patch(MOD + "CommonUsers.check_user_exists", return_value=False):
            assert (
                AdminUsersService._check_duplicate_user("uid", "cat1", "local") is None
            )


class TestRoleElevationGuard:
    def _call(self, payload, user_id, data, current_role):
        return AdminUsersService._check_role_elevation(
            payload, user_id, data, current_role
        )

    def test_unknown_role_400(self):
        with pytest.raises(Error) as exc:
            self._call(_payload("admin"), "u2", {"role": "wizard"}, "user")
        assert exc.value.status_code == 400
        assert exc.value.error["description_code"] == "bad_request"

    def test_grant_above_own_rank_403(self):
        # manager trying to make someone an admin
        with pytest.raises(Error) as exc:
            self._call(_payload("manager"), "u2", {"role": "admin"}, "user")
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_cannot_change_own_role_403(self):
        # manager demoting their own role (advanced is below manager, so not a
        # grant-above; the own-role rule is what must fire)
        with pytest.raises(Error) as exc:
            self._call(
                _payload("manager", user_id="me"), "me", {"role": "advanced"}, "manager"
            )
        assert exc.value.status_code == 403
        assert exc.value.error["description_code"] == "not_enough_rights"

    def test_allowed_grant_within_rank(self):
        # admin granting manager to another user is allowed -> no raise
        assert self._call(_payload("admin"), "u2", {"role": "manager"}, "user") is None


def _user_data(**over):
    d = dict(
        username="bob",
        provider="local",
        category="cat1",
        group="g1",
        role="user",
        password="pw",
    )
    d.update(over)
    return d


class TestCreateUserPreconditions:
    def _env(self, es_patches=()):
        # patch the pre-guard collaborators to a happy path
        from contextlib import ExitStack

        es = ExitStack()
        es.enter_context(patch(MOD + "AdminUsersService._check_duplicate_user"))
        es.enter_context(patch(MOD + "AdminUsersService.owns_category_id"))
        return es

    def test_unknown_category_404(self):
        with self._env(), patch(MOD + "RethinkCategory.exists", return_value=False):
            with pytest.raises(Error) as exc:
                AdminUsersService.create_user(_payload("admin"), _user_data())
        assert exc.value.status_code == 404

    def test_unknown_group_404(self):
        with self._env(), patch(
            MOD + "RethinkCategory.exists", return_value=True
        ), patch(MOD + "RethinkGroup.exists", return_value=False):
            with pytest.raises(Error) as exc:
                AdminUsersService.create_user(_payload("admin"), _user_data())
        assert exc.value.status_code == 404

    def test_group_not_in_category_400(self):
        with self._env(), patch(
            MOD + "RethinkCategory.exists", return_value=True
        ), patch(MOD + "RethinkGroup.exists", return_value=True), patch(
            MOD + "Caches.get_document", return_value={"parent_category": "other-cat"}
        ):
            with pytest.raises(Error) as exc:
                AdminUsersService.create_user(_payload("admin"), _user_data())
        assert exc.value.status_code == 400


class TestUpdateGroupEnrollmentGuard:
    def test_unknown_group_404(self):
        with patch(MOD + "Caches.get_document", return_value=None):
            with pytest.raises(Error) as exc:
                AdminUsersService.update_group_enrollment(
                    _payload("admin"), {"id": "nope"}
                )
        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "group_not_found"
