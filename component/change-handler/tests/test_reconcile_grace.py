# SPDX-License-Identifier: AGPL-3.0-or-later

"""Grace window for the storage/domain/media self-heal passes (#3391).

A row that entered its transitional/lock status less than ``GRACE_S`` ago is not
stuck: the producer that parked it (``enqueue_disk_creation_chain_for_domain`` and
its 12 siblings) writes ``CreatingDisk``/``maintenance`` a few statements BEFORE it
registers the task in the index, and a reconcile tick landing in that gap used to
re-issue ``find``/``check_backing_chain`` and make apiv4's ``create_task`` refuse the
real chain with ``428 storage_pending_task`` — orphaning a brand-new desktop.

Passes 2/3/4 have no age gate of their own (only Pass 1 does), so these pin the new
one: a young row is skipped and left for the next tick, an old one still heals, and a
row with no numeric ``status_time`` (legacy rows never written through the model, or
seeded fixtures) keeps the pre-grace behaviour rather than being hidden for ever.
"""

from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

YOUNG = 5  # seconds ago  -> within grace
OLD = 600  # seconds ago  -> past grace


def _storage(sid="s1", *, status="maintenance", status_time=None):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = status
    s.status_time = status_time
    return s


def _domain(did="d1", *, status="CreatingDisk", status_time=None, storages=None):
    d = MagicMock(name=f"domain-{did}")
    d.id = did
    d.status = status
    d.status_time = status_time
    d.storages = storages if storages is not None else []
    return d


def _media(mid="m1", *, status="maintenance", status_time=None):
    m = MagicMock(name=f"media-{mid}")
    m.id = mid
    m.status = status
    m.status_time = status_time
    return m


# --- Pass 2: transitional storage
@pytest.mark.asyncio
async def test_pass2_young_maintenance_storage_is_skipped():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status_time=time() - YOUNG)
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(
            reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=0)
        ) as fin,
    ):
        await reconcile._reconcile_stuck_storage(MagicMock())
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_pass2_old_maintenance_storage_is_healed():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status_time=time() - OLD)
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(
            reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=0)
        ) as fin,
    ):
        await reconcile._reconcile_stuck_storage(MagicMock())
    fin.assert_called_once()
    assert fin.call_args.args[1] is storage


@pytest.mark.asyncio
async def test_pass2_storage_without_status_time_is_healed():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(status_time=None)
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(
            reconcile, "_finalize_stuck_storage", new=AsyncMock(return_value=0)
        ) as fin,
    ):
        await reconcile._reconcile_stuck_storage(MagicMock())
    fin.assert_called_once()


# --- Pass 3: storage-lock domain
@pytest.mark.asyncio
async def test_pass3_young_creatingdisk_domain_is_skipped():
    from isardvdi_change_handler.streams import reconcile

    domain = _domain(status_time=time() - YOUNG)
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[domain]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_finalize_stuck_domain", return_value=0) as fin,
    ):
        await reconcile._reconcile_stuck_domains(MagicMock())
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_pass3_old_creatingdisk_domain_is_reobserved():
    from isardvdi_change_handler.streams import reconcile

    domain = _domain(status_time=time() - OLD)
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[domain]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_finalize_stuck_domain", return_value=0) as fin,
    ):
        await reconcile._reconcile_stuck_domains(MagicMock())
    fin.assert_called_once_with(domain)


@pytest.mark.asyncio
async def test_pass3_domain_without_status_time_is_reobserved():
    from isardvdi_change_handler.streams import reconcile

    domain = _domain(status_time=None)
    with (
        patch.object(reconcile.Domain, "get_index", return_value=[domain]),
        patch.object(reconcile, "_migration_owned_storage_ids", return_value=set()),
        patch.object(reconcile, "_finalize_stuck_domain", return_value=0) as fin,
    ):
        await reconcile._reconcile_stuck_domains(MagicMock())
    fin.assert_called_once()


# --- Pass 4: stuck media (media rows carry status_time via the shared base)
@pytest.mark.asyncio
async def test_pass4_young_maintenance_media_is_skipped():
    from isardvdi_change_handler.streams import reconcile

    media = _media(status_time=time() - YOUNG)
    with (
        patch.object(reconcile.Media, "get_index", side_effect=[[media], []]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_finalize_stuck_media", return_value=1) as fin,
    ):
        await reconcile._reconcile_stuck_media(MagicMock())
    fin.assert_not_called()


@pytest.mark.asyncio
async def test_pass4_old_maintenance_media_is_healed():
    from isardvdi_change_handler.streams import reconcile

    media = _media(status_time=time() - OLD)
    with (
        patch.object(reconcile.Media, "get_index", side_effect=[[media], []]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_finalize_stuck_media", return_value=1) as fin,
    ):
        await reconcile._reconcile_stuck_media(MagicMock())
    fin.assert_called_once_with(media)


@pytest.mark.asyncio
async def test_pass4_media_without_status_time_is_healed():
    from isardvdi_change_handler.streams import reconcile

    media = _media(status_time=None)
    with (
        patch.object(reconcile.Media, "get_index", side_effect=[[media], []]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_finalize_stuck_media", return_value=1) as fin,
    ):
        await reconcile._reconcile_stuck_media(MagicMock())
    fin.assert_called_once()


# --- The predicate itself: boundary is exclusive, non-numeric means "not young"
def test_grace_boundary_is_exclusive_at_grace_s():
    from isardvdi_change_handler.streams import reconcile

    now = 1_000_000.0
    g = reconcile.GRACE_S
    assert (
        reconcile._within_status_grace(_storage(status_time=now - g), now, g) is False
    )
    assert (
        reconcile._within_status_grace(_storage(status_time=now - g + 0.5), now, g)
        is True
    )
    assert (
        reconcile._within_status_grace(_storage(status_time=now - g - 0.5), now, g)
        is False
    )


def test_grace_missing_or_nonnumeric_status_time_is_not_young():
    from isardvdi_change_handler.streams import reconcile

    now = 1_000_000.0
    g = reconcile.GRACE_S
    assert reconcile._within_status_grace(_storage(status_time=None), now, g) is False
    assert reconcile._within_status_grace(_storage(status_time="soon"), now, g) is False
    s = MagicMock()  # a row whose status_time attr was never set at all
    del s.status_time
    assert reconcile._within_status_grace(s, now, g) is False
