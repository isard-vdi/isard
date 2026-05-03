#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UsersProcessed.check_password_expiration``.

Reproducer + regression cover for bug 54: when a user record has
``role=None`` or ``category=None`` (left in that state by a destructive
admin operation, e.g. a stale auth-policy force_validate that wiped the
field), the route ``/admin/user/required/password-reset/{user_id}`` must
NOT 500 — it returns False (no expiration check possible).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.users.users import user as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.UsersProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.UsersProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.UsersProcessed, "mod": mod}


class TestCheckPasswordExpiration:
    def test_returns_false_when_provider_is_not_local(self, stub_rdb):
        # SAML/OIDC users have no local password to expire.
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.pluck.return_value.run.return_value = {
            "category": "default",
            "role": "user",
            "provider": "saml",
            "password_last_updated": 0,
        }
        assert stub_rdb["Processed"].check_password_expiration("u-1") is False

    def test_returns_false_when_role_is_none(self, stub_rdb, monkeypatch):
        # Bug 54 reproducer: corrupted user with role=None must not 500.
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.pluck.return_value.run.return_value = {
            "category": "default",
            "role": None,
            "provider": "local",
            "password_last_updated": 0,
        }

        # If the defensive guard fails, we'd reach get_user_policy which
        # raises Error("internal_server", "Category and role must be
        # provided..."). Patching it to fail loudly catches a regression.
        def _explode(*_a, **_k):
            raise AssertionError("get_user_policy must not be called when role is None")

        monkeypatch.setattr(
            stub_rdb["mod"].UserPolicies, "get_user_policy", classmethod(_explode)
        )
        assert stub_rdb["Processed"].check_password_expiration("u-1") is False

    def test_returns_false_when_category_is_none(self, stub_rdb, monkeypatch):
        # Same bug 54 shape but missing the category half.
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.pluck.return_value.run.return_value = {
            "category": None,
            "role": "user",
            "provider": "local",
            "password_last_updated": 0,
        }

        def _explode(*_a, **_k):
            raise AssertionError(
                "get_user_policy must not be called when category is None"
            )

        monkeypatch.setattr(
            stub_rdb["mod"].UserPolicies, "get_user_policy", classmethod(_explode)
        )
        assert stub_rdb["Processed"].check_password_expiration("u-1") is False

    def test_returns_false_when_no_policy_matches(self, stub_rdb, monkeypatch):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.pluck.return_value.run.return_value = {
            "category": "default",
            "role": "user",
            "provider": "local",
            "password_last_updated": 0,
        }
        monkeypatch.setattr(
            stub_rdb["mod"].UserPolicies,
            "get_user_policy",
            classmethod(lambda cls, *a, **k: None),
        )
        assert stub_rdb["Processed"].check_password_expiration("u-1") is False
