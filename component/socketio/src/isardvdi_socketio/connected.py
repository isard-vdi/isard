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

"""Publishes this process's Socket.IO connections to redis for the stats endpoint."""

import asyncio
import contextlib
import logging
import socket

from isardvdi_common.lib.stats.connected import KEY_PREFIX, KEY_TTL_S

log = logging.getLogger(__name__)

HEARTBEAT_S = KEY_TTL_S / 3


class Presence:
    def __init__(self, redis, key=None):
        self.redis = redis
        self.key = key or f"{KEY_PREFIX}{socket.gethostname()}"
        self.sids: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._heartbeat_task = None

    async def add(self, sid, user_id):
        self.sids[sid] = user_id or ""
        try:
            async with self._lock:
                async with self.redis.pipeline(transaction=True) as pipe:
                    pipe.hset(self.key, sid, self.sids[sid])
                    pipe.expire(self.key, KEY_TTL_S)
                    await pipe.execute()
        except Exception:
            log.warning("could not record socketio connection %s", sid, exc_info=True)

    async def remove(self, sid):
        if self.sids.pop(sid, None) is None:
            return
        try:
            async with self._lock:
                await self.redis.hdel(self.key, sid)
        except Exception:
            log.warning("could not drop socketio connection %s", sid, exc_info=True)

    async def publish(self):
        """Replace the redis hash with this process's connections and renew its TTL."""
        async with self._lock:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.delete(self.key)
                if self.sids:
                    pipe.hset(self.key, mapping=dict(self.sids))
                    pipe.expire(self.key, KEY_TTL_S)
                await pipe.execute()

    async def _heartbeat(self):
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            try:
                await self.publish()
            except Exception:
                log.warning("could not publish socketio connections", exc_info=True)

    async def start(self):
        self.sids.clear()
        try:
            await self.publish()
        except Exception:
            log.warning("could not clear socketio connections", exc_info=True)
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def stop(self):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
        self.sids.clear()
        try:
            async with self._lock:
                await self.redis.delete(self.key)
        except Exception:
            log.warning("could not clear socketio connections", exc_info=True)
