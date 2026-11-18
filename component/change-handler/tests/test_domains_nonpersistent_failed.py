# SPDX-License-Identifier: AGPL-3.0-or-later

from unittest.mock import patch

import pytest

DOMAINS = "isardvdi_change_handler.handlers.domains"


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_nonpersistent_failed_does_not_schedule_delete(
    _parse, scheduler, _logging, desktop_handler, domain_row_factory
):
    """A non-persistent desktop that fails must NOT schedule its own delete."""
    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(
        id="d1",
        status="Failed",
        persistent=False,
        additional_properties={"start_logs_id": "log-1"},
    )
    await desktop_handler.on_update(old, new)

    scheduler.add_nonpersistent_desktop_delete_timeout.assert_not_called()
    assert scheduler.remove_desktop_timeouts.called


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_nonpersistent_stopped_schedules_delete(
    _parse, scheduler, _logging, desktop_handler, domain_row_factory
):
    """A non-persistent desktop that stops still schedules its delete (preserved)."""
    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(
        id="d1",
        status="Stopped",
        persistent=False,
        additional_properties={"start_logs_id": "log-1"},
    )
    await desktop_handler.on_update(old, new)

    scheduler.add_nonpersistent_desktop_delete_timeout.assert_called_once_with("d1")


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_persistent_failed_schedules_nothing(
    _parse, scheduler, _logging, desktop_handler, domain_row_factory
):
    """Control-of-control: a persistent failed desktop schedules no delete."""
    old = domain_row_factory(id="d1", status="Started", persistent=True)
    new = domain_row_factory(
        id="d1",
        status="Failed",
        persistent=True,
        additional_properties={"start_logs_id": "log-1"},
    )
    await desktop_handler.on_update(old, new)

    scheduler.add_nonpersistent_desktop_delete_timeout.assert_not_called()


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_timeouts_removed_without_start_logs_id(
    _parse, scheduler, _logging, desktop_handler, domain_row_factory
):
    """Starting->Failed with no start_logs_id must still clear timeouts.

    old=Starting is outside the earlier unconditional block, so only the
    now-ungated branch can remove them.
    """
    old = domain_row_factory(id="d1", status="Starting", persistent=False)
    new = domain_row_factory(id="d1", status="Failed", persistent=False)
    await desktop_handler.on_update(old, new)

    scheduler.remove_desktop_timeouts.assert_called_once_with("d1")
    scheduler.add_nonpersistent_desktop_delete_timeout.assert_not_called()


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_delete_scheduled_without_start_logs_id(
    _parse, scheduler, _logging, desktop_handler, domain_row_factory
):
    """A non-persistent stop schedules delete even with no start_logs_id."""
    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(id="d1", status="Stopped", persistent=False)
    await desktop_handler.on_update(old, new)

    scheduler.add_nonpersistent_desktop_delete_timeout.assert_called_once_with("d1")


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Scheduler")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
@patch(f"{DOMAINS}.Logging")
async def test_stop_logging_still_requires_start_logs_id(
    logging_, _parse, _scheduler, desktop_handler, domain_row_factory
):
    """Guard: stop logging stays gated by start_logs_id."""
    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(id="d1", status="Stopped", persistent=False)
    await desktop_handler.on_update(old, new)

    logging_.logs_domain_stop_engine.assert_not_called()


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_limit_zero_failed_does_not_destroy(
    _parse, _logging, desktop_handler, domain_row_factory
):
    """The one that matters: limit=0 + Failed must NOT destroy the desktop."""
    from isardvdi_common.helpers.scheduler import Scheduler

    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(
        id="d1",
        status="Failed",
        persistent=False,
        additional_properties={"start_logs_id": "log-1"},
    )
    with patch.object(
        Scheduler, "remove_desktop_timeouts", staticmethod(lambda _id: None)
    ), patch(
        "isardvdi_common.helpers.scheduler.Config.get_config",
        return_value={"nonpersistent_desktops_inactivity_limit": 0},
    ), patch(
        "isardvdi_common.helpers.scheduler."
        "DesktopNonpersistentEvents.desktop_non_persistent_delete"
    ) as destroy:
        await desktop_handler.on_update(old, new)

    destroy.assert_not_called()


@pytest.mark.asyncio
@patch(f"{DOMAINS}.Logging")
@patch(f"{DOMAINS}.DesktopsProcessed._parse_desktop", side_effect=lambda d: d)
async def test_limit_zero_stopped_does_destroy(
    _parse, _logging, desktop_handler, domain_row_factory
):
    """Companion: limit=0 + Stopped DOES destroy — proves the wiring is live."""
    from isardvdi_common.helpers.scheduler import Scheduler

    old = domain_row_factory(id="d1", status="Started", persistent=False)
    new = domain_row_factory(
        id="d1",
        status="Stopped",
        persistent=False,
        additional_properties={"start_logs_id": "log-1"},
    )
    with patch.object(
        Scheduler, "remove_desktop_timeouts", staticmethod(lambda _id: None)
    ), patch(
        "isardvdi_common.helpers.scheduler.Config.get_config",
        return_value={"nonpersistent_desktops_inactivity_limit": 0},
    ), patch(
        "isardvdi_common.helpers.scheduler."
        "DesktopNonpersistentEvents.desktop_non_persistent_delete"
    ) as destroy:
        await desktop_handler.on_update(old, new)

    destroy.assert_called_once_with("d1")
