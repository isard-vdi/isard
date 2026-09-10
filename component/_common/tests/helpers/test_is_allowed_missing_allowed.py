#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for ``Alloweds.is_allowed`` with a missing/partial
``allowed`` field.

A template or media document migrated before the alloweds mechanism may
have no ``allowed`` key at all. Previously ``is_allowed`` did
``item["allowed"]["roles"]`` unconditionally, raising
``KeyError: 'allowed'`` — which surfaced as HTTP 500 on
``GET /item/template/{id}/get-info`` and ``/get-details`` for templates
without ``allowed`` (tracked as R12 in the Moodle plugin apiv4
migration). It must instead treat a missing axis as "not shared via that
axis", while the owner/admin/manager fast-paths keep working.
"""

from isardvdi_common.helpers.alloweds import Alloweds


def _payload(role_id="advanced", user_id="u-1", category_id="cat-1", group_id="g-1"):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": category_id,
        "group_id": group_id,
    }


def test_missing_allowed_non_owner_denied_not_crashing():
    # No ``allowed`` key; user is not owner/admin/manager -> denied, no KeyError.
    item = {"id": "t-1", "user": "someone-else", "category": "other-cat"}
    assert Alloweds.is_allowed(_payload(), item, "domains") is False


def test_missing_allowed_owner_still_allowed():
    item = {"id": "t-1", "user": "u-1", "category": "other-cat"}
    assert Alloweds.is_allowed(_payload(user_id="u-1"), item, "domains") is True


def test_missing_allowed_admin_still_allowed():
    item = {"id": "t-1", "user": "someone-else", "category": "other-cat"}
    assert Alloweds.is_allowed(_payload(role_id="admin"), item, "domains") is True


def test_missing_allowed_manager_same_category_still_allowed():
    item = {"id": "t-1", "user": "x", "category": "cat-1"}
    assert (
        Alloweds.is_allowed(
            _payload(role_id="manager", category_id="cat-1"), item, "domains"
        )
        is True
    )


def test_partial_allowed_missing_axes_no_crash():
    # ``allowed`` present but missing categories/groups/users axes.
    item = {"id": "t-1", "user": "x", "category": "other", "allowed": {"roles": False}}
    assert Alloweds.is_allowed(_payload(), item, "domains") is False


def test_wellformed_allowed_role_match_still_works():
    item = {
        "id": "t-1",
        "user": "x",
        "category": "other",
        "allowed": {
            "roles": ["advanced"],
            "categories": False,
            "groups": False,
            "users": False,
        },
    }
    assert Alloweds.is_allowed(_payload(role_id="advanced"), item, "domains") is True


def test_wellformed_allowed_user_match_still_works():
    item = {
        "id": "t-1",
        "user": "x",
        "category": "other",
        "allowed": {
            "roles": False,
            "categories": False,
            "groups": False,
            "users": ["u-1"],
        },
    }
    assert Alloweds.is_allowed(_payload(user_id="u-1"), item, "domains") is True


def test_wellformed_allowed_empty_roles_allows_all():
    item = {
        "id": "t-1",
        "user": "x",
        "category": "other",
        "allowed": {"roles": [], "categories": False, "groups": False, "users": False},
    }
    assert Alloweds.is_allowed(_payload(), item, "domains") is True


def test_no_user_id_denied():
    item = {
        "id": "t-1",
        "allowed": {"roles": [], "categories": False, "groups": False, "users": False},
    }
    assert Alloweds.is_allowed({"role_id": "advanced"}, item, "domains") is False
