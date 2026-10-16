# SPDX-License-Identifier: AGPL-3.0-or-later

"""The repair result handlers: ``handle_storage_repair_result`` is the row's status
authority (ready / damaged / restore), and ``handle_storage_repair_size`` refreshes
qemu-img-info WITHOUT ever writing status."""

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


def _repair_dep(ok=None, after=None, result="__use_ok__"):
    if result == "__use_ok__":
        result = (
            None if ok is None else {"what": "leaks", "ok": ok, "after": after or {}}
        )
    return SimpleNamespace(task="qemu_img_check_repair", result=result)


def _domain(status="Maintenance"):
    return SimpleNamespace(status=status, current_action="repair")


# --- handle_storage_repair_result -------------------------------------------


@pytest.mark.asyncio
async def test_clean_repair_lands_ready_clears_reason_and_marks():
    from isardvdi_change_handler.task_results import storage

    dom = _domain()
    task = _task(
        dependencies=[_repair_dep(ok=True, after={"ok": True, "summary": "no errors"})]
    )
    redis_manager = AsyncMock()
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as send,
    ):
        S.exists.return_value = True
        S.return_value.domains = [dom]
        await storage.handle_storage_repair_result(
            redis_manager, task, storage_id="s1", previous_status="damaged"
        )

    S.insert_document.assert_called_once_with(
        {"id": "s1", "status": "ready", "damage_reason": None}, conflict="update"
    )
    assert ("s1", "repair_leaks") in {c.args for c in S.clear_pending.call_args_list}
    assert ("s1", "review_damage") in {c.args for c in S.clear_pending.call_args_list}
    assert dom.status == "Stopped" and dom.current_action is None
    send.assert_awaited_once_with(redis_manager, "s1", "ready", "u1")


@pytest.mark.asyncio
async def test_still_dirty_repair_stays_damaged_with_new_reason_and_keeps_marks():
    from isardvdi_change_handler.task_results import storage

    dom = _domain()
    task = _task(
        dependencies=[
            _repair_dep(ok=False, after={"ok": False, "summary": "corruptions=2"})
        ]
    )
    redis_manager = AsyncMock()
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as send,
    ):
        S.exists.return_value = True
        S.return_value.domains = [dom]
        await storage.handle_storage_repair_result(
            redis_manager, task, storage_id="s1", previous_status="damaged"
        )

    S.insert_document.assert_called_once_with(
        {"id": "s1", "status": "damaged", "damage_reason": "corruptions=2"},
        conflict="update",
    )
    S.clear_pending.assert_not_called()  # marks stay
    assert dom.status == "Failed"
    send.assert_awaited_once_with(redis_manager, "s1", "damaged", "u1")


@pytest.mark.asyncio
async def test_failed_task_restores_previous_status_and_keeps_marks():
    from isardvdi_change_handler.task_results import storage

    dom = _domain()
    # a failed task publishes no result payload
    task = _task(depending_status="failed", dependencies=[_repair_dep(result=None)])
    redis_manager = AsyncMock()
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as send,
    ):
        S.exists.return_value = True
        S.return_value.domains = [dom]
        await storage.handle_storage_repair_result(
            redis_manager, task, storage_id="s1", previous_status="damaged"
        )

    S.insert_document.assert_called_once_with(
        {"id": "s1", "status": "damaged"}, conflict="update"
    )
    S.clear_pending.assert_not_called()
    assert dom.status == "Failed"
    send.assert_awaited_once_with(redis_manager, "s1", "damaged", "u1")


@pytest.mark.asyncio
async def test_failed_repair_of_a_leaky_ready_disk_goes_back_to_ready():
    """A repair_leaks disk was Ready; a failed repair must not mark it damaged."""
    from isardvdi_change_handler.task_results import storage

    dom = _domain()
    task = _task(depending_status="failed", dependencies=[_repair_dep(result=None)])
    redis_manager = AsyncMock()
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as send,
    ):
        S.exists.return_value = True
        S.return_value.domains = [dom]
        await storage.handle_storage_repair_result(
            redis_manager, task, storage_id="s1", previous_status="ready"
        )

    S.insert_document.assert_called_once_with(
        {"id": "s1", "status": "ready"}, conflict="update"
    )
    assert dom.status == "Stopped"
    send.assert_awaited_once_with(redis_manager, "s1", "ready", "u1")


@pytest.mark.asyncio
async def test_repair_result_no_ops_on_a_missing_row():
    from isardvdi_change_handler.task_results import storage

    task = _task(dependencies=[_repair_dep(ok=True)])
    with (
        patch.object(storage, "Storage") as S,
        patch.object(storage, "send_status_socket", new=AsyncMock()) as send,
    ):
        S.exists.return_value = False
        await storage.handle_storage_repair_result(
            AsyncMock(), task, storage_id="s1", previous_status="damaged"
        )
    S.insert_document.assert_not_called()
    send.assert_not_awaited()


# --- handle_storage_repair_size ---------------------------------------------


def test_repair_size_writes_qemu_img_info_only_never_status():
    from isardvdi_change_handler.task_results import storage

    dep = SimpleNamespace(
        task="qemu_img_info_backing_chain",
        result={"id": "s1", "status": "ready", "qemu-img-info": {"actual-size": 42}},
    )
    task = _task(dependencies=[dep])
    with patch.object(storage, "Storage") as S:
        S.exists.return_value = True
        storage.handle_storage_repair_size(task, storage_id="s1")
    S.insert_document.assert_called_once_with(
        {"id": "s1", "qemu-img-info": {"actual-size": 42}}, conflict="update"
    )
    # the written payload carries no status: a corrupt-but-readable disk that
    # qemu-img info calls "ready" must never overwrite a damaged verdict
    written = S.insert_document.call_args.args[0]
    assert "status" not in written


def test_repair_size_skips_when_not_finished():
    from isardvdi_change_handler.task_results import storage

    dep = SimpleNamespace(
        task="qemu_img_info_backing_chain",
        result={"id": "s1", "status": "ready", "qemu-img-info": {"actual-size": 42}},
    )
    task = _task(depending_status="failed", dependencies=[dep])
    with patch.object(storage, "Storage") as S:
        S.exists.return_value = True
        storage.handle_storage_repair_size(task, storage_id="s1")
    S.insert_document.assert_not_called()


def test_repair_size_skips_a_dependency_with_no_measurement():
    from isardvdi_change_handler.task_results import storage

    dep = SimpleNamespace(task="qemu_img_info_backing_chain", result=None)
    task = _task(dependencies=[dep])
    with patch.object(storage, "Storage") as S:
        S.exists.return_value = True
        storage.handle_storage_repair_size(task, storage_id="s1")
    S.insert_document.assert_not_called()


# --- registry ---------------------------------------------------------------


def test_repair_handlers_are_registered():
    """A dependent whose task name is not in the registry is a silent no-op, so
    pin the wiring (see the isardvdi-tasks skill)."""
    from isardvdi_change_handler.task_results import registry, storage

    handler, is_async = registry.HANDLERS["storage_repair_result"]
    assert (
        handler is storage.handle_storage_repair_result and is_async is registry.ASYNC
    )

    handler, is_async = registry.HANDLERS["storage_repair_size"]
    assert handler is storage.handle_storage_repair_size and is_async is registry.SYNC
