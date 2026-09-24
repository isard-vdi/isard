# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pass 5: an allocated storage row that nothing ever claimed.

``new_dict`` inserts a row in ``non_existing`` before any chain runs, and that
status sits outside every other pass — so a chain that dies after the insert
leaves a row no sweep will ever look at again. A live allocation always carries
one of two claims: its chain names it in the per-owner task index, or a domain
references it through ``domains.storage_ids``. These pin that both claims are
honoured, that the status grace still covers the window before either exists,
and that an unreadable claim counts as claimed.
"""

from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

YOUNG = 5
OLD = 600


def _allocated(sid="s1", *, status_time=None, domains=None):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = "non_existing"
    s.status_time = status_time
    s.domains = domains if domains is not None else []
    return s


def _sweep(storage, *, task_alive=False, migrating=frozenset()):
    """Run the pass over one row, returning the finalize mock."""
    from isardvdi_change_handler.streams import reconcile

    return (
        reconcile,
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(
            reconcile, "_migration_owned_storage_ids", return_value=set(migrating)
        ),
        patch.object(reconcile, "_task_alive", return_value=task_alive),
    )


async def _run(storage, **kw):
    reconcile, p_index, p_mig, p_alive = _sweep(storage, **kw)
    with (
        p_index,
        p_mig,
        p_alive,
        patch.object(
            reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=0)
        ) as fin,
    ):
        await reconcile._reconcile_unclaimed_allocations(MagicMock())
    return fin


@pytest.mark.asyncio
async def test_an_old_unclaimed_allocation_is_observed():
    fin = await _run(_allocated(status_time=time() - OLD))
    fin.assert_called_once()


@pytest.mark.asyncio
async def test_a_young_allocation_is_left_for_the_next_tick():
    fin = await _run(_allocated(status_time=time() - YOUNG))
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_a_row_with_no_clock_keeps_the_pre_grace_behaviour():
    fin = await _run(_allocated(status_time=None))
    fin.assert_called_once()


@pytest.mark.asyncio
async def test_a_live_chain_claims_its_own_allocation():
    fin = await _run(_allocated(status_time=time() - OLD), task_alive=True)
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_a_referring_domain_claims_the_allocation():
    row = _allocated(status_time=time() - OLD, domains=[MagicMock(id="d1")])
    fin = await _run(row)
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_a_migration_still_owes_work_on_it():
    fin = await _run(_allocated(status_time=time() - OLD), migrating={"s1"})
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_an_unreadable_claim_counts_as_claimed():
    row = _allocated(status_time=time() - OLD)
    type(row).domains = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    fin = await _run(row)
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_nothing_allocated_is_a_no_op():
    from isardvdi_change_handler.streams import reconcile

    with (
        patch.object(reconcile.Storage, "get_index", return_value=[]),
        patch.object(
            reconcile, "_migration_owned_storage_ids", return_value=set()
        ) as mig,
        patch.object(
            reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=0)
        ) as fin,
    ):
        assert await reconcile._reconcile_unclaimed_allocations(MagicMock()) == 0
    fin.assert_not_called()
    mig.assert_not_called()


@pytest.mark.asyncio
async def test_the_pass_runs_on_every_tick():
    """Wired into the loop, not just defined."""
    import inspect

    from isardvdi_change_handler.streams import reconcile

    assert "_reconcile_unclaimed_allocations" in inspect.getsource(reconcile.run)
