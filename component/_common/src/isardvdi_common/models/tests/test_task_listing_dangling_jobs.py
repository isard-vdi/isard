# SPDX-License-Identifier: AGPL-3.0-or-later

"""Task listing resilience to dangling RQ job references.

When a worker or redis restarts mid-chain (e.g. during an upgrade), a job's
hash can be evicted from Redis while a queue list or a ``*_job_registry`` zset
still references its id. ``Task.get_by_status`` / ``Task.get_all`` materialize
every such id with ``Task(id=...)`` -> ``Job.fetch`` -> ``NoSuchJobError``.

A single dangling id must NOT abort the whole listing: that silently breaks the
change-handler reconcile self-heal (``_reconcile_orphan_deferred`` lists
DEFERRED tasks every tick) and ``Task.get_failed_storage_tasks``, and — because
the orphan references are exactly what the reconcile exists to clear — it never
recovers and re-raises ``NoSuchJobError`` every cycle. The dangling id must be
skipped and purged from its source so the orphan self-clears.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task
from rq.exceptions import NoSuchJobError
from rq.job import JobStatus

_ALL_STATUSES = ("failed", "started", "finished", "deferred", "scheduled", "canceled")


def _full_queue(registry_ids=None, queued_ids=()):
    """A fake RQ Queue exposing ``job_ids`` and every ``*_job_registry`` with a
    controllable ``get_job_ids()`` plus a ``remove`` spy."""
    registry_ids = registry_ids or {}
    queue = SimpleNamespace()
    queue.job_ids = list(queued_ids)
    queue.remove = MagicMock(name="queue.remove")
    regs = {}
    for status in _ALL_STATUSES:
        reg = MagicMock(name=f"{status}_job_registry")
        reg.get_job_ids.return_value = list(registry_ids.get(status, []))
        setattr(queue, f"{status}_job_registry", reg)
        regs[status] = reg
    return queue, regs


def _patch_construction(dangling):
    """Patch ``Task(id=...)`` so listed ids resolve to a light fake task, except
    the given dangling ids which raise ``NoSuchJobError`` like a real
    ``Job.fetch`` of an evicted job would."""

    def fake_init(self, *args, **kwargs):
        job_id = kwargs.get("id", args[0] if args else None)
        if job_id in dangling:
            raise NoSuchJobError(f"No such job: {job_id}")
        self.job = SimpleNamespace(id=job_id)

    return patch.object(Task, "__init__", fake_init)


def _patch_queue(queue):
    Q = MagicMock(name="Queue")
    Q.all.return_value = [queue]
    return patch("isardvdi_common.models.task.Queue", Q)


def test_get_by_status_skips_dangling_registry_id():
    queue, _ = _full_queue(registry_ids={"deferred": ["live1", "dangling1", "live2"]})
    with _patch_queue(queue), _patch_construction({"dangling1"}):
        tasks = Task.get_by_status(JobStatus.DEFERRED.value)
    assert sorted(t.job.id for t in tasks) == ["live1", "live2"]


def test_get_by_status_purges_dangling_registry_id():
    queue, regs = _full_queue(registry_ids={"deferred": ["dangling1", "live1"]})
    with _patch_queue(queue), _patch_construction({"dangling1"}):
        Task.get_by_status(JobStatus.DEFERRED.value)
    regs["deferred"].remove.assert_called_once_with("dangling1")


def test_get_by_status_purges_dangling_queue_id():
    queue, _ = _full_queue(queued_ids=["dangling_q"])
    with _patch_queue(queue), _patch_construction({"dangling_q"}):
        tasks = Task.get_by_status(JobStatus.DEFERRED.value)
    assert tasks == []
    queue.remove.assert_called_once_with("dangling_q")


def test_get_by_status_no_purge_when_all_live():
    queue, regs = _full_queue(
        registry_ids={"deferred": ["live1"]}, queued_ids=["live2"]
    )
    with _patch_queue(queue), _patch_construction(set()):
        tasks = Task.get_by_status(JobStatus.DEFERRED.value)
    assert sorted(t.job.id for t in tasks) == ["live1", "live2"]
    regs["deferred"].remove.assert_not_called()
    queue.remove.assert_not_called()


def test_get_by_status_propagates_non_missing_job_errors():
    """A transient redis error is NOT an orphan: it must propagate, and nothing
    may be purged on its account."""
    queue, regs = _full_queue(registry_ids={"deferred": ["boom"]})

    def fake_init(self, *args, **kwargs):
        raise ConnectionError("redis down")

    with _patch_queue(queue), patch.object(Task, "__init__", fake_init):
        raised = False
        try:
            Task.get_by_status(JobStatus.DEFERRED.value)
        except ConnectionError:
            raised = True
    assert raised
    regs["deferred"].remove.assert_not_called()


def test_get_all_skips_and_purges_dangling_ids():
    queue, regs = _full_queue(
        registry_ids={"finished": ["live_f", "dangling_f"], "failed": ["live_x"]},
        queued_ids=["live_q"],
    )
    with _patch_queue(queue), _patch_construction({"dangling_f"}):
        tasks = Task.get_all()
    assert sorted(t.job.id for t in tasks) == ["live_f", "live_q", "live_x"]
    regs["finished"].remove.assert_called_once_with("dangling_f")


def test_get_all_started_registry_unsupported_remove_no_traceback():
    """In RQ 2.3.2 ``StartedJobRegistry.remove()`` raises ``NotImplementedError``
    (composite ``{job_id}:{execution_id}`` members). A dangling 'started' id must
    still be skipped without aborting the listing AND without spamming an
    exception-level traceback every pass — the orphan is left for RQ's own
    registry cleanup."""
    queue, regs = _full_queue(registry_ids={"started": ["live_s", "dangling_s"]})
    regs["started"].remove.side_effect = NotImplementedError()
    with _patch_queue(queue), _patch_construction({"dangling_s"}), patch(
        "isardvdi_common.models.task.log"
    ) as mock_log:
        tasks = Task.get_all()
    assert sorted(t.job.id for t in tasks) == ["live_s"]
    mock_log.exception.assert_not_called()
