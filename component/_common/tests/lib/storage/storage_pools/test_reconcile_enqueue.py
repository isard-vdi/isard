# SPDX-License-Identifier: AGPL-3.0-or-later

"""enqueue_reconciles enqueues one reconcile_pool per enabled pool and skips busy ones."""

from isardvdi_common.lib.storage.storage_pools import storage_pools as mod

SPP = mod.StoragePoolsProcessed


class _FakeTask:
    created: list = []

    def __init__(self, task=None, queue=None, job_kwargs=None):
        self.task = task
        self.queue = queue
        self.job_kwargs = job_kwargs
        self.id = f"job-{len(_FakeTask.created)}"
        _FakeTask.created.append(self)


def _setup(monkeypatch, pools, pending=lambda c, q: False):
    _FakeTask.created = []
    monkeypatch.setattr(mod, "Task", _FakeTask)
    monkeypatch.setattr(SPP, "_enabled_pools", classmethod(lambda c: pools))
    monkeypatch.setattr(SPP, "_reconcile_pending", classmethod(pending))


def test_enqueues_one_task_per_enabled_pool(monkeypatch):
    _setup(
        monkeypatch,
        [{"id": "p1", "mountpoint": "/isard"}, {"id": "p2", "mountpoint": "/mnt/b"}],
    )
    out = SPP.enqueue_reconciles(apply=False, metrics_dir="/m")
    assert [t["pool"] for t in out] == ["p1", "p2"]
    assert [t.queue for t in _FakeTask.created] == [
        "storage.p1.background",
        "storage.p2.background",
    ]
    assert _FakeTask.created[0].task == "reconcile_pool"
    kw = _FakeTask.created[0].job_kwargs["kwargs"]
    assert kw["path"] == "/isard"
    assert kw["apply"] is False
    assert kw["metrics_file"] == "/m/isardvdi_storage_reconcile_p1.prom"


def test_apply_flag_is_carried_to_the_task(monkeypatch):
    _setup(monkeypatch, [{"id": "p1", "mountpoint": "/isard"}])
    SPP.enqueue_reconciles(apply=True, metrics_dir="/m")
    assert _FakeTask.created[0].job_kwargs["kwargs"]["apply"] is True


def test_idempotent_skips_a_pool_that_already_has_one(monkeypatch):
    _setup(
        monkeypatch,
        [{"id": "p1", "mountpoint": "/isard"}, {"id": "p2", "mountpoint": "/mnt/b"}],
        pending=lambda c, q: q == "storage.p1.background",
    )
    out = SPP.enqueue_reconciles(apply=False, metrics_dir="/m")
    assert [t["pool"] for t in out] == ["p2"]
    assert [t.queue for t in _FakeTask.created] == ["storage.p2.background"]


def test_pool_without_a_mountpoint_is_skipped(monkeypatch):
    _setup(monkeypatch, [{"id": "p1", "mountpoint": None}])
    assert SPP.enqueue_reconciles(apply=False) == []
    assert _FakeTask.created == []
