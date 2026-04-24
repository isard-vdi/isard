#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import asyncio
import logging

from config import settings
from fastapi import Depends, FastAPI, HTTPException
from rethinkdb import RethinkDB
from rethinkdb.errors import RqlDriverError

log = logging.getLogger(__name__)

# Initialize RethinkDB client
r = RethinkDB()
# app = FastAPI()


async def get_db_long_lived_conn():
    """Retrieve a long-lived RethinkDB connection in a background thread."""
    try:
        return await asyncio.to_thread(
            r.connect,
            settings.RETHINKDB_HOST,
            settings.RETHINKDB_PORT,
            db=settings.RETHINKDB_DB,
        )
    except RqlDriverError as e:
        raise HTTPException(status_code=500, detail="Database connection error") from e


class RethinkDBPool:
    def __init__(
        self,
        host: str = settings.RETHINKDB_HOST,
        port: int = settings.RETHINKDB_PORT,
        db: str = settings.RETHINKDB_DB,
        pool_size: int = settings.RETHINKDB_POOL_SIZE,  # adjust in settings or default to 10
        max_pending: int = settings.DB_POOL_MAX_PENDING,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.pool_size = pool_size
        self.max_pending = max_pending
        self.pool = asyncio.Queue()
        self._pending_waiters = 0

    async def initialize_pool(self):
        """Initialize a pool of database connections."""
        for _ in range(self.pool_size):
            # Fix: Use asyncio.to_thread to run connect() in a separate thread
            conn = await asyncio.to_thread(r.connect, self.host, self.port, db=self.db)
            await self.pool.put(conn)

    async def get_connection(self):
        """Retrieve a healthy connection from the pool with a timeout."""
        if self.max_pending > 0 and self._pending_waiters >= self.max_pending:
            log.warning(
                "DB pool max pending waiters exceeded: pending=%d, max_pending=%d, pool_size=%d, available=%d",
                self._pending_waiters,
                self.max_pending,
                self.pool_size,
                self.pool.qsize(),
            )
            raise HTTPException(
                status_code=503,
                detail="Database is overloaded. Try again later.",
            )

        self._pending_waiters += 1
        try:
            conn = await asyncio.wait_for(
                self.pool.get(), timeout=settings.RETHINKDB_CONNECTION_TIMEOUT
            )
        except asyncio.TimeoutError:
            log.warning(
                "DB pool connection timeout: pool_size=%d, available=%d, pending=%d, timeout=%s",
                self.pool_size,
                self.pool.qsize(),
                self._pending_waiters,
                settings.RETHINKDB_CONNECTION_TIMEOUT,
            )
            raise HTTPException(
                status_code=503, detail="Database is busy. Try again later."
            )
        finally:
            self._pending_waiters -= 1

        # Verify the connection is still alive; reconnect if stale
        if not conn.is_open():
            try:
                conn.close()
            except Exception:
                pass
            conn = await asyncio.to_thread(r.connect, self.host, self.port, db=self.db)

        log.debug(
            "DB pool connection acquired: available=%d/%d, pending=%d",
            self.pool.qsize(),
            self.pool_size,
            self._pending_waiters,
        )
        return conn

    async def release_connection(self, conn):
        """Return the connection to the pool."""
        await self.pool.put(conn)
        log.debug(
            "DB pool connection released: available=%d/%d, pending=%d",
            self.pool.qsize(),
            self.pool_size,
            self._pending_waiters,
        )

    def get_pool_stats(self):
        """Return current pool statistics."""
        return {
            "pool_size": self.pool_size,
            "available": self.pool.qsize(),
            "in_use": self.pool_size - self.pool.qsize(),
            "pending_waiters": self._pending_waiters,
            "max_pending": self.max_pending,
        }

    async def close_pool(self):
        """Close all connections in the pool."""
        while not self.pool.empty():
            conn = await self.pool.get()
            conn.close()


# Create a shared connection pool instance
db_pool = RethinkDBPool()


# @app.on_event("startup")
# async def startup():
#     """Initialize the connection pool at application startup."""
#     await db_pool.initialize_pool()


# @app.on_event("shutdown")
# async def shutdown():
#     """Close all connections when the application stops."""
#     await db_pool.close_pool()


async def get_db_conn():
    """Dependency to borrow a connection from the pool with timeout handling."""
    conn = await db_pool.get_connection()
    try:
        yield conn
    finally:
        await db_pool.release_connection(conn)


# @app.get("/items")
# async def get_items(conn=Depends(get_db)):
#     """Fetch all items from the 'items' table."""
#     cursor = await r.table("items").run(conn)
#     items = await cursor.to_list()
#     return {"data": items}


# @app.post("/items")
# async def create_item(item: dict, conn=Depends(get_db)):
#     """Insert an item into the 'items' table."""
#     result = await r.table("items").insert(item).run(conn)
#     return {"inserted": result["inserted"]}
