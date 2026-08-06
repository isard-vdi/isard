#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on the user-quota sync paths of ``UserStorage``.

``user_storage_update_user_quota`` reads the provider quota and writes it to
the user row, with a subtle error split (L1810-1817): a *not-found* from the
provider means "user not enrolled yet" and is swallowed, but any other error
must propagate — swallowing it would hide a real provider outage. If that
split breaks, "does not exist" gets treated as "failed" (or vice versa).

``user_storage_quota_update`` is the simpler sibling: no provider quota, no
write (L1829).

Both run unmocked; the provider lookup / connection and the rethink write
are stubbed. ``ErrorBase`` is the class the module's ``Error`` resolves to.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import user_storage as mod
from isardvdi_common.helpers.error_base import ErrorBase

US = mod.UserStorage


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _provider(quota=None, error=None):
    conn = MagicMock(name="conn")
    if error is not None:
        conn.get_user_quota.side_effect = error
    else:
        conn.get_user_quota.return_value = quota
    return {"conn": conn}


@pytest.fixture
def rdb(monkeypatch):
    """Stub rethink; return the ``users`` table mock to assert writes."""
    monkeypatch.setattr(US, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(US), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    users = MagicMock(name="r.table(users)")
    monkeypatch.setattr(mod.r, "table", lambda name: {"users": users}[name])
    monkeypatch.setattr(
        US, "_get_isard_user_provider_id", classmethod(lambda cls, uid: "p-1")
    )
    return users


class TestUpdateUserQuotaGuards:
    def test_no_provider_returns_without_write(self, rdb, monkeypatch):
        monkeypatch.setattr(US, "_get_provider", classmethod(lambda cls, pid: None))
        assert US.user_storage_update_user_quota("u-1") is None
        rdb.get.assert_not_called()

    def test_not_found_error_by_status_code_is_swallowed(self, rdb, monkeypatch):
        # ErrorBase("not_found") carries status_code 404 -> user not enrolled
        # yet -> swallow, no write.
        monkeypatch.setattr(
            US,
            "_get_provider",
            classmethod(lambda cls, pid: _provider(error=ErrorBase("not_found"))),
        )
        assert US.user_storage_update_user_quota("u-1") is None
        rdb.get.assert_not_called()

    def test_not_found_by_args_is_swallowed(self, rdb, monkeypatch):
        monkeypatch.setattr(
            US,
            "_get_provider",
            classmethod(lambda cls, pid: _provider(error=Exception("not_found"))),
        )
        assert US.user_storage_update_user_quota("u-1") is None
        rdb.get.assert_not_called()

    def test_other_error_object_propagates(self, rdb, monkeypatch):
        # A non-404 provider error must NOT be swallowed.
        monkeypatch.setattr(
            US,
            "_get_provider",
            classmethod(lambda cls, pid: _provider(error=ErrorBase("internal_server"))),
        )
        with pytest.raises(ErrorBase):
            US.user_storage_update_user_quota("u-1")
        rdb.get.assert_not_called()

    def test_generic_error_propagates(self, rdb, monkeypatch):
        monkeypatch.setattr(
            US,
            "_get_provider",
            classmethod(lambda cls, pid: _provider(error=RuntimeError("boom"))),
        )
        with pytest.raises(RuntimeError):
            US.user_storage_update_user_quota("u-1")

    def test_success_writes_provider_quota(self, rdb, monkeypatch):
        monkeypatch.setattr(
            US,
            "_get_provider",
            classmethod(lambda cls, pid: _provider(quota={"maxfiles": 9})),
        )
        US.user_storage_update_user_quota("u-1")
        rdb.get.assert_called_once_with("u-1")
        written = rdb.get.return_value.update.call_args.args[0]
        assert written == {"user_storage": {"provider_quota": {"maxfiles": 9}}}


class TestQuotaUpdateGuard:
    def test_no_quota_returns_without_write(self, rdb, monkeypatch):
        monkeypatch.setattr(
            US, "user_storage_quota", classmethod(lambda cls, uid: None)
        )
        assert US.user_storage_quota_update("u-1") is None
        rdb.get.assert_not_called()

    def test_quota_present_writes_and_returns(self, rdb, monkeypatch):
        monkeypatch.setattr(
            US, "user_storage_quota", classmethod(lambda cls, uid: {"maxfiles": 3})
        )
        assert US.user_storage_quota_update("u-1") == {"maxfiles": 3}
        rdb.get.assert_called_once_with("u-1")
        written = rdb.get.return_value.update.call_args.args[0]
        assert written == {"user_storage": {"provider_quota": {"maxfiles": 3}}}
