# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for AdminStorageService.reconcile_pools and its response contract."""

from unittest.mock import patch

from api.services.admin.storage import AdminStorageService


@patch("api.services.admin.storage.StoragePoolsProcessed")
def test_reports_count_and_forwards_tasks(mock_pools):
    tasks = [
        {"pool": "p1", "path": "/isard", "task_id": "t1"},
        {"pool": "p2", "path": "/mnt/b", "task_id": "t2"},
    ]
    mock_pools.enqueue_reconciles.return_value = tasks

    result = AdminStorageService.reconcile_pools(apply=False)

    mock_pools.enqueue_reconciles.assert_called_once_with(apply=False)
    assert result["enqueued"] == 2  # len of what was enqueued, not a pool total
    assert result["apply"] is False
    assert result["tasks"] == tasks


@patch("api.services.admin.storage.StoragePoolsProcessed")
def test_apply_flag_is_carried_through(mock_pools):
    mock_pools.enqueue_reconciles.return_value = []
    result = AdminStorageService.reconcile_pools(apply=True)
    mock_pools.enqueue_reconciles.assert_called_once_with(apply=True)
    assert result["apply"] is True
    assert result["enqueued"] == 0  # nothing enqueued -> count is zero, not an error
