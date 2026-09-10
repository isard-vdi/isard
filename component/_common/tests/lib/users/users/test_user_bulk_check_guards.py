#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``UsersProcessed.bulk_user_check`` — the bulk-create wall.

Before a bulk/generated user is accepted it is rejected for:

* an unsupported item_type (L420) item_type_not_allowed;
* a username that already exists in the category (L438) user_already_exists;
* a role the requester may not assign — a manager cannot create an admin
  (L446), and any role outside the valid set (L454) role_not_allowed.

``bulk_user_check`` runs unmocked; the name/category matcher, the ownership
check and the existing-user lookup are stubbed, so each reject is the real
code.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users import user as mod

UP = mod.UsersProcessed


def _user(role="user"):
    return {
        "username": "bob",
        "category": "Cat",
        "group": "Grp",
        "role": role,
        "password": "x",
    }


@pytest.fixture
def env(monkeypatch):
    state = {"existing": None}
    monkeypatch.setattr(
        mod.Helpers,
        "category_name_group_name_match",
        classmethod(lambda cls, c, g: {"category_id": "c-1", "group_id": "g-1"}),
    )
    monkeypatch.setattr(
        mod.Helpers, "owns_category_id", classmethod(lambda cls, payload, cid: None)
    )
    monkeypatch.setattr(
        UP,
        "get_by_provider_category_uid",
        classmethod(lambda cls, provider, cid, uid: state["existing"]),
    )
    return state


class TestBulkUserCheckGuards:
    def test_item_type_not_allowed(self, env):
        with pytest.raises(Error) as exc:
            UP.bulk_user_check({"role_id": "admin"}, _user(), "xml")
        assert exc.value.error["description_code"] == "item_type_not_allowed"

    def test_user_already_exists(self, env):
        env["existing"] = "u-existing"
        with pytest.raises(Error) as exc:
            UP.bulk_user_check({"role_id": "admin"}, _user(), "generate")
        assert exc.value.error["description_code"] == "user_already_exists"

    def test_manager_cannot_create_admin(self, env):
        with pytest.raises(Error) as exc:
            UP.bulk_user_check({"role_id": "manager"}, _user(role="admin"), "generate")
        assert exc.value.error["description_code"] == "role_not_allowed"

    def test_invalid_role_rejected(self, env):
        with pytest.raises(Error) as exc:
            UP.bulk_user_check(
                {"role_id": "admin"}, _user(role="superuser"), "generate"
            )
        assert exc.value.error["description_code"] == "role_not_allowed"
