#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Helpers.owns_user_id``.

A manager owns a user only when their categories match and the target
is not an admin.
"""

import pytest


@pytest.fixture
def patched_caches(monkeypatch):
    from isardvdi_common.helpers import helpers as mod

    captured = {}

    def fake_get_document(table, item_id, fields=None):
        captured.setdefault("calls", []).append((table, item_id, fields))
        return captured.get("return")

    monkeypatch.setattr(mod.Caches, "get_document", staticmethod(fake_get_document))
    return {"mod": mod, "captured": captured}


def test_manager_owns_user_in_same_category(patched_caches):
    """Manager whose payload.category_id matches the target user's
    category (and the target is not an admin) is allowed."""
    patched_caches["captured"]["return"] = {"category": "cat-a", "role": "user"}
    payload = {"role_id": "manager", "category_id": "cat-a"}

    assert patched_caches["mod"].Helpers.owns_user_id(payload, "user-x") is True
    assert patched_caches["captured"]["calls"] == [
        ("users", "user-x", ["category", "role"])
    ]


def test_manager_does_not_own_admin_in_same_category(patched_caches):
    """A manager never owns an admin, even within their own category."""
    from isardvdi_common.helpers.error_base import ErrorBase as Error

    patched_caches["captured"]["return"] = {"category": "cat-a", "role": "admin"}
    payload = {"role_id": "manager", "category_id": "cat-a"}

    with pytest.raises(Error):
        patched_caches["mod"].Helpers.owns_user_id(payload, "user-x")


def test_manager_owns_user_in_other_category_raises(patched_caches):
    """Manager whose payload.category_id does NOT match raises Error."""
    # Use ErrorBase to dodge the snapshot-bind race in error_factory.Error.
    from isardvdi_common.helpers.error_base import ErrorBase as Error

    patched_caches["captured"]["return"] = {"category": "cat-other", "role": "user"}
    payload = {"role_id": "manager", "category_id": "cat-a"}

    with pytest.raises(Error):
        patched_caches["mod"].Helpers.owns_user_id(payload, "user-x")


def test_admin_short_circuits_without_cache_call(patched_caches):
    """Admin role bypasses the cache entirely."""
    patched_caches["captured"]["return"] = {"category": "cat-other", "role": "user"}
    payload = {"role_id": "admin", "category_id": "cat-a"}

    assert patched_caches["mod"].Helpers.owns_user_id(payload, "user-x") is True


def test_manager_owns_user_when_cache_returns_none_raises(patched_caches):
    """If the cache returns None (missing user), access is not granted."""
    # Use ErrorBase to dodge the snapshot-bind race in error_factory.Error.
    from isardvdi_common.helpers.error_base import ErrorBase as Error

    patched_caches["captured"]["return"] = None
    payload = {"role_id": "manager", "category_id": "cat-a"}

    with pytest.raises(Error):
        patched_caches["mod"].Helpers.owns_user_id(payload, "user-x")
