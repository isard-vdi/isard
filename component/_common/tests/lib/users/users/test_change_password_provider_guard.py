#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Only a local user gets a password from ``change_password``."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users import user as mod

UP = mod.UsersProcessed

POLICY = {"old_passwords": 2}


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Run:
    def __init__(self, value=None, on_run=None):
        self.value = value
        self.on_run = on_run

    def run(self, conn):
        if self.on_run:
            self.on_run()
        return self.value


class _UsersTable:
    def __init__(self, users):
        self.users = users
        self.writes = {}

    def get(self, user_id):
        row = MagicMock(name=f"get({user_id})")
        row.default.return_value = _Run(self.users.get(user_id))
        row.update.side_effect = lambda doc: _Run(
            on_run=lambda: self.writes.setdefault(user_id, doc)
        )
        return row

    def get_all(self, ids):
        rows = MagicMock(name="get_all")
        rows.pluck.return_value = _Run(
            [
                {"id": uid, "group": None, "uid": uid, "email": None, **self.users[uid]}
                for uid in ids
            ]
        )
        rows.update.return_value = _Run()
        return rows


def _user(provider):
    return {
        "category": "default",
        "role": "user",
        "provider": provider,
        "password_history": [],
    }


@pytest.fixture
def users(monkeypatch):
    table = _UsersTable(
        {
            "local-1": _user("local"),
            "local-2": _user("local"),
            "saml-1": _user("saml"),
            "google-1": _user("google"),
        }
    )
    monkeypatch.setattr(UP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(UP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    monkeypatch.setattr(mod.r, "table", lambda name: table)
    monkeypatch.setattr(mod.r, "args", lambda ids: ids)
    monkeypatch.setattr(
        mod.UserPolicies,
        "get_user_policy",
        staticmethod(
            lambda subtype, category, role, provider: (
                POLICY if provider == "local" else False
            )
        ),
    )
    monkeypatch.setattr(
        mod.Password, "check_policy", staticmethod(lambda pw, policy, uid: True)
    )
    monkeypatch.setattr(mod.Password, "encrypt", staticmethod(lambda pw: f"h:{pw}"))
    monkeypatch.setattr(mod, "revoke_user_session", lambda user_id: None)
    monkeypatch.setattr(mod.Caches, "invalidate_caches", lambda *a, **k: None)
    monkeypatch.setattr(
        mod.UserStorage, "isard_user_storage_update_user", lambda **k: None
    )
    return table


@pytest.mark.parametrize("user_id", ["saml-1", "google-1"])
def test_a_user_that_is_not_local_is_refused_and_keeps_no_password(users, user_id):
    with pytest.raises(Error) as exc:
        UP.change_password("Secret123", user_id)

    assert exc.value.error["description_code"] == "user_not_local"
    assert user_id not in users.writes


def test_a_local_user_gets_the_password_and_its_history(users):
    UP.change_password("Secret123", "local-1")

    assert users.writes["local-1"]["password"] == "h:Secret123"
    assert users.writes["local-1"]["password_history"] == ["h:Secret123"]


def test_a_bulk_update_sets_the_local_users_and_skips_the_others(users):
    UP.update_multiple_users(
        ["local-1", "saml-1", "local-2", "google-1"], {"password": "Secret123"}
    )

    assert sorted(users.writes) == ["local-1", "local-2"]
    assert all(w["password"] == "h:Secret123" for w in users.writes.values())
