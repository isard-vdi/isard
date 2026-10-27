# SPDX-License-Identifier: AGPL-3.0-or-later

"""Costly disk repairs: admins always, others only when the allowed list matches them."""

from unittest.mock import patch

import pytest
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.helpers import Helpers

USER = {
    "user_id": "u1",
    "role_id": "user",
    "category_id": "c1",
    "group_id": "g1",
}
ADMIN = {**USER, "user_id": "a1", "role_id": "admin"}
EMPTY = {"roles": False, "categories": False, "groups": False, "users": False}


def _can(payload, allowed, secondary=False):
    with (
        patch.object(Alloweds, "get_storage_repair_allowed_dict", return_value=allowed),
        patch.object(Alloweds, "check_secondary_groups", return_value=secondary),
    ):
        return Helpers.can_repair_storage_costly(payload)


@pytest.mark.parametrize("allowed", [EMPTY, {}])
def test_an_empty_or_missing_list_lets_only_admins(allowed):
    assert _can(ADMIN, allowed) is True
    assert _can(USER, allowed) is False
    assert _can({**USER, "role_id": "manager"}, allowed) is False


@pytest.mark.parametrize(
    "allowed, secondary",
    [
        ({**EMPTY, "roles": ["user"]}, False),
        ({**EMPTY, "categories": ["c1"]}, False),
        ({**EMPTY, "groups": ["g1"]}, True),
        ({**EMPTY, "users": ["u1"]}, False),
    ],
)
def test_a_user_matched_by_role_category_group_or_user_may(allowed, secondary):
    assert _can(USER, allowed, secondary) is True


@pytest.mark.parametrize(
    "allowed",
    [
        {**EMPTY, "roles": ["manager"]},
        {**EMPTY, "categories": ["c2"]},
        {**EMPTY, "users": ["u2"]},
    ],
)
def test_a_user_the_list_does_not_match_may_not(allowed):
    assert _can(USER, allowed) is False


def test_an_unreadable_list_refuses_everyone_but_admins():
    with patch.object(
        Alloweds, "get_storage_repair_allowed_dict", side_effect=RuntimeError("down")
    ):
        assert Helpers.can_repair_storage_costly(USER) is False
        assert Helpers.can_repair_storage_costly(ADMIN) is True
