# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``users`` branches of ``AdminAllowedsService.get_table_term``.

The webapp user pickers label each user ``Name [uid] (Category)``, so
every branch must match the term against the uid as well as the name,
and return ``category_name`` for admins and managers alike.
"""

from unittest.mock import patch

import pytest
from api.services.admin.alloweds import AdminAllowedsService

ADMIN = {"user_id": "u-admin", "category_id": "default", "role_id": "admin"}
MANAGER = {"user_id": "u-mgr", "category_id": "cat-a", "role_id": "manager"}


@pytest.mark.parametrize(
    "payload, data",
    [
        (ADMIN, {"term": "jdoe"}),
        (ADMIN, {"term": "jdoe", "category": "cat-a"}),
        (ADMIN, {"term": "jdoe", "exclude_role": "user"}),
        (MANAGER, {"term": "jdoe"}),
        (MANAGER, {"term": "jdoe", "exclude_role": "user"}),
    ],
    ids=[
        "admin",
        "admin-category",
        "admin-exclude-role",
        "manager",
        "manager-exclude-role",
    ],
)
@patch("api.services.admin.alloweds.Alloweds.get_table_term")
def test_users_term_matches_name_or_uid_and_returns_category_name(
    mock_term, payload, data
):
    AdminAllowedsService.get_table_term("users", data, payload)
    args, kwargs = mock_term.call_args
    assert args == ("users", ["name", "uid"], "jdoe")
    assert {"uid", "category_name"} <= set(kwargs["pluck"])


@patch("api.services.admin.alloweds.Alloweds.get_table_term")
def test_manager_users_term_stays_in_own_category(mock_term):
    AdminAllowedsService.get_table_term("users", {"term": "jdoe"}, MANAGER)
    kwargs = mock_term.call_args.kwargs
    assert kwargs["index_key"] == "category"
    assert kwargs["index_value"] == "cat-a"
