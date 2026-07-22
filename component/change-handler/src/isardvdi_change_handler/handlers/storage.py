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

"""Storage table changefeed → SocketIO emitter.

Bridges the ``storage`` RethinkDB changefeed to the webapp's existing
``socket.on("storage", ...)`` listener (admin storage table, lives at
``webapp/.../static/admin/js/storage.js``). The listener already handles
three branches:

  - ``data.status != "ready"`` → row removed from current table, bumped
    on the "Other status" dropdown, added to ``storagesOtherTable`` iff
    that status is currently selected.
  - ``data.status == "ready"`` → row removed from ``storagesOtherTable``
    and re-added to the ready table.
  - status absent → row's columns updated in place via
    ``.data({…actual_data, …data}).invalidate()``.

Mirrors the rooming pattern of ``task_results.storage.send_status_socket``
(admins + user_id + user's category) so the same set of subscribers see
both the chain-driven and changefeed-driven emits — the listener is
idempotent.
"""

import asyncio
import logging as log

from isardvdi_common.helpers.caches import Caches

from .base import BaseHandler, json_dumps

# Match the existing event name the frontend listens for. Do not rename
# without a coordinated client migration — see ``base.py`` event-name
# conventions block.
_EVENT = "storage"
_NAMESPACE = "/administrators"

# Fields that, when changed in isolation, are not worth a SocketIO emit.
# The full row payload still goes out when any "meaningful" field changes.
_NOISE_FIELDS = frozenset({"status_time"})


class StorageHandler(BaseHandler):
    """Emits the ``storage`` event for every row insert / update / delete.

    The plucked fields from ``tables.json`` (see the ``storage`` entry)
    are: ``id``, ``status``, ``status_time``, ``user_id``,
    ``directory_path``, ``type``, ``parent``, ``task``,
    ``storages_with_uuid``, ``progress``, plus the sub-projection of
    ``qemu-img-info`` (``virtual-size`` / ``actual-size`` /
    ``full-backing-filename``). Storage's row is intentionally NOT in
    ``gen_changefeed_asyncapi.TABLE_TO_CLASS`` — the generated
    ``StorageRow`` is permissive (every field lives under
    ``additional_properties``), same shape as ``recycle_bin``. Use
    ``self._prop()`` (mirrors ``RecycleBinHandler._prop``) to access
    fields uniformly across attribute / additional_properties without
    a branch per field.
    """

    def _prop(self, val, key, default=None):
        """Attribute-first read, fall back to ``additional_properties``."""
        if val is None:
            return default
        attr = getattr(val, key, None)
        if attr is not None:
            return attr
        return (getattr(val, "additional_properties", None) or {}).get(key, default)

    def _payload(self, val, include_status):
        """Build the SocketIO payload from a ``StorageRow``.

        The frontend listener merges ``{…actual_data, …data}`` onto the
        existing DataTable row, so we ship every plucked field. ``status``
        is conditionally included so the listener picks the right branch
        (with status → remove/add row across tables; without status →
        in-place ``.data().invalidate()``).
        """
        dumped = val.model_dump(by_alias=True, exclude_none=True)
        payload = {"id": self._prop(val, "id")}
        for key in (
            "directory_path",
            "type",
            "parent",
            "task",
            "storages_with_uuid",
            "progress",
            "status_time",
            "qemu-img-info",
        ):
            if key in dumped:
                payload[key] = dumped[key]
        if include_status:
            status = self._prop(val, "status")
            if status is not None:
                payload["status"] = status
        return payload

    async def _emit_storage(self, payload, user_id):
        """Fan out the event to admins / user / category rooms.

        Same room set ``task_results.storage.send_status_socket`` uses,
        so the listener sees one event from either path. Category is
        resolved off the cached user view; failures are swallowed —
        admins still get the broadcast.
        """
        payload_json = json_dumps(payload)
        rooms = ["admins"]
        if user_id:
            rooms.append(user_id)
            try:
                user = await asyncio.to_thread(
                    Caches.get_cached_user_with_names, user_id
                )
            except Exception:
                user = None
                log.exception("storage: failed to resolve user %s", user_id)
            if user:
                category = user.get("category")
                if category:
                    rooms.append(category)
        for room in rooms:
            await self.emit(_EVENT, payload_json, _NAMESPACE, room=room)

    async def on_insert(self, new_val):
        payload = self._payload(new_val, include_status=True)
        await self._emit_storage(payload, self._prop(new_val, "user_id"))

    async def on_update(self, old_val, new_val):
        old_status = self._prop(old_val, "status")
        new_status = self._prop(new_val, "status")
        status_changed = old_status != new_status

        # Suppress no-op updates (e.g. a status_time-only write driven
        # by Storage.__setattr__ refreshing the timestamp on an
        # unchanged status). The frontend would otherwise pay a row
        # invalidate per such event.
        if not status_changed:
            old_dumped = (
                old_val.model_dump(by_alias=True, exclude_none=True) if old_val else {}
            )
            new_dumped = new_val.model_dump(by_alias=True, exclude_none=True)
            interesting_changed = any(
                old_dumped.get(k) != new_dumped.get(k)
                for k in new_dumped.keys() | old_dumped.keys()
                if k not in _NOISE_FIELDS
            )
            if not interesting_changed:
                return

        payload = self._payload(new_val, include_status=status_changed)
        await self._emit_storage(payload, self._prop(new_val, "user_id"))

    async def on_delete(self, old_val):
        # The frontend has no specific "storage deleted" branch, but it
        # treats any non-ready status as "remove from ready table". Send
        # status="deleted" so the row leaves the ready table promptly
        # even before the DataTable's next ajax reload.
        payload = {"id": self._prop(old_val, "id"), "status": "deleted"}
        await self._emit_storage(payload, self._prop(old_val, "user_id"))
