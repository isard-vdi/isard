#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Destructive path: ``UserStorage.isard_user_storage_provider_delete``.

Deleting a storage provider first resets it (unenrolling its users/groups)
and then deletes the provider row. Two things must hold and are pinned here:

* the delete targets exactly the ``user_storage`` row keyed by
  ``provider_id`` — nothing else (L560);
* the reset step is best-effort: its ``except`` is deliberately mute, so a
  reset failure must NOT stop the provider row from being deleted (L557).

``isard_user_storage_provider_delete`` runs unmocked; only the reset
collaborator and the rethink layer are stubbed, so the delete target is
decided by the real code.
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
    """Stub rethink; ``tbl`` maps table -> its ``r.table`` mock."""
    monkeypatch.setattr(US, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(US), "_rdb_connection", property(lambda self: MagicMock(name="conn"))
    )
    tbl = {}

    def table(name):
        return tbl.setdefault(name, MagicMock(name=f"r.table({name})"))

    monkeypatch.setattr(mod.r, "table", table)
    return tbl


class TestProviderDeleteDestructive:
    def test_deletes_only_the_provider_row_by_id(self, rdb, monkeypatch):
        reset = MagicMock(name="reset")
        monkeypatch.setattr(
            US,
            "isard_user_storage_provider_reset",
            classmethod(lambda cls, pid: reset(pid)),
        )

        US.isard_user_storage_provider_delete("prov-42")

        reset.assert_called_once_with("prov-42")
        us_tbl = rdb["user_storage"]
        us_tbl.get.assert_called_once_with("prov-42")
        us_tbl.get.return_value.delete.assert_called_once_with()
        # nothing else was deleted: no other table was touched at all
        assert set(rdb) == {"user_storage"}

    def test_reset_failure_does_not_stop_the_delete(self, rdb, monkeypatch):
        def _boom(cls, pid):
            raise RuntimeError("reset failed")

        monkeypatch.setattr(US, "isard_user_storage_provider_reset", classmethod(_boom))

        # the mute except swallows the reset failure and the row is still deleted
        US.isard_user_storage_provider_delete("prov-7")

        rdb["user_storage"].get.assert_called_once_with("prov-7")
        rdb["user_storage"].get.return_value.delete.assert_called_once_with()
