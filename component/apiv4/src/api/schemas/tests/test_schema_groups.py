# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/groups.py``."""

import pytest
from api.schemas.groups import GroupUsersResponse
from pydantic import ValidationError


class TestGroupUsersResponse:
    def test_users_required(self):
        with pytest.raises(ValidationError):
            GroupUsersResponse()

    def test_accepts_empty(self):
        assert GroupUsersResponse(users=[]).users == []

    def test_accepts_available_user_list(self):
        from api.schemas.allowed import AvailableUser

        u = AvailableUser(id="u-1", username="u", name="User", role="user")
        r = GroupUsersResponse(users=[u])
        assert r.users[0].id == "u-1"
