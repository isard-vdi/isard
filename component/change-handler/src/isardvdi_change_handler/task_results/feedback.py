#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""SocketIO ``task`` emit ported from core_worker.

core_worker's ``feedback(task_id)`` builds the chain dict (via
``Task.to_dict()``), fans it out to the admin and user rooms, and also
emits a queue-prefix event with the raw result. This module mirrors
that fan-out exactly so the existing webapp and Vue 3 listeners receive
byte-equivalent payloads — only the producer changes (storage worker
publishes to ``stream:task-results`` instead of enqueuing
``core.feedback``, change-handler emits the SocketIO event instead of
core_worker).

Differences from core_worker.task.feedback:
- user category resolved by reading the ``users`` table directly via
  ``isardvdi_common.models.user.User`` instead of an apiv4 HTTP call.
  Same shape of decision (have-category vs admins-only fallback).
- no second HTTP POST to apiv4 ``admin_emit_socketio`` — the
  AsyncRedisManager (write-only) is the single delivery path,
  matching how change-handler's existing per-table handlers emit.
"""

import asyncio
import json
import logging as log

from isardvdi_common.models.task import Task
from isardvdi_common.models.user import User


def _resolve_user_category(user_id):
    """Look up the user's category from rethinkdb.

    Replaces core_worker's ``user_info(user_id)`` apiv4 call. Returns
    ``None`` if the user no longer exists or any error occurs — same
    semantics as the original ``isinstance(user, dict)`` guard.
    """
    if not user_id:
        return None
    try:
        return User(user_id).category
    except Exception:
        return None


def _enrich_feedback(task, task_dict):
    """Add the live queue estimate and the root task's ``storage_id`` to the
    emitted payload so the frontend can map the task to its desktop card and show
    position / ETA. ``storage_id`` is excluded from ``Task.to_dict`` (it triggers
    a db query on every dependent); resolve it once here for the root only.
    Best-effort — never breaks the emit."""
    try:
        from isardvdi_common.lib.queue_estimate import estimate_task

        est = estimate_task(task)
        task_dict["effective_position"] = est.get("effective_position")
        task_dict["eta_seconds"] = est.get("eta_seconds")
        task_dict["has_consumer"] = est.get("has_consumer")
        task_dict["stranded"] = est.get("stranded")
    except Exception:
        pass
    try:
        task_dict["storage_id"] = getattr(task.storage_id, "id", None)
    except Exception:
        task_dict.setdefault("storage_id", None)


def _build_events(task, task_as_json, user_category):
    """Mirror the exact event list emitted by core_worker.task.feedback."""
    queue_event = task.queue.split(".")[0]
    result_json = json.dumps(task.result)

    events = [
        ("task", task_as_json, "/administrators", "admins"),
    ]
    if user_category:
        events.append(("task", task_as_json, "/administrators", user_category))
        events.append(("task", task_as_json, "/userspace", task.user_id))
    events.append((queue_event, result_json, "/administrators", "admins"))
    if user_category:
        events.append((queue_event, result_json, "/administrators", user_category))
        events.append((queue_event, result_json, "/administrators", task.user_id))
    return events


async def emit_task_feedback(redis_manager, task_id):
    """Emit the ``task`` SocketIO chain dict for ``task_id`` via the
    write-only :class:`AsyncRedisManager`.

    A drop-in equivalent of core_worker's ``feedback(task_id)``:
    silently no-ops for the ``isard-scheduler`` synthetic user, and
    only fans out to per-category / per-user rooms if the user is
    still present in rethinkdb.
    """
    try:
        task = await asyncio.to_thread(Task, task_id)
    except Exception:
        log.exception("task_results.feedback: failed to load Task(%s)", task_id)
        return

    if task.user_id == "isard-scheduler":
        return

    user_category = await asyncio.to_thread(_resolve_user_category, task.user_id)

    try:
        task_dict = await asyncio.to_thread(task.to_dict)
        await asyncio.to_thread(_enrich_feedback, task, task_dict)
        task_as_json = json.dumps(task_dict)
    except Exception:
        log.exception("task_results.feedback: failed to serialise Task(%s)", task_id)
        return

    for event, data, namespace, room in _build_events(
        task, task_as_json, user_category
    ):
        if room is None:
            continue
        try:
            await redis_manager.emit(event, data, namespace=namespace, room=room)
        except Exception:
            log.exception(
                "task_results.feedback: emit %s on %s/%s failed",
                event,
                namespace,
                room,
            )
