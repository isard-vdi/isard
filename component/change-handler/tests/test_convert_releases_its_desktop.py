# SPDX-License-Identifier: AGPL-3.0-or-later

"""A finished convert hands its source desktop back to ``Stopped`` without the reconcile."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.helpers import qcow2_geometry
from isardvdi_common.models.storage import Storage


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    qcow2_geometry._cached = None
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "5368709120")
    yield
    qcow2_geometry._cached = None


def _bare(storage_id):
    s = Storage.__new__(Storage)
    for k, v in {
        "id": storage_id,
        "directory_path": "/isard/groups",
        "type": "qcow2",
        "user_id": "u1",
        "parent": None,
        "task": None,
    }.items():
        object.__setattr__(s, k, v)
    return s


def _convert_core_steps():
    with (
        patch.object(Storage, "create_task") as create,
        patch.object(Storage, "set_maintenance"),
        patch("isardvdi_common.models.storage.StoragePool") as pool,
    ):
        pool.get_best_for_action.return_value = MagicMock(id="poolA")
        _bare("src").convert(
            user_id="u1",
            new_storage=_bare("dst"),
            new_storage_type="qcow2",
            new_storage_status="ready",
            compress=False,
        )
    dependents = create.call_args.kwargs["dependents"]
    return [d for d in dependents if d["queue"] == "core"]


async def _finish_convert(domains, depending_status="finished"):
    from isardvdi_change_handler.streams.task_results_consumer import _run_handler
    from isardvdi_change_handler.task_results import storage

    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        S.exists.return_value = True
        S.return_value.domains = domains
        S.write_status.return_value = "ready"
        for step in _convert_core_steps():
            task = SimpleNamespace(
                id="t1",
                user_id="u1",
                task=step["task"],
                queue=step["queue"],
                depending_status=depending_status,
                dependencies=[],
                kwargs=step.get("job_kwargs", {}).get("kwargs", {}),
            )
            assert await _run_handler(AsyncMock(), task)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["finished", "failed", "canceled"])
async def test_the_convert_chain_returns_its_desktop_to_stopped(outcome):
    desktop = SimpleNamespace(status="Maintenance", current_action="convert")

    await _finish_convert([desktop], depending_status=outcome)

    assert desktop.status == "Stopped"
    assert desktop.current_action is None


@pytest.mark.asyncio
async def test_a_domain_another_action_parked_is_left_alone():
    other = SimpleNamespace(status="Maintenance", current_action="move")
    started = SimpleNamespace(status="Started", current_action=None)

    await _finish_convert([other, started])

    assert (other.status, other.current_action) == ("Maintenance", "move")
    assert (started.status, started.current_action) == ("Started", None)


def test_the_release_step_skips_a_finished_chain_unless_always():
    from isardvdi_change_handler.task_results import storage

    desktop = SimpleNamespace(status="Maintenance", current_action="resize")
    task = SimpleNamespace(id="t1", user_id="u1", depending_status="finished")
    with patch.object(storage, "Storage") as S:
        S.exists.return_value = True
        S.return_value.domains = [desktop]
        storage.handle_release_maintenance(task, storage_id="s1", action="resize")

    assert desktop.status == "Maintenance"
