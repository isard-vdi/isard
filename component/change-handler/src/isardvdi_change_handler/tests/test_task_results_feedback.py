# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``task_results.feedback.emit_task_feedback``."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _fake_task(
    *,
    task_id="t-root",
    user_id="u-alice",
    queue="storage.poolA.high",
    result={"status": "ready"},
    to_dict_payload=None,
):
    """Build a Task-like double with the attributes ``emit_task_feedback`` reads."""
    if to_dict_payload is None:
        to_dict_payload = {"id": task_id, "user_id": user_id, "queue": queue}
    return SimpleNamespace(
        id=task_id,
        user_id=user_id,
        queue=queue,
        result=result,
        to_dict=lambda: to_dict_payload,
    )


@pytest.mark.asyncio
async def test_emits_full_fan_out_when_user_has_category():
    """User exists in rethink → 6 SocketIO events match core_worker.feedback."""
    from isardvdi_change_handler.task_results.feedback import emit_task_feedback

    task = _fake_task()
    redis_manager = AsyncMock()
    redis_manager.emit = AsyncMock()

    with (
        patch("isardvdi_change_handler.task_results.feedback.Task", return_value=task),
        patch(
            "isardvdi_change_handler.task_results.feedback.User",
            return_value=SimpleNamespace(category="cat-eng"),
        ),
    ):
        await emit_task_feedback(redis_manager, task.id)

    assert redis_manager.emit.await_count == 6
    events = [
        (c.args[0], c.kwargs["namespace"], c.kwargs["room"])
        for c in redis_manager.emit.await_args_list
    ]
    assert events == [
        ("task", "/administrators", "admins"),
        ("task", "/administrators", "cat-eng"),
        ("task", "/userspace", "u-alice"),
        ("storage", "/administrators", "admins"),
        ("storage", "/administrators", "cat-eng"),
        ("storage", "/administrators", "u-alice"),
    ]
    # Payloads: task event carries chain dict JSON; queue-prefix event
    # carries task.result JSON.
    task_payloads = {
        c.args[1] for c in redis_manager.emit.await_args_list if c.args[0] == "task"
    }
    storage_payloads = {
        c.args[1] for c in redis_manager.emit.await_args_list if c.args[0] == "storage"
    }
    assert task_payloads == {json.dumps(task.to_dict())}
    assert storage_payloads == {json.dumps(task.result)}


@pytest.mark.asyncio
async def test_emits_admins_only_when_user_missing():
    """User lookup returns None → 2 admins-only events, no per-category or user rooms."""
    from isardvdi_change_handler.task_results.feedback import emit_task_feedback

    task = _fake_task()
    redis_manager = AsyncMock()

    with (
        patch("isardvdi_change_handler.task_results.feedback.Task", return_value=task),
        patch(
            "isardvdi_change_handler.task_results.feedback.User",
            side_effect=Exception("not found"),
        ),
    ):
        await emit_task_feedback(redis_manager, task.id)

    events = [
        (c.args[0], c.kwargs["namespace"], c.kwargs["room"])
        for c in redis_manager.emit.await_args_list
    ]
    assert events == [
        ("task", "/administrators", "admins"),
        ("storage", "/administrators", "admins"),
    ]


@pytest.mark.asyncio
async def test_isard_scheduler_emits_nothing():
    """Synthetic scheduler user must not fan out any SocketIO event."""
    from isardvdi_change_handler.task_results.feedback import emit_task_feedback

    task = _fake_task(user_id="isard-scheduler")
    redis_manager = AsyncMock()

    with patch("isardvdi_change_handler.task_results.feedback.Task", return_value=task):
        await emit_task_feedback(redis_manager, task.id)

    redis_manager.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_swallows_task_load_failure():
    """A bad task_id must not raise — the stream stays consumable."""
    from isardvdi_change_handler.task_results.feedback import emit_task_feedback

    redis_manager = AsyncMock()
    with patch(
        "isardvdi_change_handler.task_results.feedback.Task",
        side_effect=Exception("redis down"),
    ):
        await emit_task_feedback(redis_manager, "does-not-exist")
    redis_manager.emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_event_uses_first_dot_segment():
    """``task.queue.split('.')[0]`` is the queue-prefix event name."""
    from isardvdi_change_handler.task_results.feedback import emit_task_feedback

    task = _fake_task(queue="media.poolB.low", result={"ok": True})
    redis_manager = AsyncMock()

    with (
        patch("isardvdi_change_handler.task_results.feedback.Task", return_value=task),
        patch(
            "isardvdi_change_handler.task_results.feedback.User",
            return_value=SimpleNamespace(category="cat-x"),
        ),
    ):
        await emit_task_feedback(redis_manager, task.id)

    queue_events = {
        c.args[0] for c in redis_manager.emit.await_args_list if c.args[0] != "task"
    }
    assert queue_events == {"media"}
