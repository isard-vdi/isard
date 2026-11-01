# SPDX-License-Identifier: AGPL-3.0-or-later

"""Concurrent-driver re-scan safety.

Two drivers can drain one migration at once (the advance lease can lapse during a
long pass). These pin that a re-scan then never regresses a live ledger row back
to ``pending`` and that the occurrence re-arm runs once per occurrence."""

import pytest
from isardvdi_common.lib.storage import migration_run as mr

from .test_migration_recurring_drive import NOW, WINDOW, _item, _Mig, _runner


def _table_backed_inserts(monkeypatch, table):
    """Replace the two ledger inserts with ones that honour the REAL RethinkDB
    conflict semantics against a by-id ``table``: ``upsert`` merges (what
    ``conflict="update"`` does, and what regresses a live row), ``insert_absent``
    is a no-op on an existing id. The suite's default fakes merely append, which
    cannot tell the regression from the fix."""

    def _upsert(cls, data):
        row = table.get(data["id"])
        if row is None:
            table[data["id"]] = dict(data)
        else:
            row.update(data)
        return True

    def _insert_absent(cls, data):
        if data["id"] in table:
            return False
        table[data["id"]] = dict(data)
        return True

    monkeypatch.setattr(mr.StorageMigrationItem, "upsert", classmethod(_upsert))
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "insert_absent",
        classmethod(_insert_absent),
        raising=False,
    )


def _released_in_table(sid):
    return _item(
        sid,
        "released",
        tree=sid,
        move_task_id=f"t-{sid}",
        move_delete_task_id=f"d-{sid}",
        verify_passed=True,
    )


def test_rescan_insert_new_does_not_regress_a_live_released_row(monkeypatch):
    # Another driver already inserted and released disk x; this driver's snapshot
    # predates that insert, so the re-scan sees x as "new" and tries to add it.
    released = _released_in_table("x")
    table = {released["id"]: dict(released)}
    m = _Mig("running", {"recurring": True, "window": WINDOW})
    r = _runner(monkeypatch, [], m, now=NOW, planned=[_item("x", "pending", tree="x")])
    r._snapshot = None
    _table_backed_inserts(monkeypatch, table)

    r._rescan_insert_new()

    assert table[released["id"]]["state"] == "released"
    assert table[released["id"]]["move_task_id"] == "t-x"


def test_occurrence_rearm_does_not_regress_a_live_released_row(monkeypatch):
    released = _released_in_table("x")
    table = {released["id"]: dict(released)}
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    r = _runner(monkeypatch, [], m, now=NOW, planned=[_item("x", "pending", tree="x")])
    r._snapshot = None
    _table_backed_inserts(monkeypatch, table)

    r._rearm_for_occurrence("2026-07-01")

    assert table[released["id"]]["state"] == "released"


def test_occurrence_rescan_runs_once_when_claim_is_lost(monkeypatch):
    # Two drivers reach the same occurrence edge; only the one that wins the
    # atomic marker re-arms, so a second driver cannot run the re-arm concurrently.
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"  # different -> this tick is an occurrence edge
    r = _runner(
        monkeypatch, [_item("r", "failed")], m, now=NOW, planned=[_item("r", "pending")]
    )
    calls = []
    r._rearm_for_occurrence = lambda key: calls.append(key)
    m.claim_occurrence = lambda key: False  # this driver lost the marker race

    assert r._maybe_rescan_occurrence() is False
    assert calls == []


def test_occurrence_rescan_runs_for_the_winner(monkeypatch):
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(
        monkeypatch, [_item("r", "failed")], m, now=NOW, planned=[_item("r", "pending")]
    )
    calls = []
    r._rearm_for_occurrence = lambda key: calls.append(key)

    assert r._maybe_rescan_occurrence() is True
    assert calls == ["2026-07-01"]
    assert m.last_occurrence == "2026-07-01"


def test_occurrence_marker_rolls_back_when_the_rearm_aborts(monkeypatch):
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    r = _runner(
        monkeypatch, [_item("r", "failed")], m, now=NOW, planned=[_item("r", "pending")]
    )

    def _boom(key):
        raise RuntimeError("rearm aborted mid-flight")

    r._rearm_for_occurrence = _boom
    with pytest.raises(RuntimeError):
        r._maybe_rescan_occurrence()

    # the marker is rolled back, so the occurrence is not skipped for ever
    assert m.last_occurrence == "2026-06-30"
    # and the next pass re-runs the occurrence re-arm
    calls = []
    r._rearm_for_occurrence = lambda key: calls.append(key)
    assert r._maybe_rescan_occurrence() is True
    assert calls == ["2026-07-01"]
