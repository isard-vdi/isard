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

"""Maps RQ chain dependent task names to change-handler-side handlers.

The consumer reads ``stream:task-results``, hydrates the matching RQ
:class:`Task`, walks its dependent tree, and for each dependent whose
queue starts with ``core`` calls the handler registered here. Handlers
return ``None`` and may raise — the consumer logs and continues.

Handlers come in two flavours:
- *async* (require :class:`AsyncRedisManager` for SocketIO emits)
- *sync*  (pure rethink writes; the consumer wraps the call in
  :func:`asyncio.to_thread` to keep the event loop healthy).

Each registry entry is ``(handler, is_async)``.
"""

from . import domain, media, storage

ASYNC = True
SYNC = False

HANDLERS = {
    # storage
    "storage_update": (storage.handle_storage_update, ASYNC),
    "storage_update_parent": (storage.handle_storage_update_parent, SYNC),
    "storage_update_pool": (storage.handle_storage_update_pool, ASYNC),
    "storage_update_dict": (storage.handle_storage_update_dict, ASYNC),
    "storage_add": (storage.handle_storage_add, SYNC),
    "storage_delete": (storage.handle_storage_delete, SYNC),
    "update_status": (storage.handle_update_status, ASYNC),
    # media
    "media_update": (media.handle_media_update, SYNC),
    "recycle_bin_update": (media.handle_recycle_bin_update, SYNC),
    # domain
    "domain_creating_disk": (domain.handle_domain_creating_disk, SYNC),
    "domain_change_storage": (domain.handle_domain_change_storage, SYNC),
}
