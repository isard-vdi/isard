# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for RecycleBinService — delegates to common helpers and
queues async deletes. Tests pin the not-found dispatch + the queue
enqueue payload shape.
"""

from unittest.mock import AsyncMock, patch

import pytest
from api.services.error import Error
from api.services.recycle_bin import RecycleBinService


class TestGetUserCutoffTime:
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_category_recycle_bin_cuttoff_time",
        return_value=86400,
    )
    @patch("api.services.recycle_bin.RethinkCategory.exists", return_value=True)
    def test_returns_helper_value(self, _exists, mock_get):
        assert RecycleBinService.get_user_cutoff_time("default") == 86400
        mock_get.assert_called_once_with(category_id="default")

    @patch("api.services.recycle_bin.RethinkCategory.exists", return_value=False)
    def test_raises_not_found_for_missing_category(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.get_user_cutoff_time("ghost")


class TestGetRecycleBinEntryDetails:
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get",
        return_value={"id": "rb1", "items": []},
    )
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    def test_forwards_all_data_flag(self, _exists, mock_get):
        RecycleBinService.get_recycle_bin_entry_details("rb1", all_data=True)
        mock_get.assert_called_once_with(recycle_bin_id="rb1", all_data=True)

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.get_recycle_bin_entry_details("ghost")


class TestRestoreRecycleBinEntry:
    @patch("api.services.recycle_bin.CommonRecycleBin")
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    def test_calls_restore_on_common(self, _exists, mock_common):
        instance = mock_common.return_value
        instance.restore.return_value = "restore-task-1"
        result = RecycleBinService.restore_recycle_bin_entry("rb1")
        mock_common.assert_called_once_with("rb1")
        instance.restore.assert_called_once_with()
        assert result == "restore-task-1"

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.restore_recycle_bin_entry("ghost")


class TestBulkRestore:
    """Commit 695852b09 wraps the sync per-item restore loop in
    ``asyncio.to_thread`` so the asyncio event loop stays free during
    a multi-item restore. The service is fire-and-forget: it returns
    the IDs immediately and the actual work happens in a background
    task. Pin both halves of the contract.
    """

    async def test_returns_ids_immediately(self):
        """``bulk_restore`` must NOT block on the per-item work — it
        returns the ID list synchronously after scheduling the task."""
        with patch("api.services.recycle_bin.CommonRecycleBin"):
            ids = ["rb-1", "rb-2", "rb-3"]
            result = await RecycleBinService.bulk_restore(ids, "u-1")
            assert result == ids

    async def test_schedules_work_via_create_task(self, monkeypatch):
        """The work goes through ``asyncio.create_task(asyncio.to_thread(...))``.
        Pin so a refactor that drops the create_task / to_thread wrap
        and runs the loop body inline (which would block the event
        loop on every restore) fails this test."""
        import asyncio as _asyncio

        captured = {}
        original_create_task = _asyncio.create_task

        def spy_create_task(coro_or_future, *args, **kwargs):
            captured["scheduled"] = True
            return original_create_task(coro_or_future, *args, **kwargs)

        monkeypatch.setattr("asyncio.create_task", spy_create_task)
        with patch("api.services.recycle_bin.CommonRecycleBin"):
            await RecycleBinService.bulk_restore(["rb-1"], "u-1")
        assert captured.get("scheduled") is True

    async def test_empty_ids_still_returns_list(self):
        """Edge case: empty ID list must still succeed (no work to do)."""
        result = await RecycleBinService.bulk_restore([], "u-1")
        assert result == []


class TestDeleteRecycleBinEntry:
    @patch("api.services.recycle_bin.RethinkUser.exists", return_value=True)
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    async def test_enqueues_delete_action(self, _rb, _user):
        with patch("api.services.recycle_bin.RecycleBinDeleteQueue") as mock_q:
            instance = mock_q.return_value
            instance.enqueue = AsyncMock()
            await RecycleBinService.delete_recycle_bin_entry("rb1", "u1")
            instance.enqueue.assert_awaited_once_with(
                {"action": "delete", "recycle_bin_id": "rb1", "user_id": "u1"}
            )

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    async def test_raises_not_found_for_missing_entry(self, _rb):
        with pytest.raises(Error):
            await RecycleBinService.delete_recycle_bin_entry("ghost", "u1")

    @patch("api.services.recycle_bin.RethinkUser.exists", return_value=False)
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    async def test_raises_not_found_for_missing_user(self, _rb, _user):
        with pytest.raises(Error):
            await RecycleBinService.delete_recycle_bin_entry("rb1", "ghost")


class TestRecycleUnusedItems:
    """Pin the scheduler-driven entry point for the nightly
    ``recycle_bin_add_unused_items`` job. Apiv3 parity:
    ``main:api/src/api/views/RecycleBinView.py:599-672``. Pre-fix this
    method did not exist on ``RecycleBinService`` and the route swallowed
    the resulting ``AttributeError``, so the job had been a silent no-op
    for the entire apiv4-integration cutover."""

    @patch("api.services.recycle_bin.NotificationsDataProcessed.add_notification_data")
    @patch(
        "api.services.recycle_bin.NotificationsActionProcessed.get_notification_action",
        return_value={"kwargs": ["name"]},
    )
    @patch(
        "api.services.recycle_bin.NotificationsProcessed.get_notifications_by_action_id",
        return_value=[{"id": "n1", "trigger": True, "action_id": "a1"}],
    )
    @patch(
        "api.services.recycle_bin.DeploymentsProcessed.get_unused_deployments",
        return_value=[],
    )
    @patch(
        "api.services.recycle_bin.DesktopsProcessed.get_unused_desktops",
        return_value=[
            {"id": "d-1", "user": "u-1", "name": "alpha"},
            {"id": "d-2", "user": "u-2", "name": "beta"},
            {"id": "d-3", "user": "u-1", "name": "gamma"},
        ],
    )
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_recycle_bin_cuttoff_time",
        return_value=24,
    )
    @patch("api.services.recycle_bin.DesktopEvents.desktop_delete")
    @patch("api.services.recycle_bin.DesktopEvents.deployment_delete")
    def test_recycles_each_unused_desktop(
        self,
        mock_deployment_delete,
        mock_desktop_delete,
        _cutoff,
        _desktops,
        _deployments,
        _notif_lookup,
        _action_lookup,
        mock_add_notification_data,
    ):
        RecycleBinService.recycle_unused_items()
        # Pre-fix the route swallowed AttributeError so this was 0; pin
        # at exactly len(unused_desktops).
        assert mock_desktop_delete.call_count == 3
        for call in mock_desktop_delete.call_args_list:
            assert call.args[1] == "isard-scheduler"
        # No deployments returned, so deployment_delete must NOT be called.
        assert mock_deployment_delete.call_count == 0
        # Notifications written exactly once with the desktop batch.
        mock_add_notification_data.assert_called_once()
        notification_data = mock_add_notification_data.call_args.args[0]
        assert len(notification_data) == 3
        assert {n["item_id"] for n in notification_data} == {"d-1", "d-2", "d-3"}
        assert all(n["item_type"] == "desktop" for n in notification_data)
        assert all(n["notification_id"] == "n1" for n in notification_data)
        # ``vars`` extracts only the keys named in ``action.kwargs`` from
        # the desktop row. With ``kwargs=["name"]`` and per-desktop
        # ``name`` fields ``alpha`` / ``beta`` / ``gamma`` we expect
        # exact-shape matches.
        names_by_id = {"d-1": "alpha", "d-2": "beta", "d-3": "gamma"}
        for n in notification_data:
            assert n["vars"] == {"name": names_by_id[n["item_id"]]}

    @patch("api.services.recycle_bin.NotificationsDataProcessed.add_notification_data")
    @patch(
        "api.services.recycle_bin.NotificationsActionProcessed.get_notification_action",
        return_value={"kwargs": ["name"]},
    )
    @patch(
        "api.services.recycle_bin.NotificationsProcessed.get_notifications_by_action_id",
        side_effect=[
            [],  # no unused_desktops notification
            [{"id": "n2", "trigger": True, "action_id": "a2"}],
        ],
    )
    @patch(
        "api.services.recycle_bin.DeploymentsProcessed.get_unused_deployments",
        return_value=[
            {"id": "dep-1", "user": "u-1", "co_owners": ["u-2"], "name": "delta"},
            {"id": "dep-2", "user": "u-3", "co_owners": [], "name": "epsilon"},
        ],
    )
    @patch(
        "api.services.recycle_bin.DesktopsProcessed.get_unused_desktops",
        return_value=[],
    )
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_recycle_bin_cuttoff_time",
        return_value=12,
    )
    @patch("api.services.recycle_bin.DesktopEvents.desktop_delete")
    @patch("api.services.recycle_bin.DesktopEvents.deployment_delete")
    def test_recycles_each_unused_deployment_and_notifies_co_owners(
        self,
        mock_deployment_delete,
        mock_desktop_delete,
        _cutoff,
        _desktops,
        _deployments,
        _notif_lookup,
        _action_lookup,
        mock_add_notification_data,
    ):
        RecycleBinService.recycle_unused_items()
        assert mock_desktop_delete.call_count == 0
        # Pre-fix the route had no deployments branch at all; pin per-id call.
        assert mock_deployment_delete.call_count == 2
        for call in mock_deployment_delete.call_args_list:
            assert call.args[1] == "isard-scheduler"
        # Notifications: dep-1 owner + 1 co_owner (2 rows), dep-2 owner only (1 row).
        mock_add_notification_data.assert_called_once()
        notification_data = mock_add_notification_data.call_args.args[0]
        assert len(notification_data) == 3
        users = sorted(n["user_id"] for n in notification_data)
        assert users == ["u-1", "u-2", "u-3"]
        assert all(n["item_type"] == "deployment" for n in notification_data)

    @patch("api.services.recycle_bin.NotificationsDataProcessed.add_notification_data")
    @patch(
        "api.services.recycle_bin.NotificationsActionProcessed.get_notification_action",
    )
    @patch(
        "api.services.recycle_bin.NotificationsProcessed.get_notifications_by_action_id",
        return_value=[],
    )
    @patch(
        "api.services.recycle_bin.DeploymentsProcessed.get_unused_deployments",
        return_value=[],
    )
    @patch(
        "api.services.recycle_bin.DesktopsProcessed.get_unused_desktops",
        return_value=[{"id": "d-1", "user": "u-1"}],
    )
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_recycle_bin_cuttoff_time",
        return_value=24,
    )
    @patch("api.services.recycle_bin.DesktopEvents.desktop_delete")
    @patch("api.services.recycle_bin.DesktopEvents.deployment_delete")
    def test_no_notifications_when_action_disabled(
        self,
        mock_deployment_delete,
        mock_desktop_delete,
        _cutoff,
        _desktops,
        _deployments,
        _notif_lookup,
        _action_lookup,
        mock_add_notification_data,
    ):
        # Apiv3 contract: when no notification is configured for the
        # action, recycle still happens but no notification rows are
        # written. Pin so a future refactor that requires a notification
        # to recycle doesn't silently break the cron.
        RecycleBinService.recycle_unused_items()
        assert mock_desktop_delete.call_count == 1
        mock_add_notification_data.assert_not_called()
        _action_lookup.assert_not_called()

    @patch("api.services.recycle_bin.NotificationsDataProcessed.add_notification_data")
    @patch(
        "api.services.recycle_bin.NotificationsActionProcessed.get_notification_action",
    )
    @patch(
        "api.services.recycle_bin.NotificationsProcessed.get_notifications_by_action_id",
        return_value=[{"id": "n1", "trigger": False, "action_id": "a1"}],
    )
    @patch(
        "api.services.recycle_bin.DeploymentsProcessed.get_unused_deployments",
        return_value=[],
    )
    @patch(
        "api.services.recycle_bin.DesktopsProcessed.get_unused_desktops",
        return_value=[{"id": "d-1", "user": "u-1"}],
    )
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_recycle_bin_cuttoff_time",
        return_value=24,
    )
    @patch("api.services.recycle_bin.DesktopEvents.desktop_delete")
    @patch("api.services.recycle_bin.DesktopEvents.deployment_delete")
    def test_no_notifications_when_trigger_false(
        self,
        mock_deployment_delete,
        mock_desktop_delete,
        _cutoff,
        _desktops,
        _deployments,
        _notif_lookup,
        _action_lookup,
        mock_add_notification_data,
    ):
        RecycleBinService.recycle_unused_items()
        assert mock_desktop_delete.call_count == 1
        mock_add_notification_data.assert_not_called()


class TestCreateUnusedItemTimeoutRule:
    """Apiv3 ``Cerberus`` set ``id`` via ``default_setter: genuuid`` and
    ``allowed`` via ``default: {}``. The webapp form sends neither.
    Pin the service-side defaults so the webapp create succeeds and the
    response carries a usable id."""

    @patch("api.services.recycle_bin.CommonRecycleBin.create_unused_item_timeout")
    def test_generates_id_when_not_provided(self, mock_create):
        result = RecycleBinService.create_unused_item_timeout_rule(
            {
                "name": "Old desktops",
                "description": "",
                "op": "send_unused_desktops_to_recycle_bin",
                "cutoff_time": 720,
                "priority": 10,
            }
        )
        # Returned id MUST be a non-empty UUID (not the empty string the
        # pre-fix path returned via ``data.get("id", "")``).
        assert result
        assert isinstance(result, str)
        assert len(result) >= 32  # uuid4 string form is 36 chars
        # Helper called with the same dict, now augmented with id+allowed.
        mock_create.assert_called_once()
        forwarded = mock_create.call_args.args[0]
        assert forwarded["id"] == result
        assert forwarded["allowed"] == {}

    @patch("api.services.recycle_bin.CommonRecycleBin.create_unused_item_timeout")
    def test_keeps_caller_supplied_id(self, mock_create):
        result = RecycleBinService.create_unused_item_timeout_rule(
            {"id": "rule-fixed", "name": "x", "op": "y", "priority": 0}
        )
        assert result == "rule-fixed"
        mock_create.assert_called_once()
        assert mock_create.call_args.args[0]["id"] == "rule-fixed"

    @patch("api.services.recycle_bin.CommonRecycleBin.create_unused_item_timeout")
    def test_keeps_caller_supplied_allowed(self, mock_create):
        custom_allowed = {
            "categories": ["cat-1"],
            "groups": False,
            "roles": False,
            "users": False,
        }
        RecycleBinService.create_unused_item_timeout_rule(
            {
                "name": "x",
                "op": "y",
                "priority": 0,
                "allowed": custom_allowed,
            }
        )
        forwarded = mock_create.call_args.args[0]
        assert forwarded["allowed"] == custom_allowed
