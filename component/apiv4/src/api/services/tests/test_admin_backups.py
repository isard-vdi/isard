# SPDX-License-Identifier: AGPL-3.0-or-later

"""Service-layer tests for ``AdminBackupsService`` — the bits that
aren't already exercised by ``routes/tests/test_admin_backups.py``:
``_retention``, ``_cleanup_old_backups``, and the integrity toggle
get/set pair. Route tests stub the service; these tests stub the DB.
"""

import contextlib
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from api.services.admin_backups import (
    INTEGRITY_ENABLED_DEFAULT,
    AdminBackupsService,
    _normalize_check,
    _normalize_times,
    _normalize_timestamp,
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


# ══════════════════════════════════════════════════════════════════════════
#  _normalize_timestamp / _normalize_times
# ══════════════════════════════════════════════════════════════════════════


class TestNormalizeTimestamp:
    """The DB layer hands back a mix of types depending on which writer
    inserted the row: rethinkdb-mock returns native ints, the live
    driver returns ``datetime``, and old records still carry ISO
    strings. Normalise to a single ISO string for the wire."""

    def test_none_passthrough(self):
        assert _normalize_timestamp(None) is None

    def test_datetime_isoformatted(self):
        dt = datetime(2026, 1, 15, 10, 30, 0)
        assert _normalize_timestamp(dt) == "2026-01-15T10:30:00"

    def test_unix_seconds(self):
        """``< 1e10`` is treated as Unix seconds (epoch ~ 2286).
        2026-01-15 10:30:00 UTC = 1768487400."""
        result = _normalize_timestamp(1768487400)
        # Local-tz dependent; pin only the date part.
        assert result.startswith("2026-01-1")

    def test_unix_milliseconds_detected(self):
        """``> 1e10`` is treated as Unix milliseconds. The cutoff
        between s and ms is ~ 2286 — beyond a sane window for any
        legacy ``timestamp`` field."""
        result = _normalize_timestamp(1768487400000)
        assert result.startswith("2026-01-1")

    def test_float_seconds(self):
        result = _normalize_timestamp(1768487400.5)
        assert result.startswith("2026-01-1")

    def test_iso_string_passthrough(self):
        """ISO strings are returned untouched — no double-formatting."""
        assert _normalize_timestamp("2026-04-27T12:00:00") == "2026-04-27T12:00:00"

    def test_unknown_type_passthrough(self):
        """Bytes / lists / dicts have no ``isoformat`` and aren't
        numeric — drop through unchanged so a future field rename
        doesn't produce a 500 here."""
        assert _normalize_timestamp([1, 2]) == [1, 2]


class TestNormalizeTimes:
    def test_normalises_each_known_timestamp_field(self):
        item = {
            "id": "b1",
            "status": "ok",
            "timestamp": 1768487400,
            "received_at": "2026-04-27T12:00:00",
            "created_at": datetime(2026, 4, 27, 12, 0, 0),
            "backup_start_time": None,
        }
        out = _normalize_times(item)
        # In-place mutation — pin the contract.
        assert out is item
        assert isinstance(item["timestamp"], str)
        assert item["received_at"] == "2026-04-27T12:00:00"
        assert item["created_at"] == "2026-04-27T12:00:00"
        assert item["backup_start_time"] is None
        # Non-time fields untouched.
        assert item["id"] == "b1"
        assert item["status"] == "ok"

    def test_skips_absent_fields(self):
        """A row that only has ``timestamp`` doesn't get the others
        injected as ``None`` — pin so a future refactor that adds
        ``setdefault`` is caught."""
        item = {"timestamp": 1768487400}
        _normalize_times(item)
        assert "received_at" not in item
        assert "created_at" not in item
        assert "backup_start_time" not in item


# ══════════════════════════════════════════════════════════════════════════
#  _normalize_check
# ══════════════════════════════════════════════════════════════════════════


class TestNormalizeCheck:
    """``insert_backup`` calls this on every entry of
    ``data["details"]["checks"]`` to coerce historical formats
    (string, raw object) into the canonical
    ``{"name": str, "status": str}`` shape the webapp renders."""

    def test_canonical_dict_passthrough(self):
        check = {"name": "borg-init", "status": "success"}
        assert _normalize_check(check) is check

    def test_canonical_dict_with_extra_keys_passthrough(self):
        """Extra keys are preserved — the function only enforces the
        two required ones."""
        check = {"name": "borg-init", "status": "warning", "details": "..."}
        assert _normalize_check(check) is check

    def test_string_wrapped(self):
        assert _normalize_check("borg-init") == {
            "name": "borg-init",
            "status": "success",
        }

    def test_partial_dict_treated_as_unknown(self):
        """A dict missing ``name`` or ``status`` falls through to the
        ``str(check)`` branch — the result is a syntactically valid
        check object even if its name field looks ugly. Pin this so
        a future change that raises here is a deliberate choice."""
        out = _normalize_check({"name": "borg-init"})  # missing 'status'
        assert out["status"] == "success"
        assert out["name"] == str({"name": "borg-init"})

    def test_arbitrary_object_stringified(self):
        out = _normalize_check(42)
        assert out == {"name": "42", "status": "success"}
