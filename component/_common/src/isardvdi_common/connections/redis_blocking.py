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

"""Redis client construction for the commands that block server-side."""

from typing import Any

import redis
import redis.asyncio as aioredis

# The block a stream consumer asks the server to hold a read open for.
STREAM_BLOCK_MS = 5000

# The client's deadline starts when it sends, the server's block timer only
# when it receives, so at equal values the client always expires first.
SOCKET_TIMEOUT_MARGIN_S = 5.0

SOCKET_CONNECT_TIMEOUT_S = 5.0


def socket_timeout_for(block_ms: int | float | None) -> float:
    """The socket deadline a read blocking ``block_ms`` needs."""
    if not block_ms or block_ms <= 0:
        raise ValueError(
            f"block_ms must be a positive number of milliseconds, got {block_ms!r}"
        )
    return block_ms / 1000.0 + SOCKET_TIMEOUT_MARGIN_S


def _connection_kwargs(
    block_ms: int | float | None, kwargs: dict[str, Any]
) -> dict[str, Any]:
    required = socket_timeout_for(block_ms)
    socket_timeout = kwargs.pop("socket_timeout", None)
    if socket_timeout is None:
        socket_timeout = required
    elif socket_timeout <= block_ms / 1000.0:
        raise ValueError(
            f"socket_timeout {socket_timeout} does not outlast a {block_ms} ms block"
        )
    kwargs.setdefault("socket_connect_timeout", SOCKET_CONNECT_TIMEOUT_S)
    kwargs["socket_timeout"] = socket_timeout
    return kwargs


def blocking_client(
    url: str, block_ms: int | float | None = STREAM_BLOCK_MS, **kwargs: Any
) -> redis.Redis:
    """A client whose socket outlasts the longest read it will issue."""
    return redis.from_url(url, **_connection_kwargs(block_ms, kwargs))


def async_blocking_client(
    url: str, block_ms: int | float | None = STREAM_BLOCK_MS, **kwargs: Any
) -> aioredis.Redis:
    """``blocking_client`` for ``redis.asyncio``, which has the same default."""
    return aioredis.from_url(url, **_connection_kwargs(block_ms, kwargs))
