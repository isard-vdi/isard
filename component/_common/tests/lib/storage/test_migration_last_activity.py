# SPDX-License-Identifier: AGPL-3.0-or-later

"""last_activity_at: the executor stamps the job on every disk state change."""

from types import SimpleNamespace

import isardvdi_common.lib.storage.migration_run as mr


def _runner(migration):
    r = object.__new__(mr.MigrationRunner)
    r.migration = migration
    return r


def _no_db_writes(monkeypatch):
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(lambda cls, iid, fields, validate=True: None),
    )


def test_set_stamps_last_activity_on_state_change(monkeypatch):
    _no_db_writes(monkeypatch)
    m = SimpleNamespace(last_activity_at=None)
    r = _runner(m)
    r._set({"id": "i1", "state": "pending"}, state="moving")
    assert m.last_activity_at is not None


def test_set_does_not_stamp_a_non_state_write(monkeypatch):
    _no_db_writes(monkeypatch)
    m = SimpleNamespace(last_activity_at=None)
    r = _runner(m)
    r._set({"id": "i1", "state": "moving"}, error="boom")
    assert m.last_activity_at is None


def test_set_does_not_stamp_an_idempotent_resave(monkeypatch):
    # at-least-once re-delivery re-writes the same state; that is not new activity.
    _no_db_writes(monkeypatch)
    m = SimpleNamespace(last_activity_at=None)
    r = _runner(m)
    r._set({"id": "i1", "state": "moving"}, state="moving")
    assert m.last_activity_at is None
