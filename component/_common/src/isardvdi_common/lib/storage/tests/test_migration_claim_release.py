"""Restoring a disk puts its status back and touches nothing else.

The saga used to stamp its claim on the storage row and clear it here. Claims now
live in the task index, which reclaims its own dangling members, so there is no
release to perform -- and the row's ``task`` field is retired, kept only so a
rollback can still read what the last chain was. Writing to it here would erase
exactly the data the retirement preserves, which is why these tests assert on
what is *not* written as much as on what is.

The double must never declare liveness through the row's ``task``: the previous
version of this file did, so every case stayed green while the code path it
exercised could no longer run in production.
"""

from unittest.mock import patch

from isardvdi_common.lib.storage.migration_run import MigrationRunner


def _runner():
    return MigrationRunner.__new__(MigrationRunner)


def test_a_recorded_original_is_restored():
    item = {
        "storage_id": "s-moved",
        "move_task_id": "t-move",
        "storage_orig_status": "recycled",
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        _runner()._restore_storage_status(item)

    storage.update_document.assert_called_once()
    args = storage.update_document.call_args[0]
    assert args[0] == "s-moved"
    assert args[1] == {"status": "recycled"}


def test_the_retired_field_is_never_written():
    """The guard against reintroducing the rollback-data wipe.

    ``status`` is the only thing this writes. A future edit that adds
    ``"task": None`` back -- to "clean up" or to release a claim -- would clear
    the field the pointer retirement deliberately leaves on the row.
    """
    item = {
        "storage_id": "s-moved",
        "rebase_task_id": "t-rebase",
        "storage_orig_status": "ready",
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        _runner()._restore_storage_status(item)

    written = storage.update_document.call_args[0][1]
    assert "task" not in written
    assert set(written) == {"status"}


def test_a_disk_we_never_put_into_maintenance_is_not_written_at_all():
    """No recorded original means we never took a status, so none is forced --
    never blindly ``ready``, which would un-bin a recycled disk."""
    item = {
        "storage_id": "s-inplace",
        "rebase_task_id": "t-rebase",
        "storage_orig_status": None,
    }
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        _runner()._restore_storage_status(item)

    storage.update_document.assert_not_called()


def test_restore_does_not_read_the_row_to_decide():
    """It used to instantiate ``Storage`` just to compare the row's task against
    ours. That read now answers ``None`` for every disk, so the branch it fed was
    dead; nothing here may depend on the row's contents any more."""
    item = {"storage_id": "s-pending", "storage_orig_status": None}
    with patch("isardvdi_common.lib.storage.migration_run.Storage") as storage:
        _runner()._restore_storage_status(item)

    storage.assert_not_called()


def test_an_in_place_disk_is_released_and_audited_without_a_write():
    """dst == src: the move is skipped, so nothing recorded an original and the
    row must be left untouched -- but the item still reaches released and the
    audit still records it as in place."""
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
        runner._skip_release(item)

    assert "in_place" in recorded, "the audit record must still say it was in place"
    storage.update_document.assert_not_called()
