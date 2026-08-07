# SPDX-License-Identifier: AGPL-3.0-or-later

"""``has_pending_task`` answers whether the disk is busy, not whether a job row
still exists.

The field replaced the retired ``task`` pointer on the storage detail. Its own
commit says what it is for: *"Its only consumer, the desktop storage modal, used
it as a boolean — is this row busy — so the schema carries that as
has_pending_task"*. It was derived as ``bool(current_task_id(...))``, and that
primitive answers a different question by design: it returns *the newest member
whose job still EXISTS*, deliberately not proving the job is unfinished. rq keeps
a finished job's hash for its result TTL, so for those minutes an idle disk
reports itself busy.

Observed on a live stack, on a disk whose create chain had just completed::

    index      → 2b544d05…  status=JobStatus.FINISHED  pending=False
    GET /item/storage/<id> → {"status": "ready", "has_pending_task": true}

Every other reader in the tree already pairs the lookup with the pending check
(``if pending and Task(pending).pending``); this one did not, and nothing tested
it, which is how it shipped.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.services.storage import StorageService

ROW = {"id": "s-1", "status": "ready", "task": "leftover-scalar"}


def _run(task_id, pending, loadable=True):
    """Run the real ``get_storage_detail`` with the index and the resolver
    stubbed. ``loadable`` models the job whose hash the index can see but rq
    cannot load: the resolver's contract is to answer with nothing."""
    task_cls = MagicMock(name="TaskClass")
    task_cls._redis = MagicMock(name="redis")
    resolved = [SimpleNamespace(pending=pending)] if (task_id and loadable) else []

    with patch("api.services.storage.get_storage"), patch(
        "api.services.storage.StorageProcessed.get_storage_row",
        return_value=dict(ROW),
    ), patch("api.services.storage.Task", task_cls), patch(
        "api.services.storage.tasks_from_ids", return_value=resolved
    ), patch(
        "api.services.storage.current_task_id", return_value=task_id
    ):
        return StorageService.get_storage_detail({"user_id": "u-1"}, "s-1")


class TestHasPendingTask:
    def test_a_finished_job_is_not_pending(self):
        """The defect: rq still holds the hash, so the index still names it."""
        assert _run("t-done", pending=False)["has_pending_task"] is False

    def test_a_live_job_is_pending(self):
        assert _run("t-live", pending=True)["has_pending_task"] is True

    def test_no_task_at_all_is_not_pending(self):
        assert _run(None, pending=False)["has_pending_task"] is False

    def test_the_retired_scalar_is_never_served(self):
        """Unchanged contract, pinned so the fix cannot reintroduce it."""
        assert "task" not in _run("t-live", pending=True)

    def test_a_hash_the_index_sees_but_rq_cannot_load_is_not_a_500(self):
        """The other half of "exists is not enough".

        The index proves the hash is THERE. A hash left with only a status
        field passes that and still cannot be loaded — rq raises on it, and
        this route's blanket handler would serve that as internal_server. So
        the id is resolved the way the neighbouring endpoints resolve it,
        through ``tasks_from_ids``, which answers with nothing instead of
        raising. Reading a disk must not fail because of a half-expired job.
        """
        assert _run("t-half-expired", pending=True, loadable=False) == {
            **{k: v for k, v in ROW.items() if k != "task"},
            "has_pending_task": False,
        }
