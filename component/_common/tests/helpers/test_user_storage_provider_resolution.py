#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``UserStorage._get_provider`` has to reach the provider, not be starved by
the admin getter that hides its password.

Pinned here: the resolver answers with a connection for an enabled, authorised
provider, still refuses a disabled or unauthorised one, and the admin getter it
no longer depends on keeps stripping the secret.

The methods run unmocked; only the rethink layer and the Nextcloud client are
stubbed.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import user_storage as mod

US = mod.UserStorage

_ROW = {
    "id": "p-1",
    "provider": "nextcloud",
    "enabled": True,
    "password": "s3cret",
    "user": "admin",
    "url": "cloud.example",
    "urlprefix": "/nc",
    "verify_cert": True,
    "intra_docker": False,
    "auth_protocol": "basic",
}


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def rdb(monkeypatch):
    monkeypatch.setattr(US, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(US), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    table = MagicMock(name="r.table(user_storage)")
    monkeypatch.setattr(mod.r, "table", lambda name: table)
    monkeypatch.setattr(mod, "NextcloudApi", MagicMock(name="NextcloudApi"))
    mod.cache_provider.clear()
    yield table
    mod.cache_provider.clear()


def _row(rdb, value):
    rdb.get.return_value.run.return_value = value


class TestTheResolverReachesTheProvider:
    def test_an_enabled_authorised_provider_resolves(self, rdb):
        _row(rdb, dict(_ROW))
        resolved = US._get_provider("p-1")
        assert resolved is not None
        assert resolved["cfg"]["id"] == "p-1"
        resolved["conn"].set_basic_auth.assert_called_once_with("admin", "s3cret")

    def test_the_password_survives_the_read_the_resolver_makes(self, rdb):
        _row(rdb, dict(_ROW))
        assert US._get_provider_row("p-1")["password"] == "s3cret"

    def test_a_disabled_provider_still_resolves_to_nothing(self, rdb):
        _row(rdb, dict(_ROW, enabled=False))
        assert US._get_provider("p-1") is None

    def test_a_provider_with_no_password_still_resolves_to_nothing(self, rdb):
        row = dict(_ROW)
        row.pop("password")
        _row(rdb, row)
        assert US._get_provider("p-1") is None

    def test_a_missing_provider_resolves_to_nothing(self, rdb):
        _row(rdb, None)
        assert US._get_provider("p-1") is None

    def test_a_falsy_provider_id_never_reaches_the_database(self, rdb):
        assert US._get_provider_row(None) is None
        assert US._get_provider_row("") is None
        rdb.get.assert_not_called()

    def test_a_rethink_failure_resolves_to_nothing(self, rdb):
        rdb.get.return_value.run.side_effect = RuntimeError("db down")
        assert US._get_provider_row("p-1") is None


class TestTheAdminGetterKeepsHidingTheSecret:
    def test_the_admin_getter_still_strips_the_password(self, rdb):
        _row(rdb, dict(_ROW))
        served = US.isard_user_storage_get_provider("p-1")
        assert "password" not in served
        assert served["authorization"] is True
