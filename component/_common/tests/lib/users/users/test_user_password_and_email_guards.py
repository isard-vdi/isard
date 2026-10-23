#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``verify_password`` and ``get_user_by_email_and_category``.

* verify_password: a wrong password is rejected (L1868) wrong_password_entered.
* get_user_by_email_and_category: only local users with a verified email
  match; zero matches -> not_found (user_not_found), more than one -> conflict
  (user_email_conflict), exactly one -> the id.

Both run unmocked; only rethink (and ``Password.valid``) are stubbed, so the
accept/reject decision is the real code.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.users.users import user as mod

UP = mod.UsersProcessed


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rdb(monkeypatch):
    monkeypatch.setattr(UP, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(UP), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = MagicMock(name="r.table(users)")
    monkeypatch.setattr(mod.r, "table", lambda name: tbl)
    return tbl


class TestVerifyPassword:
    def test_wrong_password_rejected(self, rdb, monkeypatch):
        rdb.get.return_value.__getitem__.return_value.run.return_value = "hash"
        monkeypatch.setattr(
            mod.Password, "valid", staticmethod(lambda pw, stored: False)
        )
        with pytest.raises(Error) as exc:
            UP.verify_password("u-1", "nope")
        assert exc.value.error["description_code"] == "wrong_password_entered"

    def test_correct_password_returns_true(self, rdb, monkeypatch):
        rdb.get.return_value.__getitem__.return_value.run.return_value = "hash"
        monkeypatch.setattr(
            mod.Password, "valid", staticmethod(lambda pw, stored: True)
        )
        assert UP.verify_password("u-1", "right") is True


class TestGetUserByEmailAndCategory:
    def _set_users(self, rdb, ids):
        # chain: get_all(...).filter(...).pluck("id")["id"].run(conn)
        rdb.get_all.return_value.filter.return_value.pluck.return_value.__getitem__.return_value.run.return_value = (
            ids
        )

    def test_no_verified_user_not_found(self, rdb):
        self._set_users(rdb, [])
        with pytest.raises(Error) as exc:
            UP.get_user_by_email_and_category("a@b.c", "cat-1")
        assert exc.value.error["description_code"] == "user_not_found"

    def test_multiple_verified_users_conflict(self, rdb):
        self._set_users(rdb, ["u-1", "u-2"])
        with pytest.raises(Error) as exc:
            UP.get_user_by_email_and_category("a@b.c", "cat-1")
        assert exc.value.error["description_code"] == "user_email_conflict"

    def test_single_user_returned(self, rdb):
        self._set_users(rdb, ["u-1"])
        assert UP.get_user_by_email_and_category("a@b.c", "cat-1") == "u-1"


class _Field:
    def __init__(self, value):
        self.value = value

    def eq(self, other):
        # ReQL never equates booleans and numbers
        return type(self.value) is type(other) and self.value == other

    def gt(self, other):
        # ReQL sorts booleans and null below numbers and times above them
        if isinstance(self.value, datetime):
            return True
        return type(self.value) in (int, float) and self.value > other


class _Row(dict):
    def __getitem__(self, key):
        return _Field(self.get(key))


class TestGetUserByEmailAndCategoryFilter:
    @pytest.mark.parametrize(
        "row, matches",
        [
            ({"provider": "local", "email_verified": datetime.now()}, True),
            ({"provider": "local", "email_verified": 1700000000}, True),
            ({"provider": "local", "email_verified": True}, True),
            ({"provider": "local", "email_verified": False}, False),
            ({"provider": "local", "email_verified": 0}, False),
            ({"provider": "local", "email_verified": None}, False),
            ({"provider": "local"}, False),
            ({"provider": "ldap", "email_verified": datetime.now()}, False),
        ],
    )
    def test_only_local_users_with_a_verified_email(self, rdb, row, matches):
        rdb.get_all.return_value.filter.return_value.pluck.return_value.__getitem__.return_value.run.return_value = [
            "u-1"
        ]
        UP.get_user_by_email_and_category("a@b.c", "cat-1")
        predicate = rdb.get_all.return_value.filter.call_args.args[0]
        assert bool(predicate(_Row(row, email="a@b.c"))) is matches
