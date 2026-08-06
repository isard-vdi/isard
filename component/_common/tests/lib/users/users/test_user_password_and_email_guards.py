#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``verify_password`` and ``get_user_by_email_and_category``.

* verify_password: a wrong password is rejected (L1868) wrong_password_entered.
* get_user_by_email_and_category: zero verified matches -> not_found
  (user_not_found), more than one -> conflict (user_email_conflict), exactly
  one -> the id.

Both run unmocked; only rethink (and ``Password.valid``) are stubbed, so the
accept/reject decision is the real code.
"""

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
