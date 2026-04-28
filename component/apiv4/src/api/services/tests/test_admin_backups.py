# SPDX-License-Identifier: AGPL-3.0-or-later

"""Service-layer tests for ``AdminBackupsService`` — the bits that
aren't already exercised by ``routes/tests/test_admin_backups.py``:
``_retention``, ``_cleanup_old_backups``, and the integrity toggle
get/set pair. Route tests stub the service; these tests stub the DB.
"""

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from api.services.admin_backups import (
    INTEGRITY_ENABLED_DEFAULT,
    AdminBackupsService,
    _retention,
)
from api.services.error import Error

# ══════════════════════════════════════════════════════════════════════════
#  _retention()
# ══════════════════════════════════════════════════════════════════════════


class TestRetention:
    """``BACKUP_RETENTION`` is opt-in via env. Default 30, clamped to ≥1
    so a misconfigured ``BACKUP_RETENTION=0`` doesn't wipe every record
    on the next insert."""

    def test_default_30_when_unset(self, monkeypatch):
        monkeypatch.delenv("BACKUP_RETENTION", raising=False)
        assert _retention() == 30

    def test_reads_env(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION", "7")
        assert _retention() == 7

    def test_invalid_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION", "not-a-number")
        assert _retention() == 30

    def test_zero_clamped_to_one(self, monkeypatch):
        """``BACKUP_RETENTION=0`` would wipe every record on the next
        insert if not clamped — pin the floor."""
        monkeypatch.setenv("BACKUP_RETENTION", "0")
        assert _retention() == 1

    def test_negative_clamped_to_one(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION", "-5")
        assert _retention() == 1


# ══════════════════════════════════════════════════════════════════════════
#  _cleanup_old_backups()
# ══════════════════════════════════════════════════════════════════════════


def _patch_rdb(monkeypatch, *, count, old_ids, delete_result=None):
    """Stub the RethinkDB chain ``_cleanup_old_backups`` walks.

    Returns the ``delete`` mock so the test can assert call counts /
    that ``get_all`` was passed the right ids.
    """
    monkeypatch.setattr(
        "api.services.admin_backups.RethinkSharedConnection._rdb_context",
        contextlib.nullcontext,
    )
    monkeypatch.setattr(
        "api.services.admin_backups.RethinkSharedConnection._rdb_connection",
        MagicMock(),
    )
    delete_mock = MagicMock(return_value=delete_result or {"deleted": len(old_ids)})
    table = MagicMock()
    table.count.return_value.run.return_value = count
    table.order_by.return_value.skip.return_value.pluck.return_value.run.return_value = [
        {"id": i} for i in old_ids
    ]
    table.get_all.return_value.delete.return_value.run = delete_mock
    monkeypatch.setattr("api.services.admin_backups.r.table", lambda _: table)
    return delete_mock, table


class TestCleanupOldBackups:
    def test_below_retention_no_delete(self, monkeypatch):
        """Nothing to do — total <= keep returns 0 without calling delete."""
        monkeypatch.setenv("BACKUP_RETENTION", "30")
        delete, table = _patch_rdb(monkeypatch, count=10, old_ids=[])
        assert AdminBackupsService._cleanup_old_backups() == 0
        delete.assert_not_called()

    def test_equal_to_retention_no_delete(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION", "5")
        delete, table = _patch_rdb(monkeypatch, count=5, old_ids=[])
        assert AdminBackupsService._cleanup_old_backups() == 0
        delete.assert_not_called()

    def test_above_retention_deletes_skipped_rows(self, monkeypatch):
        """``order_by(desc).skip(keep).pluck("id")`` enumerates the rows
        beyond the keep window — only those ids must be deleted."""
        monkeypatch.setenv("BACKUP_RETENTION", "3")
        delete, table = _patch_rdb(
            monkeypatch, count=8, old_ids=["b6", "b7", "b8", "b9", "b10"]
        )
        AdminBackupsService._cleanup_old_backups()
        delete.assert_called_once()
        # ``get_all`` must receive the same id list (not a slice or
        # re-ordering) — pin so a future refactor that drops .skip()
        # in favor of slicing produces a clear failure.
        table.get_all.assert_called_once_with("b6", "b7", "b8", "b9", "b10")

    def test_returns_count_from_delete(self, monkeypatch):
        monkeypatch.setenv("BACKUP_RETENTION", "2")
        delete, table = _patch_rdb(
            monkeypatch,
            count=5,
            old_ids=["a", "b", "c"],
            delete_result={"deleted": 3},
        )
        assert AdminBackupsService._cleanup_old_backups() == 3


# ══════════════════════════════════════════════════════════════════════════
#  get_integrity_enabled() / set_integrity_enabled()
# ══════════════════════════════════════════════════════════════════════════


def _patch_config_read(monkeypatch, doc):
    monkeypatch.setattr(
        "api.services.admin_backups.RethinkSharedConnection._rdb_context",
        contextlib.nullcontext,
    )
    monkeypatch.setattr(
        "api.services.admin_backups.RethinkSharedConnection._rdb_connection",
        MagicMock(),
    )
    table = MagicMock()
    table.get.return_value.run.return_value = doc
    update_mock = MagicMock(return_value={"replaced": 1})
    table.get.return_value.update.return_value.run = update_mock
    monkeypatch.setattr("api.services.admin_backups.r.table", lambda _: table)
    return table, update_mock


class TestGetIntegrityEnabled:
    def test_default_when_no_config(self, monkeypatch):
        """``config[1]`` row does not exist — return the module default."""
        _patch_config_read(monkeypatch, doc=None)
        assert AdminBackupsService.get_integrity_enabled() == INTEGRITY_ENABLED_DEFAULT

    def test_default_when_no_backups_subdoc(self, monkeypatch):
        """Existing config without a ``backups`` subdoc — still default off."""
        _patch_config_read(monkeypatch, doc={"id": 1})
        assert AdminBackupsService.get_integrity_enabled() == INTEGRITY_ENABLED_DEFAULT

    def test_default_when_subdoc_missing_key(self, monkeypatch):
        _patch_config_read(monkeypatch, doc={"id": 1, "backups": {}})
        assert AdminBackupsService.get_integrity_enabled() == INTEGRITY_ENABLED_DEFAULT

    def test_returns_true_when_enabled(self, monkeypatch):
        _patch_config_read(
            monkeypatch, doc={"id": 1, "backups": {"integrity_enabled": True}}
        )
        assert AdminBackupsService.get_integrity_enabled() is True

    def test_returns_false_when_disabled(self, monkeypatch):
        _patch_config_read(
            monkeypatch, doc={"id": 1, "backups": {"integrity_enabled": False}}
        )
        assert AdminBackupsService.get_integrity_enabled() is False

    def test_coerces_truthy_non_bool(self, monkeypatch):
        """Defensive: a corrupt config row carrying ``1`` instead of
        ``True`` should still come out as a Python ``bool`` so the
        Pydantic response model accepts it."""
        _patch_config_read(
            monkeypatch, doc={"id": 1, "backups": {"integrity_enabled": 1}}
        )
        assert AdminBackupsService.get_integrity_enabled() is True


class TestSetIntegrityEnabled:
    def test_persists_true(self, monkeypatch):
        _, update = _patch_config_read(monkeypatch, doc={"id": 1})
        out = AdminBackupsService.set_integrity_enabled(True)
        assert out == {"integrity_enabled": True}
        update.assert_called_once()

    def test_persists_false(self, monkeypatch):
        _, update = _patch_config_read(monkeypatch, doc={"id": 1})
        out = AdminBackupsService.set_integrity_enabled(False)
        assert out == {"integrity_enabled": False}
        update.assert_called_once()

    def test_rejects_non_bool(self, monkeypatch):
        """Don't ``bool("false")`` — ``"false"`` is truthy and would
        silently enable integrity. Force the caller to pass a real bool."""
        _, update = _patch_config_read(monkeypatch, doc={"id": 1})
        with pytest.raises(Error):
            AdminBackupsService.set_integrity_enabled("true")
        update.assert_not_called()

    def test_rejects_int(self, monkeypatch):
        _, update = _patch_config_read(monkeypatch, doc={"id": 1})
        with pytest.raises(Error):
            AdminBackupsService.set_integrity_enabled(1)
        update.assert_not_called()

    def test_rejects_none(self, monkeypatch):
        _, update = _patch_config_read(monkeypatch, doc={"id": 1})
        with pytest.raises(Error):
            AdminBackupsService.set_integrity_enabled(None)
        update.assert_not_called()
