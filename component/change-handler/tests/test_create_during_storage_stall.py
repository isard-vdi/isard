# SPDX-License-Identifier: AGPL-3.0-or-later

"""A desktop created while the storage gives no verdict waits for it, instead of failing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from tests.test_reconcile import _domain, _DomainRows, _storage


def _change_storage(storage_status, domain_status="CreatingDisk"):
    from isardvdi_change_handler.task_results import domain

    fake_domain = MagicMock()
    fake_domain.status = domain_status
    fake_storage = MagicMock()
    fake_storage.status = storage_status
    with (
        patch.object(domain, "Domain") as domain_cls,
        patch.object(domain, "Storage") as storage_cls,
    ):
        domain_cls.build.return_value = fake_domain
        storage_cls.build.return_value = fake_storage
        domain.handle_domain_change_storage(
            SimpleNamespace(depending_status="finished"), "d1", "s1"
        )
    return fake_domain, fake_storage, domain_cls


@pytest.mark.parametrize("storage_status", ["maintenance", "creating"])
def test_a_disk_with_no_verdict_leaves_both_rows_waiting(storage_status):
    fake_domain, fake_storage, domain_cls = _change_storage(storage_status)

    assert fake_domain.status == "CreatingDisk"
    assert fake_storage.status == storage_status
    domain_cls.update_document_if.assert_not_called()


@pytest.mark.parametrize("storage_status", ["deleted", "orphan", "broken_chain"])
def test_a_disk_with_a_negative_verdict_still_fails_both(storage_status):
    fake_domain, fake_storage, _ = _change_storage(storage_status)

    assert fake_domain.status == "Failed"
    assert fake_storage.status == "Failed"


async def _pass3(status, storage):
    from isardvdi_change_handler.streams import reconcile

    dom = _domain(status=status, storages=[storage], disks=[{"storage_id": "s1"}])
    rows = _DomainRows(dom)
    with (
        rows.patched(reconcile),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "handle_domain_change_storage") as hand_off,
    ):
        healed = await reconcile._reconcile_stuck_domains(AsyncMock())
    return healed, hand_off, rows


@pytest.mark.asyncio
async def test_a_waiting_desktop_is_handed_on_once_its_disk_reads_ready():
    storage = _storage(status="ready")

    healed, hand_off, _ = await _pass3("CreatingDisk", storage)

    assert healed == 1
    hand_off.assert_called_once_with(None, "d1", "s1")
    storage.find.assert_not_called()


@pytest.mark.asyncio
async def test_a_waiting_desktop_whose_disk_has_no_verdict_yet_is_re_observed():
    storage = _storage(status="maintenance")

    healed, hand_off, rows = await _pass3("CreatingDisk", storage)

    assert healed == 0
    hand_off.assert_not_called()
    storage.find.assert_called_once()
    assert rows.store["d1"]["status"] == "CreatingDisk"


@pytest.mark.asyncio
async def test_other_lock_statuses_are_still_only_re_observed():
    storage = _storage(status="ready")

    _, hand_off, _ = await _pass3("CreatingTemplate", storage)

    hand_off.assert_not_called()
    storage.find.assert_called_once()


@pytest.mark.asyncio
async def test_a_disk_a_chain_still_works_on_is_left_alone():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status="ready")
    dom = _domain(
        status="CreatingDisk", storages=[storage], disks=[{"storage_id": "s1"}]
    )
    rows = _DomainRows(dom)
    with (
        rows.patched(reconcile),
        patch.object(reconcile, "_task_alive", return_value=True),
        patch.object(reconcile, "handle_domain_change_storage") as hand_off,
    ):
        await reconcile._reconcile_stuck_domains(AsyncMock())

    hand_off.assert_not_called()
