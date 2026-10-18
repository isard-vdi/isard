# SPDX-License-Identifier: AGPL-3.0-or-later

"""A reading with ``open_error`` keeps the row's status and flags review_damage."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_ERROR = "qemu-img: Could not open '/pool/s1.qcow2': Permission denied"


def _task(dependencies):
    return SimpleNamespace(
        id="t1", user_id="u1", depending_status="finished", dependencies=dependencies
    )


async def _update(result, *, row_status="ready", observer=False):
    from isardvdi_change_handler.task_results import storage

    dep = SimpleNamespace(task="qemu_img_info_backing_chain", result=result)
    domain_obj = MagicMock(status="Stopped")
    child_obj = MagicMock(status="ready")
    storage_obj = MagicMock(domains=[domain_obj])
    storage_obj.domains_dependents.return_value = [domain_obj]
    storage_obj.dependents.return_value = [child_obj]
    with (
        patch.object(storage, "Storage") as mock_storage_cls,
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        mock_storage_cls.exists.return_value = True
        mock_storage_cls.write_reading.return_value = row_status
        mock_storage_cls.return_value = storage_obj
        await storage.handle_storage_update(
            AsyncMock(), _task([dep]), observer=observer
        )
    return mock_storage_cls, domain_obj, child_obj


@pytest.mark.asyncio
async def test_an_open_error_flags_the_row_and_writes_no_status():
    storage_cls, domain_obj, child_obj = await _update(
        {"id": "s1", "open_error": _ERROR}
    )

    (reading,), _ = storage_cls.write_reading.call_args
    assert reading == {"id": "s1"}
    storage_cls.flag_pending.assert_called_once_with(
        "s1",
        "review_damage",
        found_by="storage refresh",
        detail={
            "reason": "the file is present but could not be opened",
            "error": _ERROR,
        },
        if_absent=True,
    )
    assert domain_obj.status == "Stopped"
    assert child_obj.status == "ready"


@pytest.mark.asyncio
async def test_an_observer_does_not_flag_a_row_a_chain_holds():
    """The chain holding the row may be writing the file at that moment."""
    storage_cls, _, _ = await _update(
        {"id": "s1", "open_error": _ERROR}, row_status="maintenance", observer=True
    )
    storage_cls.flag_pending.assert_not_called()


@pytest.mark.asyncio
async def test_the_chain_that_holds_the_row_does_flag_it():
    storage_cls, _, _ = await _update(
        {"id": "s1", "open_error": _ERROR}, row_status="maintenance"
    )
    storage_cls.flag_pending.assert_called_once()


@pytest.mark.asyncio
async def test_a_reading_that_opened_flags_nothing():
    storage_cls, _, _ = await _update({"id": "s1", "status": "ready"})
    storage_cls.flag_pending.assert_not_called()
