# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/users.py``.

Locks the response shapes that ``GET /item/user/get-details`` and
``GET /item/user`` serialize. Older user documents in the wild lack
the optional ``photo`` field entirely (the DB stores nothing instead
of an empty string), and ``Caches.get_cached_user_with_names`` returns
the raw doc verbatim. After an admin impersonates such a user, every
subsequent profile fetch must still validate cleanly — otherwise the
JWT cookie wedges the session and the only recovery is wiping cookies
in the browser.
"""

from api.schemas.users import UserDetailsResponse, UserResponse

_BASE_DETAILS = {
    "id": "u-1",
    "username": "manager02",
    "name": "Manager Hidden",
    "email": "",
    "provider": "local",
    "category": "cat-1",
    "category_name": "Default",
    "group": "grp-1",
    "group_name": "Default",
    "role": "manager",
    "role_name": "Manager",
    "secondary_groups_data": [],
}


def test_user_details_response_defaults_photo_when_missing():
    """Reproduces the impersonation crash: the source dict has no ``photo`` key.

    ``Caches.get_cached_user_with_names`` returns the user document as-is from
    RethinkDB; legacy / system users (manager02, password_reset, unverified, …)
    were created without a ``photo`` field. The response model must default
    instead of 500-ing on validation.
    """
    resp = UserDetailsResponse(**_BASE_DETAILS)
    assert resp.photo == ""


def test_user_details_response_accepts_explicit_photo():
    resp = UserDetailsResponse(**{**_BASE_DETAILS, "photo": "https://x/y.png"})
    assert resp.photo == "https://x/y.png"


def test_user_response_defaults_photo_when_missing():
    """Mirror of the above for the lighter ``GET /item/user`` payload."""
    resp = UserResponse(
        name="Manager Hidden",
        email="",
        role="manager",
        role_name="Manager",
        items_in_bin=0,
    )
    assert resp.photo == ""
