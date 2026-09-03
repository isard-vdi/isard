#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards on ``UserStorage.isard_user_storage_get_provider``.

Reads one provider row and returns it with the password stripped and an
``authorization`` boolean derived from whether a password was set. Pinned:

* a falsy ``provider_id`` short-circuits to ``None`` (L423) — no DB hit;
* a row with a password -> ``authorization=True`` and password removed (L431);
* a row without a password -> ``authorization=False`` (L431);
* any rethink failure is swallowed -> ``None`` (L434, mute except).

The method runs unmocked; only the rethink layer is stubbed.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import user_storage as mod

US = mod.UserStorage


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
    return table


def _run(rdb):
    """Shortcut to the terminal ``.get(id).run(conn)`` return value."""
    return rdb.get.return_value.run


class TestGetProviderGuards:
    def test_falsy_provider_id_returns_none_without_db(self, rdb):
        assert US.isard_user_storage_get_provider(None) is None
        assert US.isard_user_storage_get_provider("") is None
        rdb.get.assert_not_called()

    def test_password_present_sets_authorization_and_strips_password(self, rdb):
        _run(rdb).return_value = {"id": "p-1", "password": "s3cret", "user": "admin"}
        result = US.isard_user_storage_get_provider("p-1")
        assert result["authorization"] is True
        assert "password" not in result

    def test_password_absent_sets_authorization_false(self, rdb):
        _run(rdb).return_value = {"id": "p-1", "user": "admin"}
        result = US.isard_user_storage_get_provider("p-1")
        assert result["authorization"] is False

    def test_rethink_failure_is_swallowed_to_none(self, rdb):
        _run(rdb).side_effect = RuntimeError("db down")
        assert US.isard_user_storage_get_provider("p-1") is None
