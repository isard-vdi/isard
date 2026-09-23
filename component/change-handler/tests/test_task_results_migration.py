# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the aggregate ``storage:migration`` emit + its consumer dispatch."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_change_handler.streams import task_results_consumer
from isardvdi_change_handler.task_results import migration


# --------------------------------------------------------------------------- #
# _build_payload — lean job summary (persisted totals, NO per-tree list, no items)
# --------------------------------------------------------------------------- #
def test_build_payload_is_lean_job_summary_no_trees():
    # built from the job row's persisted totals; the socket no longer ships the
    # per-tree list (thousands of trees) — the webapp pulls those from /trees.
    fake_sm = MagicMock()
    fake_sm.exists.return_value = True
    fake_sm.return_value = SimpleNamespace(
        id="mig-1",
        status="running",
        totals={
            "items_total": 3,
            "bytes_total": 30,
            "bytes_done": 20,
            "done": 2,
            "state_counts": {"released": 2, "moving": 1},
        },
    )
    with patch.object(migration, "StorageMigration", fake_sm):
        payload = migration._build_payload("mig-1")

    assert payload["id"] == "mig-1"
    assert payload["status"] == "running"
    assert payload["totals"]["items_total"] == 3
    assert payload["totals"]["done"] == 2
    assert payload["state_counts"]["released"] == 2
    assert "trees" not in payload  # the socket no longer carries the tree list
    assert "items" not in payload


def test_build_payload_missing_migration_returns_none():
    with patch.object(migration.StorageMigration, "exists", return_value=False):
        assert migration._build_payload("ghost") is None


# --------------------------------------------------------------------------- #
# send_migration_socket — admin-room broadcast (modeled on send_status_socket)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_send_migration_socket_emits_to_admins():
    redis_manager = AsyncMock()
    payload = {"id": "mig-1", "status": "running", "totals": {}, "trees": []}
    with patch.object(migration, "_build_payload", return_value=payload):
        await migration.send_migration_socket(redis_manager, "mig-1")

    redis_manager.emit.assert_awaited_once()
    args, kwargs = redis_manager.emit.call_args
    assert args[0] == "storage:migration"
    assert json.loads(args[1])["id"] == "mig-1"
    assert kwargs["namespace"] == "/administrators"
    assert kwargs["room"] == "admins"


@pytest.mark.asyncio
async def test_send_migration_socket_noop_when_payload_none():
    redis_manager = AsyncMock()
    with patch.object(migration, "_build_payload", return_value=None):
        await migration.send_migration_socket(redis_manager, "ghost")
    redis_manager.emit.assert_not_awaited()


# --------------------------------------------------------------------------- #
# consumer dispatch — kind=migration routes to send_migration_socket
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_process_entry_migration_kind_dispatches():
    redis_manager = AsyncMock()
    with patch.object(
        task_results_consumer, "send_migration_socket", new=AsyncMock()
    ) as mock_send:
        acked = await task_results_consumer._process_entry(
            redis_manager, {"kind": "migration", "migration_id": "mig-1"}
        )
    assert acked is True
    mock_send.assert_awaited_once_with(redis_manager, "mig-1")


@pytest.mark.asyncio
async def test_process_entry_migration_kind_without_id_acks():
    redis_manager = AsyncMock()
    with patch.object(
        task_results_consumer, "send_migration_socket", new=AsyncMock()
    ) as mock_send:
        acked = await task_results_consumer._process_entry(
            redis_manager, {"kind": "migration"}
        )
    assert acked is True
    mock_send.assert_not_awaited()
