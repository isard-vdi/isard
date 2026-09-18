# SPDX-License-Identifier: AGPL-3.0-or-later

"""``handle_storage_update_pool`` - which copy on disk the row ends up on.

The find task reports every file it matched; this handler decides which
one is the row's real disk, which are duplicates worth recording, and
whether the row should be marked ``deleted`` because none of them is
usable. Two of those outcomes are destructive and neither had a test:

* falling through every classification marks the row ``deleted``, so a
  classification that wrongly rejects the live copy deletes a row whose
  file is on disk;
* a ``recycled`` row must not be flipped back to ``ready`` just because
  the file it points at looks ready - it would leave the recycle bin
  without anyone asking.

The duplicate ordering matters for the same reason: the row adopts the
first entry after the sort, so reversing it points the row at the
oldest copy while every count stays identical.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _found(path, *, status="ready", mtime=100, virtual_size=1024):
    return {
        "path": path,
        "mtime": mtime,
        "storage_data": {
            "status": status,
            "qemu-img-info": {"virtual-size": virtual_size},
        },
    }


def _task(matching_files, *, depending_status="finished", result_status=None):
    result = {"matching_files": matching_files}
    if result_status is not None:
        result["status"] = result_status
    dependency = SimpleNamespace(task="find", result=result)
    return SimpleNamespace(
        id="t1",
        user_id="u1",
        depending_status=depending_status,
        dependencies=[dependency],
    )


async def _run(row, task, *, pool_for=None, owner=False):
    """Run the handler and return (applied_payload_or_None, emitted_status)."""
    from isardvdi_change_handler.task_results import storage

    default_pool = MagicMock(name="pool")
    table = pool_for or {}

    with (
        patch.object(storage, "Storage") as mock_storage_cls,
        patch.object(
            storage,
            "_valid_storage_pool",
            side_effect=lambda _row, path: table.get(path, default_pool),
        ),
        patch.object(
            storage,
            "_apply_storage_update",
            side_effect=lambda payload, **_: payload["status"],
        ) as mock_apply,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as mock_send,
    ):
        mock_storage_cls.exists.return_value = True
        mock_storage_cls.return_value = row
        kwargs = {"owner": True} if owner else {}
        await storage.handle_storage_update_pool(AsyncMock(), task, "s1", **kwargs)

    applied = mock_apply.call_args.args[0] if mock_apply.call_args else None
    if mock_apply.call_args:
        assert mock_apply.call_args.kwargs["observer"] is not owner
    emitted = mock_send.await_args.args[2] if mock_send.await_args else None
    return applied, emitted


def _row(path="/pool/s1.qcow2", status="ready"):
    return MagicMock(id="s1", path=path, status=status)


# ---------------------------------------------------------------------------
# the guards before any classification happens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unfinished_chain_does_not_touch_the_row():
    applied, emitted = await _run(
        _row(), _task([_found("/pool/s1.qcow2")], depending_status="failed")
    )
    assert applied is None and emitted is None


@pytest.mark.asyncio
async def test_an_empty_find_leaves_the_row_alone_unless_it_said_deleted():
    """No matches is not the same as "the file is gone".

    The find can come back empty because the pool was unreachable. Only
    the explicit ``deleted`` result is allowed to mark the row.
    """
    applied, emitted = await _run(_row(), _task([]))
    assert applied is None and emitted is None


@pytest.mark.asyncio
async def test_an_empty_find_that_reported_deleted_marks_the_row_deleted():
    applied, emitted = await _run(_row(), _task([], result_status="deleted"))
    assert applied["status"] == "deleted"
    assert emitted == "deleted"


# ---------------------------------------------------------------------------
# the destructive fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_row_whose_every_copy_is_unusable_is_marked_deleted():
    """All candidates rejected means there is nothing to point at."""
    applied, emitted = await _run(
        _row(), _task([_found("/pool/s1.qcow2", virtual_size=0)])
    )
    assert applied["status"] == "deleted"
    assert emitted == "deleted"
    assert applied["storages_with_uuid"] == [
        {"status": "invalid", "path": "/pool/s1.qcow2"}
    ]


@pytest.mark.asyncio
async def test_a_zero_sized_file_is_invalid_not_a_candidate():
    """A qcow2 whose virtual-size is 0 is a stub, not the disk."""
    applied, _ = await _run(
        _row(),
        _task([_found("/pool/s1.qcow2", virtual_size=0), _found("/other/s1.qcow2")]),
    )
    assert applied["status"] != "deleted"
    assert {"status": "invalid", "path": "/pool/s1.qcow2"} in applied[
        "storages_with_uuid"
    ]


@pytest.mark.asyncio
async def test_a_file_under_deleted_is_classified_move_deleted_not_adopted():
    applied, _ = await _run(
        _row(), _task([_found("/pool/deleted/s1.qcow2"), _found("/pool/s1.qcow2")])
    )
    assert {"status": "move_deleted", "path": "/pool/deleted/s1.qcow2"} in applied[
        "storages_with_uuid"
    ]


# ---------------------------------------------------------------------------
# the recycled guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_recycled_row_is_not_resurrected_by_a_ready_looking_file():
    """The file on disk says ready because nothing rewrites it when a row
    is recycled. Adopting that status pulls the disk back out of the
    recycle bin without anyone asking for it."""
    row = _row(status="recycled")
    applied, emitted = await _run(
        row, _task([_found("/pool/s1.qcow2", status="ready")])
    )
    assert applied["status"] == "recycled"
    assert emitted == "recycled"


@pytest.mark.asyncio
async def test_a_non_ready_status_on_disk_is_still_adopted_over_recycled():
    """The handler passes the file's status on; the write itself keeps a
    recycled row recycled whatever the reading says."""
    row = _row(status="recycled")
    applied, _ = await _run(
        row, _task([_found("/pool/s1.qcow2", status="maintenance")])
    )
    assert applied["status"] == "maintenance"


# ---------------------------------------------------------------------------
# which duplicate wins
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_most_recent_copy_is_the_one_adopted():
    """The row adopts the first entry after the sort, so the ordering is
    the decision. The older copy is recorded as a duplicate, not lost."""
    row = _row(path="/nowhere/s1.qcow2")
    applied, _ = await _run(
        row,
        _task(
            [
                _found("/old/s1.qcow2", mtime=100, status="maintenance"),
                _found("/new/s1.qcow2", mtime=900, status="ready"),
            ]
        ),
    )
    assert applied["status"] == "ready"
    assert {"status": "duplicated", "path": "/old/s1.qcow2"} in applied[
        "storages_with_uuid"
    ]


@pytest.mark.asyncio
async def test_the_row_own_path_wins_when_it_is_also_the_newest():
    """When the row already points at the newest copy nothing moves, and
    the copy it adopted is not also listed as one of its duplicates."""
    row = _row(path="/pool/s1.qcow2", status="ready")
    applied, _ = await _run(
        row,
        _task(
            [
                _found("/pool/s1.qcow2", mtime=900),
                _found("/old/s1.qcow2", mtime=100),
            ]
        ),
    )
    paths = [e["path"] for e in applied["storages_with_uuid"]]
    assert "/pool/s1.qcow2" not in paths
    assert "/old/s1.qcow2" in paths


@pytest.mark.asyncio
async def test_a_copy_a_pool_does_not_claim_is_recorded_not_adopted():
    """``not_in_pool`` and ``bad_path`` are kept apart because they mean
    different things - no pool owns the directory, versus a pool owns it
    but the filename is not the one it would have written."""
    applied, _ = await _run(
        _row(path="/nowhere/s1.qcow2"),
        _task(
            [
                _found("/unclaimed/s1.qcow2"),
                _found("/claimed/s1.qcow2"),
                _found("/good/s1.qcow2"),
            ]
        ),
        pool_for={"/unclaimed/s1.qcow2": None, "/claimed/s1.qcow2": False},
    )
    entries = applied["storages_with_uuid"]
    assert {"status": "not_in_pool", "path": "/unclaimed/s1.qcow2"} in entries
    assert {"status": "bad_path", "path": "/claimed/s1.qcow2"} in entries


@pytest.mark.asyncio
async def test_a_row_a_chain_holds_is_not_moved_to_another_copy():
    row = _row(path="/nowhere/s1.qcow2", status="maintenance")
    applied, emitted = await _run(row, _task([_found("/new/s1.qcow2")]))
    assert applied is None and emitted is None
    row.set_storage_pool.assert_not_called()


# ---------------------------------------------------------------------------
# the chain that parks the row (set_path, delete_path) is its owner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_owner_chain_releases_the_row_on_its_own_copy():
    row = _row(status="maintenance")
    applied, emitted = await _run(row, _task([_found("/pool/s1.qcow2")]), owner=True)
    assert applied["status"] == "ready" and emitted == "ready"


@pytest.mark.asyncio
async def test_the_owner_chain_moves_the_row_to_the_newest_copy():
    row = _row(path="/nowhere/s1.qcow2", status="maintenance")
    applied, emitted = await _run(row, _task([_found("/new/s1.qcow2")]), owner=True)
    assert applied["status"] == "ready" and emitted == "ready"
    row.set_storage_pool.assert_called_once()


@pytest.mark.asyncio
async def test_the_owner_chain_marks_the_row_deleted_when_no_copy_is_left():
    row = _row(status="maintenance")
    applied, _ = await _run(row, _task([], result_status="deleted"), owner=True)
    assert applied["status"] == "deleted"


# the row's own path is the disk, wherever that directory is


@pytest.mark.asyncio
async def test_the_live_copy_at_the_rows_own_path_is_adopted_outside_pool_paths():
    """A file at the row's own path, even ``bad_path``, is adopted, not deleted."""
    row = _row(path="/isard/groups/templates2/s1.qcow2", status="ready")
    applied, emitted = await _run(
        row,
        _task([_found("/isard/groups/templates2/s1.qcow2", status="ready")]),
        pool_for={"/isard/groups/templates2/s1.qcow2": False},
    )
    assert applied["status"] == "ready"
    assert emitted == "ready"
    assert applied["qemu-img-info"] == {"virtual-size": 1024}
    assert applied["storages_with_uuid"] == [
        {"status": "bad_path", "path": "/isard/groups/templates2/s1.qcow2"}
    ]


@pytest.mark.asyncio
async def test_the_rows_own_path_is_adopted_even_when_no_pool_claims_it():
    """The same when no pool owns the directory at all (``not_in_pool``)."""
    row = _row(path="/mnt/legacy/s1.qcow2", status="ready")
    applied, emitted = await _run(
        row,
        _task([_found("/mnt/legacy/s1.qcow2", status="ready")]),
        pool_for={"/mnt/legacy/s1.qcow2": None},
    )
    assert applied["status"] == "ready"
    assert emitted == "ready"
    assert applied["storages_with_uuid"] == [
        {"status": "not_in_pool", "path": "/mnt/legacy/s1.qcow2"}
    ]


@pytest.mark.asyncio
async def test_a_recycled_row_stays_recycled_when_adopted_from_its_own_path():
    """The recycled guard applies on this branch too."""
    row = _row(path="/isard/groups/templates2/s1.qcow2", status="recycled")
    applied, _ = await _run(
        row,
        _task([_found("/isard/groups/templates2/s1.qcow2", status="ready")]),
        pool_for={"/isard/groups/templates2/s1.qcow2": False},
    )
    assert applied["status"] == "recycled"


@pytest.mark.asyncio
async def test_the_owner_chain_releases_its_row_adopted_from_outside_pool_paths():
    """The chain holding the row writes with its authority on this branch too."""
    row = _row(path="/isard/groups/templates2/s1.qcow2", status="maintenance")
    applied, emitted = await _run(
        row,
        _task([_found("/isard/groups/templates2/s1.qcow2", status="ready")]),
        pool_for={"/isard/groups/templates2/s1.qcow2": False},
        owner=True,
    )
    assert applied["status"] == "ready" and emitted == "ready"
