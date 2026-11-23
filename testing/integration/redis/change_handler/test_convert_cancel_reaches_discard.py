# SPDX-License-Identifier: AGPL-3.0-or-later

"""A cancelled convert chain reaches ``convert_discard_destination`` on a real rq graph."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.models import storage as storage_model
from isardvdi_common.models.task import Task

from .._chain_harness import canceled_event

SOURCE_STORAGE_ID = "test-convert-source-1"
DEST_STORAGE_ID = "test-convert-dest-1"
SOURCE_PATH = f"/isard/groups/u/{SOURCE_STORAGE_ID}.qcow2"
DEST_PATH = f"/isard/groups/u/{DEST_STORAGE_ID}.vmdk"

CORE_STEPS = ("storage_update", "update_status", "convert_discard_destination")


def convert_chain_kwargs():
    """The chain ``Storage.convert`` builds; only ``create_task`` is replaced."""
    origin = SimpleNamespace(
        id=SOURCE_STORAGE_ID,
        path=SOURCE_PATH,
        directory_path="/isard/groups/u",
        set_maintenance=MagicMock(),
        create_task=MagicMock(return_value="unused"),
    )
    destination = SimpleNamespace(
        id=DEST_STORAGE_ID, path=DEST_PATH, directory_path="/isard/groups/u"
    )
    with (
        patch.object(
            storage_model.StoragePool,
            "get_best_for_action",
            return_value=SimpleNamespace(id="default"),
        ),
        patch.object(
            storage_model.qcow2_geometry,
            "policy",
            return_value=storage_model.qcow2_geometry.from_env({}),
        ),
        patch.object(storage_model, "storage_min_free_bytes", return_value=0),
    ):
        storage_model.Storage.convert(
            origin, "test-user", destination, "vmdk", "ready", False
        )
    kwargs = dict(origin.create_task.call_args.kwargs)
    kwargs.pop("blocking", None)
    kwargs.setdefault("storage_id", SOURCE_STORAGE_ID)
    kwargs.setdefault("index_owners", [SOURCE_STORAGE_ID])
    return kwargs


def _recorders(ran, real=None):
    """Recorders for every core step, except those named in ``real``."""

    def make(name):
        def handler(step, **kwargs):
            ran.append((name, step.depending_status, kwargs))

        return handler

    handlers = {name: (make(name), False) for name in CORE_STEPS}
    handlers.update(real or {})
    return handlers


async def _cancel_and_dispatch(connection, root, handlers):
    from isardvdi_change_handler.streams import task_results_consumer

    root.cancel()
    with (
        patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
        patch.object(task_results_consumer, "HANDLERS", handlers),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(), canceled_event(connection)
        )


@pytest.mark.asyncio
async def test_a_cancelled_convert_reaches_the_discard_step(task_on_scratch_redis):
    """a main: the chain has no discard step, so the written file stays in the pool."""
    ran = []
    root = Task(**convert_chain_kwargs())
    await _cancel_and_dispatch(task_on_scratch_redis, root, _recorders(ran))

    dispatched = [name for name, _status, _kwargs in ran]
    assert "convert_discard_destination" in dispatched, (
        "the cancelled convert never reached convert_discard_destination; "
        f"it dispatched only {dispatched}"
    )
    discard = next(entry for entry in ran if entry[0] == "convert_discard_destination")
    assert discard[2] == {
        "storage_id": DEST_STORAGE_ID,
        "path": DEST_PATH,
    }, f"expected the destination's id and path, got {discard[2]}"
    assert (
        discard[1] != "finished"
    ), f"the discard step read depending_status={discard[1]!r} after a cancel"
    assert (
        "update_status" in dispatched
    ), f"update_status was not dispatched next to the discard: {dispatched}"


@pytest.mark.asyncio
async def test_the_real_discard_handler_queues_a_delete_of_the_destination(
    task_on_scratch_redis,
):
    """a main: no handler is registered, so nothing deletes the destination file."""
    from isardvdi_change_handler.task_results import registry
    from isardvdi_change_handler.task_results import storage as storage_results

    entry = registry.HANDLERS.get("convert_discard_destination")
    assert entry is not None, "no handler is registered for convert_discard_destination"

    destination_row = MagicMock(
        path=DEST_PATH,
        status="creating",
        domains=[],
        directory_path="/isard/groups/u",
    )
    storage_cls = MagicMock(return_value=destination_row)
    storage_cls.exists.return_value = True
    pool_cls = MagicMock()
    pool_cls.get_best_for_action.return_value = SimpleNamespace(id="default")
    pool_cls.mountpoint_for_path.return_value = "/isard"

    ran = []
    root = Task(**convert_chain_kwargs())
    with (
        patch.object(storage_results, "Storage", storage_cls),
        patch.object(storage_results, "StoragePool", pool_cls),
    ):
        await _cancel_and_dispatch(
            task_on_scratch_redis,
            root,
            _recorders(ran, real={"convert_discard_destination": entry}),
        )

    storage_cls.assert_called_with(DEST_STORAGE_ID)
    calls = destination_row.create_task.call_args_list
    assert (
        len(calls) == 1
    ), f"expected one delete queued for the destination, got {len(calls)}: {calls}"
    queued = calls[0].kwargs
    assert queued["task"] == "delete", f"queued {queued['task']!r}, not delete"
    assert (
        queued["job_kwargs"]["kwargs"]["path"] == DEST_PATH
    ), f"the delete targets {queued['job_kwargs']['kwargs']}, not {DEST_PATH}"
