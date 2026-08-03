"""A disk we claimed must not keep our task id once we are done with it.

The claim is stamped on the storage row so a concurrent operation can see the
saga owns the disk. Releasing it is a separate concern from restoring the status:
a disk already sitting at the destination skips the move entirely, so it never
records a pre-migration status, but its parent still moves and the child is still
rebased -- which claims the row. Left behind, that dead task id makes a lookup by
task return more than one storage and makes a reconcile pass read finished work
as live.
"""

from unittest.mock import patch

from isardvdi_common.lib.storage.migration_run import MigrationRunner


def _runner():
    return MigrationRunner.__new__(MigrationRunner)


def test_release_clears_our_claim_when_only_rebase_touched_the_disk():
    """The in-place disk: move skipped (no original recorded), rebase claimed it."""
    item = {
        "storage_id": "s-inplace",
        "rebase_task_id": "t-rebase",
        "storage_orig_status": None,
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        storage.return_value.task = "t-rebase"
        _runner()._restore_storage_status(item)

    storage.update_document.assert_called_once()
    args = storage.update_document.call_args[0]
    assert args[0] == "s-inplace"
    assert args[1]["task"] is None
    assert "status" not in args[1], "no original was recorded, so none is forced"


def test_release_restores_status_and_clears_claim_when_both_are_known():
    item = {
        "storage_id": "s-moved",
        "move_task_id": "t-move",
        "storage_orig_status": "recycled",
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        storage.return_value.task = "t-move"
        _runner()._restore_storage_status(item)

    args = storage.update_document.call_args[0]
    assert args[1] == {"status": "recycled", "task": None}


def test_release_leaves_a_task_that_is_not_ours_alone():
    """Someone else owns the disk now -- clearing their claim would be worse than
    leaving ours behind."""
    item = {
        "storage_id": "s-taken",
        "rebase_task_id": "t-rebase",
        "storage_orig_status": None,
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        storage.return_value.task = "t-someone-else"
        _runner()._restore_storage_status(item)

    storage.update_document.assert_not_called()


def test_untouched_disk_is_not_written_at_all():
    item = {"storage_id": "s-pending", "storage_orig_status": None}
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        storage.return_value.task = None
        _runner()._restore_storage_status(item)

    storage.update_document.assert_not_called()


def test_skip_release_drops_the_claim_a_rebase_left_on_an_in_place_disk():
    """The path the live run exposed: dst == src, so the move is skipped and the
    disk goes straight to released -- but its parent moved, so a rebase ran and
    claimed the row. Marking it released without dropping that claim leaves a
    dead task id on a ready disk."""
    runner = _runner()
    item = {
        "storage_id": "s-inplace",
        "rebase_task_id": "t-rebase",
        "storage_orig_status": None,
    }
    recorded = []
    with patch(
        "isardvdi_common.lib.storage.migration_run.Storage"
    ) as storage, patch.object(
        MigrationRunner, "_set", lambda self, it, **kw: recorded.append(kw)
    ), patch.object(
        MigrationRunner, "_audit", lambda self, it, result: recorded.append(result)
    ):
        storage.return_value.task = "t-rebase"
        runner._skip_release(item)

    assert "in_place" in recorded, "the audit record must still say it was in place"
    storage.update_document.assert_called_once()
    assert storage.update_document.call_args[0][1]["task"] is None
