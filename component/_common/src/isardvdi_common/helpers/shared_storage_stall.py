#
#   Copyright © 2026 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The shared-storage stall the engine stores in ``config.shared_storage_stall``."""

import logging
import threading
import time

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r

DESCRIPTION_CODE = "service_temporarily_unavailable"


class SharedStorageStall(RethinkSharedConnection):
    TTL_S = 2

    _lock = threading.Lock()
    _cached_at = 0.0
    _cached = None

    @classmethod
    def current(cls):
        """The stored condition; a read failure never blocks a start."""
        with cls._lock:
            if time.monotonic() - cls._cached_at < cls.TTL_S:
                return cls._cached
        try:
            with cls._rdb_context():
                state = (
                    r.table("config")
                    .get(1)
                    .pluck("shared_storage_stall")
                    .run(cls._rdb_connection)
                    .get("shared_storage_stall")
                )
        except Exception:
            logging.exception("Could not read the shared storage condition")
            state = None
        with cls._lock:
            cls._cached, cls._cached_at = state, time.monotonic()
        return state

    @classmethod
    def active(cls):
        state = cls.current()
        return isinstance(state, dict) and state.get("active") is True

    @classmethod
    def raise_if_active(cls):
        if cls.active():
            raise Error(
                "service_unavailable",
                "Service temporarily unavailable",
                description_code=DESCRIPTION_CODE,
            )
