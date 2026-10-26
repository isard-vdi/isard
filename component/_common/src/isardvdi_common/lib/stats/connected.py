#
#   Copyright © 2026 IsardVDI
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

"""Socket.IO connections, one redis hash of sid to user id per socketio process."""

KEY_PREFIX = "socketio:connected:"
KEY_TTL_S = 60


def count_connected(redis) -> dict:
    users = set()
    sockets = 0
    for key in redis.scan_iter(match=f"{KEY_PREFIX}*", count=100):
        values = redis.hvals(key)
        sockets += len(values)
        for value in values:
            if isinstance(value, bytes):
                value = value.decode()
            if value:
                users.add(value)
    return {"users": len(users), "sockets": sockets}
