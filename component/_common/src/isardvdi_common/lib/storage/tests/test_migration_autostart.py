# SPDX-License-Identifier: AGPL-3.0-or-later

"""Autostart-suppression crash-safety tests (qcow-2).

The guard must survive a crash at ANY point of prepare() without either
(a) leaving a domain recorded-but-not-suppressed (original bug), or
(b) losing the pre-suppression value so reactivate can't restore it (the
    regression the first re-fix introduced by deactivating before persisting).

Correct ordering: persist the ledger records FIRST (was_on = current live
value), THEN deactivate; re-derive the deactivation set from the full ledger
every prepare but filter it to the still-live domains so it neither re-fires
(notify spam) nor misses a crash-interrupted suppression.
"""

import isardvdi_common.lib.storage.migration_run as mr
from isardvdi_common.lib.storage import migration as mig


class _Dom:
    def __init__(self, did, on):
        self.id = did
        self.server_autostart = on


def _domains_map(mapping):
    return lambda sid: mapping.get(sid, [])


# --------------------------------------------------------------------------- #
# plan_autostart_deactivation (pure)
# --------------------------------------------------------------------------- #
def test_records_new_items_capturing_current_live_value():
    items = [{"id": "i1", "storage_id": "s1", "autostart_domains": None}]
    doms = _domains_map({"s1": [_Dom("d1", True), _Dom("d2", False)]})
    writes, to_deactivate = mig.plan_autostart_deactivation(items, doms)
    # was_on captures the live value at record time (pre-suppression)
    assert writes == [
        (items[0], [{"id": "d1", "was_on": True}, {"id": "d2", "was_on": False}])
    ]
    # only the currently-on domain is suppressed
    assert to_deactivate == ["d1"]


def test_recorded_but_still_on_is_resuppressed_after_crash():
    # crash between persisting was_on=True and deactivating: the domain is still
    # live-on, so a fresh prepare re-derives and re-suppresses it (crash-safe).
    items = [
        {
            "id": "i1",
            "storage_id": "s1",
            "autostart_domains": [{"id": "d1", "was_on": True}],
        }
    ]
    doms = _domains_map({"s1": [_Dom("d1", True)]})  # still on (not yet suppressed)
    writes, to_deactivate = mig.plan_autostart_deactivation(items, doms)
    assert writes == []  # already recorded -> not re-recorded
    assert to_deactivate == ["d1"]  # re-suppressed


def test_recorded_and_already_suppressed_is_not_refired():
    # once a domain is suppressed (live now False) it is NOT re-added every tick
    # -> no redundant writes / admin-notification spam.
    items = [
        {
            "id": "i1",
            "storage_id": "s1",
            "autostart_domains": [{"id": "d1", "was_on": True}],
        }
    ]
    doms = _domains_map({"s1": [_Dom("d1", False)]})  # already suppressed
    writes, to_deactivate = mig.plan_autostart_deactivation(items, doms)
    assert writes == []
    assert to_deactivate == []  # no re-fire


def test_combines_recorded_and_new():
    items = [
        {
            "id": "i1",
            "storage_id": "s1",
            "autostart_domains": [{"id": "d1", "was_on": True}],
        },
        {"id": "i2", "storage_id": "s2", "autostart_domains": None},
    ]
    doms = _domains_map({"s1": [_Dom("d1", True)], "s2": [_Dom("d2", True)]})
    writes, to_deactivate = mig.plan_autostart_deactivation(items, doms)
    assert [w[0]["id"] for w in writes] == ["i2"]  # only the un-recorded item
    assert set(to_deactivate) == {"d1", "d2"}  # both still-on


# --------------------------------------------------------------------------- #
# prepare() ordering (executor) — persist BEFORE deactivate (the re-fix)
# --------------------------------------------------------------------------- #
def test_prepare_persists_records_before_deactivating(monkeypatch):
    """A crash right after deactivation must still leave was_on=True in the
    ledger for reactivate to restore — so the record is persisted FIRST."""
    item = {"id": "i1", "storage_id": "s1", "autostart_domains": None}
    events = []

    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: [item]),
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(
            lambda cls, iid, fields, validate=True: events.append(
                ("persist", fields.get("autostart_domains"))
            )
        ),
    )
    monkeypatch.setattr(
        mr.DesktopEvents,
        "deactivate_autostart",
        staticmethod(lambda ids, **k: events.append(("deactivate", list(ids)))),
    )
    monkeypatch.setattr(
        mr.MigrationRunner, "_domains", lambda self, sid: [_Dom("d1", True)]
    )

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.prepare()

    kinds = [e[0] for e in events]
    assert "persist" in kinds and "deactivate" in kinds
    assert kinds.index("persist") < kinds.index("deactivate")  # persist FIRST
    # the persisted record captured the PRE-suppression value
    persisted = next(e[1] for e in events if e[0] == "persist")
    assert persisted == [{"id": "d1", "was_on": True}]
    # the still-on domain was the one deactivated
    assert next(e[1] for e in events if e[0] == "deactivate") == ["d1"]
