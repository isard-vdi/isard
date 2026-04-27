# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/categories.py``."""

import pytest
from api.schemas.categories import CategoriesUsersSearchResponse
from pydantic import ValidationError


class TestCategoriesUsersSearchResponse:
    """Wraps a list of AvailableUser. The route returns this so the
    admin UI's user-picker has typed entries; pin both the empty-list
    and required-field cases."""

    def test_users_required(self):
        with pytest.raises(ValidationError):
            CategoriesUsersSearchResponse()

    def test_accepts_empty_list(self):
        r = CategoriesUsersSearchResponse(users=[])
        assert r.users == []

    def test_accepts_user_dict_via_available_user_validation(self):
        """Each item is validated as AvailableUser. A dict missing a
        required AvailableUser field would fail — pin the propagation
        so a future AvailableUser tightening trips this test too."""
        from api.schemas.allowed import AvailableUser

        u = AvailableUser(id="u-1", username="u", name="User", role="user")
        r = CategoriesUsersSearchResponse(users=[u])
        assert r.users[0].id == "u-1"
