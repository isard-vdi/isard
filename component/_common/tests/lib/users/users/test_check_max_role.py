# SPDX-License-Identifier: AGPL-3.0-or-later

"""``UsersProcessed.check_max_role``: the per-provider role cap on user writes.

A category's authentication config may pin ``authentication.<provider>.max_role``
(user|advanced|manager|admin). Any user write whose resulting role would exceed
that cap for the user's provider is rejected — for admins and managers alike,
it caps the result, not who does it. Absent/empty max_role means no cap (today's
behaviour). Only ``Caches.get_document`` is stubbed; the real comparison runs.
"""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users import user as mod

UP = mod.UsersProcessed


def _cat_with(provider, max_role):
    # get_document("categories", id, ["authentication"]) returns the
    # authentication dict directly (provider -> config), not {auth: ...}.
    auth = {provider: {"disabled": False}}
    if max_role is not None:
        auth[provider]["max_role"] = max_role
    return auth


@pytest.fixture
def cat(monkeypatch):
    state = {"doc": {}}
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, *a, **k: state["doc"])
    )
    return state


def test_no_max_role_allows_anything(cat):
    cat["doc"] = _cat_with("local", None)
    assert UP.check_max_role("c1", "local", "admin") in (None, False)


def test_empty_max_role_allows_anything(cat):
    cat["doc"] = _cat_with("local", "")
    assert UP.check_max_role("c1", "local", "manager") in (None, False)


def test_role_above_cap_is_rejected(cat):
    cat["doc"] = _cat_with("local", "advanced")
    with pytest.raises(Error) as exc:
        UP.check_max_role("c1", "local", "manager")
    assert exc.value.status_code == 403
    assert exc.value.error["description_code"] == "role_above_provider_max_role"


def test_role_at_cap_is_allowed(cat):
    cat["doc"] = _cat_with("saml", "manager")
    assert UP.check_max_role("c1", "saml", "manager") in (None, False)


def test_role_below_cap_is_allowed(cat):
    cat["doc"] = _cat_with("local", "manager")
    assert UP.check_max_role("c1", "local", "user") in (None, False)


def test_cap_is_per_provider(cat):
    # saml capped at manager, but the write is for the local provider (uncapped).
    cat["doc"] = {"saml": {"max_role": "manager"}}
    assert UP.check_max_role("c1", "local", "admin") in (None, False)


def test_admin_over_manager_cap_rejected(cat):
    cat["doc"] = _cat_with("saml", "manager")
    with pytest.raises(Error) as exc:
        UP.check_max_role("c1", "saml", "admin")
    assert exc.value.status_code == 403
