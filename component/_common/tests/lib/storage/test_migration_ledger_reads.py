# SPDX-License-Identifier: AGPL-3.0-or-later

"""How often one advance() reads the migration ledger, and how it audits."""

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from isardvdi_common.models.storage_migration import build_totals

from .test_migration_recurring_drive import NOW, _FakeRedis, _item, _Mig, _runner

N = 500


class _Lock:
    def acquire(self):
        return True

    def reacquire(self):
        return True

    def release(self):
        pass


class _Conn(_FakeRedis):
    def lock(self, *a, **k):
        return _Lock()


class _CountingMig(_Mig):
    def recompute_totals(self, items=None):
        if items is None:
            items = mr.StorageMigrationItem.dicts_by_migration(self.id)
        return build_totals({}, items)


def _in_flight(n):
    return [
        _item(
            f"d{i}",
            "moving",
            tree=f"d{i}",
            move_task_id=f"t{i}",
            autostart_domains=[],
        )
        for i in range(n)
    ]


def test_one_advance_reads_the_ledger_at_most_twice(monkeypatch):
    items = _in_flight(N)
    m = _CountingMig("running", {})
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=lambda t: "started")
    del r.prepare
    reads = []
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: reads.append(mid) or items),
    )

    class _SM:
        exists = staticmethod(lambda mid: True)

        def __new__(cls, mid):
            return m

    monkeypatch.setattr(mr, "StorageMigration", _SM)
    monkeypatch.setattr(mr, "MigrationRunner", lambda mid, job_status_fn: r)
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: _Conn())
    progress = iter([True, False])
    monkeypatch.setattr(mig, "tick_made_progress", lambda results: next(progress))

    assert mr.advance("m", check_abandon=False) == "done"
    assert len(reads) <= 2, f"{len(reads)} ledger reads for one advance()"


def test_audit_is_appended_server_side_not_rewritten(monkeypatch):
    item = _item("d0", "released")
    del item["audit"]
    m = _Mig("running", {})
    r = _runner(monkeypatch, [item], m, now=NOW)
    appended = []
    written = []
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "append_audit",
        classmethod(lambda cls, iid, rec: appended.append((iid, rec["result"]))),
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(lambda cls, iid, fields, validate=True: written.append(fields)),
    )

    r._audit(item, "moved_ok")

    assert appended == [("m--d0", "moved_ok")]
    assert not any("audit" in fields for fields in written)
