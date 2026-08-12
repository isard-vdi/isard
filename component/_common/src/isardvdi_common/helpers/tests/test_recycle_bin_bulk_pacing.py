#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the pacing of the two bulk paths that feed the recycle bin.

Both hand a burst of RethinkDB row writes to the changefeed emitter and
from there to the change-handler and the engine. Unpaced, a large delete
floods them in one go, which is the load spike this pacing prevents. The
queue-tier governor does not cover this: it gates the RQ storage lanes,
which never see these row writes.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def bulk_module(monkeypatch):
    from isardvdi_common.helpers import recycle_bin as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.RecycleBinBulk, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.RecycleBinBulk),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod.r, "args", lambda ids: list(ids))

    reads = []

    def fake_table(name):
        table = MagicMock(name="table-" + name)

        def fake_get_all(args):
            chain = MagicMock(name="get_all")
            reads.append(list(args))
            chain.run = MagicMock(return_value=[])
            chain.delete = MagicMock(
                return_value=MagicMock(run=MagicMock(return_value={"deleted": 0}))
            )
            return chain

        table.get_all = fake_get_all
        return table

    monkeypatch.setattr(mod.r, "table", fake_table)
    monkeypatch.setattr(
        mod.CommonHelpers, "desktops_stop", staticmethod(lambda *a: None)
    )

    sleeps = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

    yield mod, reads, sleeps


class TestRecycleBinBulkAddPacing:
    """``add`` is reached with a whole deployment group at once via
    ``deployment_delete_desktops``, so the caller's batching does not bound
    it — it needs pacing of its own."""

    def _build(self, mod):
        bulk = mod.RecycleBinBulk.__new__(mod.RecycleBinBulk)
        bulk.id = "rb-1"
        bulk.agent_id = "agent"
        return bulk

    def test_paces_every_50_desktops(self, bulk_module, monkeypatch):
        mod, _reads, sleeps = bulk_module
        bulk = self._build(mod)
        # ``add`` reaches these through ``super()``, so they must be patched on
        # the parent class, not on RecycleBinBulk.
        monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda self, o: None)
        monkeypatch.setattr(mod.RecycleBin, "_set_data", lambda self, i: None)
        monkeypatch.setattr(
            mod, "RecycleBinDesktop", lambda **kw: MagicMock(name="rcb-desktop")
        )

        bulk.add([f"d-{i}" for i in range(120)])

        # Crossings at 50 and 100, never a trailing pause.
        assert sleeps == [0.5, 0.5]

    def test_single_batch_does_not_sleep(self, bulk_module, monkeypatch):
        mod, _reads, sleeps = bulk_module
        bulk = self._build(mod)
        # ``add`` reaches these through ``super()``, so they must be patched on
        # the parent class, not on RecycleBinBulk.
        monkeypatch.setattr(mod.RecycleBin, "_add_owner", lambda self, o: None)
        monkeypatch.setattr(mod.RecycleBin, "_set_data", lambda self, i: None)
        monkeypatch.setattr(
            mod, "RecycleBinDesktop", lambda **kw: MagicMock(name="rcb-desktop")
        )

        bulk.add([f"d-{i}" for i in range(10)])

        assert sleeps == []


class TestDesktopsDeletePacing:
    """``DesktopEvents.desktops_delete`` is the admin multiple-actions
    delete path."""

    def test_batches_at_50_and_paces_between_them(self, monkeypatch):
        from isardvdi_common.helpers import desktop_events as mod

        created = []

        class _FakeBulk:
            def __init__(self, user_id=None):
                created.append(self)

            def add(self, batch_ids):
                self.batch = list(batch_ids)

        monkeypatch.setattr(mod, "RecycleBinBulk", _FakeBulk)
        monkeypatch.setattr(
            mod.RecycleBinHelpers,
            "get_user_recycle_bin_cutoff_time",
            classmethod(lambda cls, agent_id: 3600),
        )
        monkeypatch.setattr(mod, "notify_admins", lambda *a, **kw: None)

        sleeps = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        mod.DesktopEvents.desktops_delete("agent", [f"d-{i}" for i in range(120)])

        # 120 ids at batch_size 50 -> 3 batches, 2 pauses.
        assert [len(b.batch) for b in created] == [50, 50, 20]
        assert sleeps == [0.5, 0.5]

    def test_no_pause_for_a_single_batch(self, monkeypatch):
        from isardvdi_common.helpers import desktop_events as mod

        class _FakeBulk:
            def __init__(self, user_id=None):
                pass

            def add(self, batch_ids):
                pass

        monkeypatch.setattr(mod, "RecycleBinBulk", _FakeBulk)
        monkeypatch.setattr(
            mod.RecycleBinHelpers,
            "get_user_recycle_bin_cutoff_time",
            classmethod(lambda cls, agent_id: 3600),
        )
        monkeypatch.setattr(mod, "notify_admins", lambda *a, **kw: None)

        sleeps = []
        monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

        mod.DesktopEvents.desktops_delete("agent", ["d-1", "d-2"])

        assert sleeps == []
