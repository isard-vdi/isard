# SPDX-License-Identifier: AGPL-3.0-or-later

"""The destructive end of the storage finalize handlers.

``handle_storage_delete`` is the only handler here that drops a row, and
what stops it dropping a live one is a two-part guard: the row must exist
*and* already be marked ``deleted``. Neither half had a test, so removing
either one kept the suite green while turning the finalize step of any
chain into an unconditional delete.

``_valid_storage_pool`` answers three different things with two falsy
values (``None`` = no pool claims this path, ``False`` = a pool claims it
but the filename does not match what it would have produced). A caller
that tested truthiness alone could not tell them apart, so the tests
assert identity rather than truthiness.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _task(depending_status="finished", **attrs):
    base = dict(
        id=attrs.pop("id", "t1"),
        user_id=attrs.pop("user_id", "u1"),
        depending_status=depending_status,
        dependencies=attrs.pop("dependencies", []),
    )
    base.update(attrs)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# storage.handle_storage_delete — the only handler that drops a row
# ---------------------------------------------------------------------------


def test_storage_delete_drops_a_row_already_marked_deleted():
    """The intended path: the chain settled, the row says ``deleted``."""
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as mock_storage_cls:
        mock_storage_cls.exists.return_value = True
        mock_storage_cls.return_value = SimpleNamespace(status="deleted")

        storage.handle_storage_delete(_task(), "s1")

    mock_storage_cls.delete.assert_called_once_with("s1")


def test_storage_delete_refuses_a_row_that_is_not_marked_deleted():
    """The guard that matters: a row in any other status keeps its file.

    ``storage_delete`` is the tail of the delete chain, but the chain can
    reach it with the row back in ``ready`` — a cancel, a heal, or a
    redelivery landing after something else revived the row. Dropping it
    then removes the DB row while the qcow2 is still on disk, which is
    the orphan class this whole finalize path exists to avoid.
    """
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as mock_storage_cls:
        mock_storage_cls.exists.return_value = True
        mock_storage_cls.return_value = SimpleNamespace(status="ready")

        storage.handle_storage_delete(_task(), "s1")

    mock_storage_cls.delete.assert_not_called()


def test_storage_delete_does_not_read_a_row_that_is_gone():
    """A vanished row returns before the lookup, not after it.

    Hydrating ``Storage(storage_id)`` for a missing id is what raises, so
    the existence check has to short-circuit rather than merely make the
    delete conditional.
    """
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as mock_storage_cls:
        mock_storage_cls.exists.return_value = False

        storage.handle_storage_delete(_task(), "s1")

    mock_storage_cls.assert_not_called()
    mock_storage_cls.delete.assert_not_called()


# ---------------------------------------------------------------------------
# storage.handle_storage_add
# ---------------------------------------------------------------------------


def test_storage_add_writes_the_payload_it_was_given():
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as mock_storage_cls:
        storage.handle_storage_add(_task(), id="s1", status="ready", user_id="u1")

    mock_storage_cls.insert_document.assert_called_once_with(
        {"id": "s1", "status": "ready", "user_id": "u1"}, conflict="update"
    )


# ---------------------------------------------------------------------------
# storage.handle_update_status — one bad entry must not eat the batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_skips_an_unknown_item_class_and_keeps_going():
    """An unrecognised ``item_class`` is skipped, not fatal to its batch.

    The statuses payload is built by the enqueuing side, so a name this
    consumer does not know is a version skew, not a reason to abandon the
    rows that follow it in the same dict. If the guard returned instead of
    continuing, every row listed after the unknown key would silently keep
    its old status — the chain would look finished with nothing written.
    """
    from isardvdi_change_handler.task_results import storage

    redis_manager = AsyncMock()
    model = MagicMock()

    with (
        patch.dict(storage._ITEM_CLASS_MAP, {"storage": model}, clear=False),
        patch.object(storage, "send_status_socket", new=AsyncMock()) as mock_send,
    ):
        await storage.handle_update_status(
            redis_manager,
            _task(),
            statuses={
                "_all": {
                    "ready": {
                        "NoSuchClass": ["x1"],
                        "storage": ["s1"],
                    }
                }
            },
        )

    model.insert_document.assert_called_once_with(
        {"id": "s1", "status": "ready"}, conflict="update"
    )
    mock_send.assert_awaited_once()


# ---------------------------------------------------------------------------
# storage._valid_storage_pool — two falsy answers that mean different things
# ---------------------------------------------------------------------------


def test_valid_storage_pool_returns_none_when_no_pool_claims_the_path():
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "StoragePool") as mock_pool_cls:
        mock_pool_cls.get_by_path.return_value = []

        assert storage._valid_storage_pool(MagicMock(), "/data/x.qcow2") is None


def test_valid_storage_pool_returns_false_when_the_path_is_not_the_one_it_would_write():
    """A pool claims the directory but the file is not this row's own.

    Distinct from ``None`` on purpose: a pool exists, so the row is not
    unplaceable — the path is wrong. Collapsing the two would let a
    mismatched path be treated as "no pool known" and re-resolved instead
    of rejected.
    """
    from isardvdi_change_handler.task_results import storage

    pool = MagicMock()
    row = MagicMock(id="s1")
    row.get_storage_pool_path.return_value = "/data"

    with patch.object(storage, "StoragePool") as mock_pool_cls:
        mock_pool_cls.get_by_path.return_value = [pool]

        assert storage._valid_storage_pool(row, "/data/someone-else.qcow2") is False


def test_valid_storage_pool_returns_the_pool_when_the_path_is_its_own():
    from isardvdi_change_handler.task_results import storage

    pool = MagicMock()
    row = MagicMock(id="s1")
    row.get_storage_pool_path.return_value = "/data"

    with patch.object(storage, "StoragePool") as mock_pool_cls:
        mock_pool_cls.get_by_path.return_value = [pool]

        assert storage._valid_storage_pool(row, "/data/s1.qcow2") is pool


def test_valid_storage_pool_returns_false_when_the_pool_has_no_path_for_this_row():
    """``get_storage_pool_path`` returning nothing must not become a match.

    ``expected_path`` is ``None`` in that case, so comparing it against a
    real path has to reject; a mutation that dropped the conditional and
    formatted ``None/<id>.qcow2`` would compare two strings that can never
    be equal and reach the same answer by luck, but one that let ``None ==
    None`` through would accept any row whose new_path was also unset.
    """
    from isardvdi_change_handler.task_results import storage

    pool = MagicMock()
    row = MagicMock(id="s1")
    row.get_storage_pool_path.return_value = None

    with patch.object(storage, "StoragePool") as mock_pool_cls:
        mock_pool_cls.get_by_path.return_value = [pool]

        assert storage._valid_storage_pool(row, "/data/s1.qcow2") is False
