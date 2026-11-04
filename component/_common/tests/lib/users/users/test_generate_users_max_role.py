# SPDX-License-Identifier: AGPL-3.0-or-later

"""The CSV + bulk producer (``generate_users``) must honour the per-provider
``max_role`` cap: a batch that would create a user above the local provider's
``max_role`` for the category is rejected before any write.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users import user as mod

UP = mod.UsersProcessed


def _row(username, role):
    return {
        "username": username,
        "name": username,
        "role": role,
        "password": "pw",
        "email": f"{username}@e.org",
        "category_id": "c1",
        "group_id": "g1",
    }


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(
        UP, "bulk_user_check", classmethod(lambda cls, payload, user, kind: user)
    )
    monkeypatch.setattr(mod, "notify_admin", lambda *a, **k: None)
    monkeypatch.setattr(mod.Password, "encrypt", staticmethod(lambda p: p))
    spy = MagicMock(name="bulk_create")
    monkeypatch.setattr(UP, "bulk_create", classmethod(lambda cls, users: spy(users)))
    # Category c1 caps the local provider at 'advanced'.
    # get_document("categories", id, ["authentication"]) returns the auth dict.
    monkeypatch.setattr(
        mod.Caches,
        "get_document",
        classmethod(lambda cls, *a, **k: {"local": {"max_role": "advanced"}}),
    )
    return spy


def test_batch_with_role_above_cap_rejected_before_write(harness):
    spy = harness
    payload = {"user_id": "mgr", "role_id": "manager", "category_id": "c1"}
    data = {"users": [_row("u1", "user"), _row("u2", "manager")]}  # manager > advanced
    with pytest.raises(Error) as exc:
        UP.generate_users(payload, data)
    assert exc.value.status_code == 403
    spy.assert_not_called()


def test_batch_within_cap_is_written(harness):
    spy = harness
    payload = {"user_id": "mgr", "role_id": "manager", "category_id": "c1"}
    data = {"users": [_row("u1", "user"), _row("u2", "advanced")]}
    UP.generate_users(payload, data)
    spy.assert_called_once()
