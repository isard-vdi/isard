#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
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

import json
import logging as log
from datetime import date, datetime

from pydantic import BaseModel


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, BaseModel):
        return obj.model_dump(exclude_none=True)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def json_dumps(obj):
    """json.dumps with datetime and Pydantic model serialization support."""
    return json.dumps(obj, default=_json_default)


# Event-name conventions emitted via self.emit():
#
# - BaseHandler default (admin passthrough tables):
#     "{table}_add" / "{table}_update" / "{table}_delete"
# - Flat user-facing tables (users, categories, groups):
#     "{table}_data" for insert+update, "{table}_delete" for delete
#     (single "_data" event keeps clients simple; they don't need to
#      distinguish insert from update.)
# - Hypervisors (admin namespace, legacy shorthand):
#     "hyper_data" / "hyper_deleted"
# - Domain-specific tables (domains, bookings, media, targets,
#   deployments, vgpus, resource_planner, resources, recycle_bin):
#     custom event names per subdomain — see the specific handler.
#
# These schemes are intentionally heterogeneous: existing frontend
# clients depend on them. Do not rename without a coordinated client
# migration.
class BaseHandler:
    def __init__(self, socketio_server, table):
        self.socketio_server = socketio_server
        self.table = table

    async def handle(self, change):
        log.debug(f"Handling change: {change}")
        try:
            if change.new_val is not None and change.old_val is None:
                log.debug(f"Insert change detected in {self.table}: {change.new_val}")
                return await self.on_insert(change.new_val)
            elif change.old_val is not None and change.new_val is None:
                log.debug(f"Delete change detected in {self.table}: {change.old_val}")
                return await self.on_delete(change.old_val)
            elif change.new_val is not None and change.old_val is not None:
                log.debug(
                    f"Update change detected in {self.table}: {change.old_val} -> {change.new_val}"
                )
                return await self.on_update(change.old_val, change.new_val)
            else:
                return
        except Exception:
            log.exception(
                "Handler %s on table %s failed for change=%r; skipping",
                self.__class__.__name__,
                self.table,
                change,
            )

    # DomainsHandler delegates all emits to DesktopDomainHandler /
    # TemplateDomainHandler and never calls this BaseHandler.emit() directly.
    async def emit(self, event, payload, namespace="/userspace", room=None):
        # room=None would broadcast to the whole namespace; refuse it.
        if room is None:
            log.warning(
                "Refusing to emit event '%s' on namespace '%s' with room=None (table=%s)",
                event,
                namespace,
                self.table,
            )
            return
        log.debug(
            f"Emitting event '{event}' with payload: {payload} to namespace '{namespace}' and room '{room}'"
        )
        await self.socketio_server.emit(event, payload, namespace=namespace, room=room)

    async def on_insert(self, new_val):
        log.debug(f"Insert event: {new_val}")
        await self.emit(
            f"{self.table}_add",
            json_dumps(new_val),
            "/administrators",
            "admins",
        )

    async def on_update(self, old_val, new_val):
        log.debug(f"Update event: {new_val}")
        await self.emit(
            f"{self.table}_update",
            json_dumps(new_val),
            "/administrators",
            "admins",
        )

    async def on_delete(self, old_val):
        log.debug(f"Delete event: {old_val}")
        await self.emit(
            f"{self.table}_delete",
            json_dumps(old_val),
            "/administrators",
            "admins",
        )
