# SPDX-License-Identifier: AGPL-3.0-or-later

"""Autostart-suppression crash-safety tests (qcow-2).

prepare() recorded each item's autostart_domains in the ledger but only added
the JUST-recorded items to the deactivation batch. A crash (or a swallowed
batch error) between recording and deactivating left domains
recorded-but-not-suppressed; resume skipped them (record present) so autostart
was never actually turned off — the livelock guard silently defeated, an
autostart could open a qcow2 mid-rsync/rebase.

plan_autostart_deactivation re-derives the deactivation set from the FULL
ledger every prepare (already-recorded items included), and the runner
deactivates BEFORE persisting, so the suppression is idempotent and
crash-safe.
"""

from isardvdi_common.lib.storage import migration as mig


class _Dom:
    def __init__(self, did, on):
        self.id = did
        self.server_autostart = on


def test_redrives_recorded_domains_after_crash():
    # record persisted (was_on=True) but deactivate never ran (crash window):
    # a fresh prepare MUST still re-derive it into the deactivation set.
    items = [
        {
            "id": "i1",
            "storage_id": "s1",
            "autostart_domains": [
                {"id": "d1", "was_on": True},
                {"id": "d2", "was_on": False},
            ],
        }
    ]
    writes, to_deactivate = mig.plan_autostart_deactivation(items, lambda sid: [])
    assert writes == []  # already recorded -> not re-recorded
    assert to_deactivate == ["d1"]  # re-derived despite being recorded


def test_records_new_items_and_collects_was_on():
    items = [{"id": "i1", "storage_id": "s1", "autostart_domains": None}]
    writes, to_deactivate = mig.plan_autostart_deactivation(
        items, lambda sid: [_Dom("d1", True), _Dom("d2", False)]
    )
    assert writes == [
        (items[0], [{"id": "d1", "was_on": True}, {"id": "d2", "was_on": False}])
    ]
    assert to_deactivate == ["d1"]


def test_combines_recorded_and_new():
    items = [
        {
            "id": "i1",
            "storage_id": "s1",
            "autostart_domains": [{"id": "d1", "was_on": True}],
        },
        {"id": "i2", "storage_id": "s2", "autostart_domains": None},
    ]
    writes, to_deactivate = mig.plan_autostart_deactivation(
        items, lambda sid: [_Dom("d2", True)]
    )
    assert [w[0]["id"] for w in writes] == ["i2"]  # only the un-recorded item
    assert set(to_deactivate) == {"d1", "d2"}  # recorded + new, both suppressed
