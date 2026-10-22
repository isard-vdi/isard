# SPDX-License-Identifier: AGPL-3.0-or-later

"""The finalize passes must fail CLOSED when the migration ledger cannot be read.

A disk mid-saga is only ``active_storage_ids()`` knows a migration still owes it
work; between its phase tasks the disk reads as abandoned. If that read raises --
which a timing-out DB makes exactly when it matters -- the passes must skip, not
finalize a disk a live migration still owns (which would free its parked desktops
onto a source the migration is about to discard). A readable ledger that does not
list the disk still finalizes it; that control is what proves the skip above is
the fail-closed guard and not some unrelated short-circuit.
"""

from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

OLD = 600  # status_time well past the grace window


def _storage(sid="s1", status="maintenance"):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = status
    s.status_time = time() - OLD
    s.domains = []
    return s


def _domain():
    d = MagicMock(name="domain-d1")
    d.id = "d1"
    d.status = "Maintenance"
    d.status_time = time() - OLD
    backing = MagicMock()
    backing.id = "s1"
    d.storages = [backing]
    return d


def _ledger(reconcile, *, raises):
    p = patch.object(reconcile.StorageMigrationItem, "active_storage_ids")
    m = p.start()
    if raises:
        m.side_effect = RuntimeError("db down")
    else:
        m.return_value = set()  # readable, disk not migrating
    return p


@pytest.mark.asyncio
async def test_stuck_storage_finalizes_when_ledger_readable():
    """Control: the row IS stuck and the ledger reads fine -> it gets finalized."""
    from isardvdi_change_handler.streams import reconcile

    p = _ledger(reconcile, raises=False)
    try:
        with (
            patch.object(reconcile.Storage, "get_index", return_value=[_storage()]),
            patch.object(reconcile, "_task_alive", return_value=False),
            patch.object(
                reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=1)
            ) as fin,
        ):
            healed = await reconcile._reconcile_stuck_storage(MagicMock())
        fin.assert_called_once()
        assert healed == 1
    finally:
        p.stop()


@pytest.mark.asyncio
async def test_stuck_storage_fails_closed_when_ledger_unreadable():
    from isardvdi_change_handler.streams import reconcile

    p = _ledger(reconcile, raises=True)
    try:
        with (
            patch.object(reconcile.Storage, "get_index", return_value=[_storage()]),
            patch.object(reconcile, "_task_alive", return_value=False),
            patch.object(
                reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=1)
            ) as fin,
        ):
            healed = await reconcile._reconcile_stuck_storage(MagicMock())
        fin.assert_not_called()
        assert healed == 0
    finally:
        p.stop()


@pytest.mark.asyncio
async def test_unclaimed_allocations_fails_closed_when_ledger_unreadable():
    from isardvdi_change_handler.streams import reconcile

    p = _ledger(reconcile, raises=True)
    try:
        with (
            patch.object(
                reconcile.Storage,
                "get_index",
                return_value=[_storage(status="non_existing")],
            ),
            patch.object(reconcile, "_task_alive", return_value=False),
            patch.object(reconcile, "_claimed_by_a_domain", return_value=False),
            patch.object(
                reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=1)
            ) as fin,
        ):
            healed = await reconcile._reconcile_unclaimed_allocations(MagicMock())
        fin.assert_not_called()
        assert healed == 0
    finally:
        p.stop()


@pytest.mark.asyncio
async def test_stuck_domains_fails_closed_when_ledger_unreadable():
    from isardvdi_change_handler.streams import reconcile

    p = _ledger(reconcile, raises=True)
    try:
        with (
            patch.object(reconcile.Domain, "get_index", return_value=[_domain()]),
            patch.object(
                reconcile, "_finalize_stuck_domain", new=MagicMock(return_value=1)
            ) as fin,
        ):
            healed = await reconcile._reconcile_stuck_domains(MagicMock())
        fin.assert_not_called()
        assert healed == 0
    finally:
        p.stop()
