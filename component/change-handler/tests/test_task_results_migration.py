# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the aggregate ``storage:migration`` emit + its consumer dispatch."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_change_handler.streams import task_results_consumer
from isardvdi_change_handler.task_results import migration


def _item(storage_id, tree_id, kind, state, size=10):
    return {
        "storage_id": storage_id,
        "tree_id": tree_id,
        "kind": kind,
        "state": state,
        "size_bytes": size,
    }


# --------------------------------------------------------------------------- #
# _build_payload — derived aggregate (one row per root tree + job totals)
# --------------------------------------------------------------------------- #
def test_build_payload_aggregates_per_tree_and_totals():
    items = [
        _item("r", "r", "template", "released"),
        _item("d1", "r", "desktop", "released"),
        _item("d2", "r", "desktop", "moving"),
    ]
    fake_sm = MagicMock()
    fake_sm.exists.return_value = True
    fake_sm.return_value = SimpleNamespace(id="mig-1", status="running")
    fake_item = MagicMock()
    fake_item.dicts_by_migration.return_value = items
    with (
        patch.object(migration, "StorageMigration", fake_sm),
        patch.object(migration, "StorageMigrationItem", fake_item),
    ):
        payload = migration._build_payload("mig-1")

    assert payload["id"] == "mig-1"
    assert payload["status"] == "running"
    assert payload["totals"]["items_total"] == 3
    assert payload["totals"]["done"] == 2  # two released
    assert payload["totals"]["bytes_total"] == 30
    assert payload["totals"]["state_counts"]["released"] == 2
    assert len(payload["trees"]) == 1
    tree = payload["trees"][0]
    assert tree["tree_id"] == "r"
    assert tree["desktops"] == 2
    assert tree["done"] == 2


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
