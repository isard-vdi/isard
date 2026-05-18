# SPDX-License-Identifier: AGPL-3.0-or-later

"""Behavioural ports of core_worker handler tests onto the task_results modules.

These tests pin the depending_status guards, dispatch routing in the
indirect-call branches, and the recycle_bin → ``_common`` shortcut.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _task(depending_status="finished", **attrs):
    base = dict(
        id=attrs.pop("id", "t1"),
        user_id=attrs.pop("user_id", "u1"),
        depending_status=depending_status,
        dependencies=attrs.pop("dependencies", []),
    )
    base.update(attrs)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# storage.handle_storage_update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_storage_update_skips_when_depending_status_not_finished():
    """Mirror of core_worker.task.storage_update's first guard."""
    from isardvdi_change_handler.task_results import storage

    redis_manager = AsyncMock()
    task = _task(depending_status="failed")

    with (
        patch.object(storage, "Storage") as mock_storage_cls,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as mock_send,
    ):
        await storage.handle_storage_update(
            redis_manager, task, id="s1", status="ready"
        )
    mock_storage_cls.init_document.assert_not_called()
    mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_update_indirect_walks_qemu_img_info_dependency():
    """No storage_dict → look at task.dependencies for a qemu_img_info result."""
    from isardvdi_change_handler.task_results import storage

    dep = SimpleNamespace(
        task="qemu_img_info_backing_chain",
        result={"id": "s1", "status": "ready"},
    )
    task = _task(dependencies=[dep])
    redis_manager = AsyncMock()

    storage_obj = MagicMock()
    storage_obj.domains = []
    storage_obj.domains_derivatives = []
    storage_obj.derivatives = []
    with (
        patch.object(storage, "Storage") as mock_storage_cls,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as mock_send,
    ):
        mock_storage_cls.exists.return_value = True
        mock_storage_cls.init_document.return_value = storage_obj
        await storage.handle_storage_update(redis_manager, task)

    mock_storage_cls.init_document.assert_called_once_with(id="s1", status="ready")
    mock_send.assert_awaited_once_with(redis_manager, "s1", "ready", "u1")


# ---------------------------------------------------------------------------
# storage.handle_update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_applies_all_branch_and_storage_socket():
    """``_all`` overrides apply regardless of depending_status; storage rows emit."""
    from isardvdi_change_handler.task_results import storage

    statuses = {
        "_all": {"ready": {"storage": ["s1"]}},
    }
    task = _task(depending_status="failed")  # _all still applies
    redis_manager = AsyncMock()

    fake_storage_model = MagicMock()
    fake_media_model = MagicMock()
    fake_domain_model = MagicMock()
    fake_map = {
        "storage": fake_storage_model,
        "media": fake_media_model,
        "domain": fake_domain_model,
    }
    with (
        patch.object(storage, "_ITEM_CLASS_MAP", fake_map),
        patch.object(storage, "send_status_socket", new=AsyncMock()) as mock_send,
    ):
        await storage.handle_update_status(redis_manager, task, statuses=statuses)

    fake_storage_model.init_document.assert_called_once_with("s1", status="ready")
    mock_send.assert_awaited_once_with(redis_manager, "s1", "ready")


@pytest.mark.asyncio
async def test_update_status_dispatches_per_depending_status():
    """Per-status branch (``failed``) fires when task.depending_status matches."""
    from isardvdi_change_handler.task_results import storage

    statuses = {
        "failed": {"maintenance": {"storage": ["s2"]}},
    }
    task = _task(depending_status="failed")
    redis_manager = AsyncMock()
    fake_storage_model = MagicMock()
    fake_map = {"storage": fake_storage_model}
    with (
        patch.object(storage, "_ITEM_CLASS_MAP", fake_map),
        patch.object(storage, "send_status_socket", new=AsyncMock()),
    ):
        await storage.handle_update_status(redis_manager, task, statuses=statuses)
    fake_storage_model.init_document.assert_called_once_with("s2", status="maintenance")


# ---------------------------------------------------------------------------
# media.handle_media_update
# ---------------------------------------------------------------------------


def test_media_update_skips_when_depending_status_not_finished():
    from isardvdi_change_handler.task_results import media

    task = _task(depending_status="failed")
    with patch.object(media, "Media") as mock_media_cls:
        media.handle_media_update(task, id="m1", status="ready")
    mock_media_cls.init_document.assert_not_called()


def test_media_update_direct_writes_payload():
    from isardvdi_change_handler.task_results import media

    task = _task()
    with patch.object(media, "Media") as mock_media_cls:
        media.handle_media_update(task, id="m1", status="ready")
    mock_media_cls.init_document.assert_called_once_with(id="m1", status="ready")


def test_media_update_indirect_walks_check_media_existence():
    from isardvdi_change_handler.task_results import media

    dep = SimpleNamespace(
        task="check_media_existence",
        result={"id": "m1", "status": "ready"},
    )
    task = _task(dependencies=[dep])
    with patch.object(media, "Media") as mock_media_cls:
        media.handle_media_update(task, **{})
    mock_media_cls.init_document.assert_called_once_with(id="m1", status="ready")


# ---------------------------------------------------------------------------
# media.handle_media_download_update_status
# ---------------------------------------------------------------------------


def test_media_download_update_status_downloaded_when_no_abort():
    """depending_status=finished + media not aborting → Downloaded."""
    from isardvdi_change_handler.task_results import media

    task = _task(depending_status="finished")
    fake_media = MagicMock()
    fake_media.status = "Downloading"
    with patch.object(media, "Media") as mock_media_cls:
        mock_media_cls.exists.return_value = True
        mock_media_cls.return_value = fake_media
        media.handle_media_download_update_status(task, media_id="m1")
    assert fake_media.status == "Downloaded"


def test_media_download_update_status_failed_when_aborting():
    """Even if depending_status=finished, DownloadAborting → DownloadFailed.

    Pins the race condition: curl may have finished successfully just as
    the user aborted. The media row's current status is the only authority
    here, not the chain's depending_status. From
    naomi.hidalgo/fix/1171-media-fixes:c84a99e43.
    """
    from isardvdi_change_handler.task_results import media

    task = _task(depending_status="finished")
    fake_media = MagicMock()
    fake_media.status = "DownloadAborting"
    with patch.object(media, "Media") as mock_media_cls:
        mock_media_cls.exists.return_value = True
        mock_media_cls.return_value = fake_media
        media.handle_media_download_update_status(task, media_id="m1")
    assert fake_media.status == "DownloadFailed"


def test_media_download_update_status_failed_when_chain_failed():
    """depending_status=failed → DownloadFailed regardless of media row."""
    from isardvdi_change_handler.task_results import media

    task = _task(depending_status="failed")
    fake_media = MagicMock()
    fake_media.status = "Downloading"
    with patch.object(media, "Media") as mock_media_cls:
        mock_media_cls.exists.return_value = True
        mock_media_cls.return_value = fake_media
        media.handle_media_download_update_status(task, media_id="m1")
    assert fake_media.status == "DownloadFailed"


def test_media_download_update_status_skips_missing_media():
    """Media.exists=False → no write."""
    from isardvdi_change_handler.task_results import media

    task = _task(depending_status="finished")
    with patch.object(media, "Media") as mock_media_cls:
        mock_media_cls.exists.return_value = False
        media.handle_media_download_update_status(task, media_id="missing")
    mock_media_cls.assert_not_called()  # __init__ not invoked


# ---------------------------------------------------------------------------
# media.handle_recycle_bin_update
# ---------------------------------------------------------------------------


def test_recycle_bin_update_calls_common_helper_with_root_status():
    """change-handler shortcuts the apiv4 hop and calls _common directly with the chain root's status."""
    from isardvdi_change_handler.task_results import media

    root = SimpleNamespace(id="root-task", status="finished")
    parent = SimpleNamespace(dependencies=[root])
    task = SimpleNamespace(id="dep-task", dependencies=[parent])

    with patch.object(media, "RecycleBinHelpers") as mock_helpers:
        media.handle_recycle_bin_update(task, recycle_bin_id="rb-42")
    mock_helpers.update_task_status.assert_called_once_with(
        {"recycle_bin_id": "rb-42", "id": "root-task", "status": "finished"}
    )


def test_recycle_bin_update_skips_when_recycle_bin_id_missing():
    from isardvdi_change_handler.task_results import media

    task = SimpleNamespace(id="dep-task", dependencies=[])
    with patch.object(media, "RecycleBinHelpers") as mock_helpers:
        media.handle_recycle_bin_update(task)  # no recycle_bin_id
    mock_helpers.update_task_status.assert_not_called()


# ---------------------------------------------------------------------------
# domain.handle_domain_creating_disk / handle_domain_change_storage
# ---------------------------------------------------------------------------


def test_domain_creating_disk_only_advances_allow_listed_statuses():
    from isardvdi_change_handler.task_results import domain

    task = _task()
    fake_domain = MagicMock()
    fake_domain.status = "Started"
    with patch.object(domain, "Domain") as mock_domain_cls:
        mock_domain_cls.exists.return_value = True
        mock_domain_cls.return_value = fake_domain
        domain.handle_domain_creating_disk(task, domain_id="d1")
    # Started is NOT in the allow set → status stays put.
    assert fake_domain.status == "Started"


def test_domain_creating_disk_flips_creating_to_creating_disk():
    from isardvdi_change_handler.task_results import domain

    task = _task()
    fake_domain = MagicMock()
    fake_domain.status = "Creating"
    with patch.object(domain, "Domain") as mock_domain_cls:
        mock_domain_cls.exists.return_value = True
        mock_domain_cls.return_value = fake_domain
        domain.handle_domain_creating_disk(task, domain_id="d1")
    assert fake_domain.status == "CreatingDisk"


def test_domain_change_storage_raises_when_storage_not_ready_for_create_domain():
    """The create flow must fail-fast when the chain failed upstream."""
    from isardvdi_change_handler.task_results import domain

    task = _task()
    fake_domain = MagicMock()
    fake_domain.status = "Creating"
    fake_storage = MagicMock()
    fake_storage.status = "broken_chain"
    with (
        patch.object(domain, "Domain") as mock_domain_cls,
        patch.object(domain, "Storage") as mock_storage_cls,
    ):
        mock_domain_cls.exists.return_value = True
        mock_storage_cls.exists.return_value = True
        mock_domain_cls.return_value = fake_domain
        mock_storage_cls.return_value = fake_storage
        with pytest.raises(Exception, match="not ready"):
            domain.handle_domain_change_storage(task, domain_id="d1", storage_id="s1")
