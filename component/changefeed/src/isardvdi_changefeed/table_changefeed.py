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


import asyncio
import logging as log
from datetime import datetime

import redis.asyncio as aioredis
import redis.exceptions as redis_err
from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from isardvdi_common.connections.redis_urls import changefeed_url
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.connections.rethink_dedicated_connection import (
    dedicated_async_connection,
)
from rethinkdb import r
from rethinkdb.errors import ReqlDriverError


def sanitize(obj):
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(i) for i in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def redact_path(doc, path):
    """Delete the leaf key at ``path`` (a list of keys) from ``doc`` in place.

    Walks only through dict parents, so the deletion is skipped when any
    parent along the path is absent or not a dict. This lets us strip a
    secret leaf (e.g. ``vpn.wireguard.keys.private``) without disturbing a
    reset sentinel where the parent is a scalar (e.g. ``keys`` is ``False``,
    which the wireguard consumer relies on to detect a key reset).
    """
    if not isinstance(doc, dict):
        return
    for key in path[:-1]:
        doc = doc.get(key)
        if not isinstance(doc, dict):
            return
    doc.pop(path[-1], None)


# Secret fields stripped from each change before it is published/streamed,
# keyed by table; each value is a list of dotted paths (key lists). Kept in
# code rather than tables.json because tables.json is the sha-pinned codegen
# input for the wire schema, whereas this is a runtime safety filter applied
# after the pluck. Only the leaf is deleted, so reset sentinels are preserved
# (the wireguard consumer detects a key reset via ``keys is False``).
REDACT_FIELDS = {
    "users": [["vpn", "wireguard", "keys", "private"]],
}


class TableChangefeed(RethinkSharedConnection):
    def __init__(
        self,
        tables,
        redis,
    ):
        self.tables = tables
        self.redis = redis
        self.stream_tables = {t["table"] for t in tables if t.get("stream")}
        self._per_table = {
            t["table"]: {
                "stream_maxlen": t.get("stream_maxlen", 10000),
                "squash": t.get("squash", 0.5),
            }
            for t in tables
        }
        self._retry_delay = 5

    async def _wait_for_tables(self):
        """Wait until the RethinkDB database and all required tables exist."""
        required = {t["table"] for t in self.tables}
        delay = 2
        while True:
            try:
                existing = await asyncio.to_thread(self._fetch_table_list)
                missing = required - existing
                if not missing:
                    log.info("All required tables exist, starting changefeed")
                    return
                log.info("Waiting for %d tables: %s", len(missing), missing)
            except Exception:
                log.exception("DB readiness check failed")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    def _fetch_table_list(self):
        """Sync helper run on a worker thread by ``_wait_for_tables``.

        Bound to ``self`` (not ``cls``) so the existing
        ``TestWaitForTables`` fixtures, which mock
        ``cf._rdb_context`` / ``cf._rdb_connection`` instance-side, keep
        working.
        """
        with self._rdb_context():
            return set(r.table_list().run(self._rdb_connection))

    async def run(self):
        while True:
            try:
                await self._wait_for_tables()
                log.info(f"Starting changefeed for tables {self.tables}")
                all_tables = self.tables[
                    :
                ]  # copy to avoid changing the original and errors when reconnecting
                changes_query = r.table(all_tables[0]["table"]).merge(
                    {"table": all_tables[0]["table"]}
                )
                if "pluck" in all_tables[0]:
                    changes_query = changes_query.pluck(
                        all_tables[0]["pluck"] + ["table"]
                    )  # Must include the table name in the pluck
                changes_query = changes_query.changes(
                    include_initial=False,
                    squash=self._per_table[all_tables[0]["table"]]["squash"],
                )
                all_tables = all_tables[
                    1:
                ]  # Remove the first table as it's already added

                # Add the rest of the tables to the changes query with union
                for table in all_tables:
                    if table.get("pluck"):
                        changes_query = changes_query.union(
                            r.table(table["table"])
                            .merge({"table": table["table"]})
                            .pluck(
                                table["pluck"] + ["table"]
                            )  # Must include the table name in the pluck
                            .changes(
                                include_initial=False,
                                squash=self._per_table[table["table"]]["squash"],
                            )
                        )
                    else:
                        changes_query = changes_query.union(
                            r.table(table["table"])
                            .merge({"table": table["table"]})
                            .changes(
                                include_initial=False,
                                squash=self._per_table[table["table"]]["squash"],
                            )
                        )

                # The cursor is open for the lifetime of the process —
                # holding a pool slot across that span would starve the
                # short-query traffic in `_wait_for_tables` and any
                # future shared-pool callers in this service. Use a
                # dedicated connection the loop owns; close it on
                # reconnect or exception so a hung socket can't outlive
                # the cursor.
                await self._consume_cursor(changes_query)
                self._retry_delay = 5
            except ReqlDriverError:
                log.warning("RethinkDB connection lost, attempting to reconnect...")
            except Exception:
                log.exception("Unexpected error in changefeed loop")

            # Wait before reconnecting
            log.info("Waiting %ds before retrying...", self._retry_delay)
            await asyncio.sleep(self._retry_delay)
            self._retry_delay = min(self._retry_delay * 2, 60)

    async def _consume_cursor(self, changes_query):
        """Run ``changes_query`` against a dedicated asyncio-native
        connection and dispatch each change to ``_publish_change``.

        Native ``async for change in cursor:`` (P2 #10, 2026-05-02):
        the cursor's socket recv yields control to the asyncio event
        loop between deliveries via :class:`AsyncioCursor.__anext__`,
        so other coroutines on the same loop (health checks, metrics
        endpoints) keep getting scheduled — without the worker-thread
        + ``asyncio.Queue`` plumbing the previous P2 #8 implementation
        used. ``ReqlDriverError`` raised mid-iteration (socket loss)
        propagates naturally to the outer ``run`` loop's reconnect
        branch.

        The connection is owned by this method: opened on entry,
        closed on every exit path (normal completion, exception,
        cancellation). Holding the cursor on a shared-pool slot
        would starve every other caller of the pool — see the
        comment in ``run`` for the design rationale.
        """
        cursor_conn = await dedicated_async_connection()
        cursor = None
        try:
            cursor = await changes_query.run(cursor_conn)
            async for change in cursor:
                await self._publish_change(change)
        finally:
            # Close the cursor first so the rdb server stops streaming.
            # ``cursor.close`` is async on :class:`AsyncioCursor`; it
            # may race with cancellation (the cursor is mid-recv) but
            # the driver tolerates a double-close. Tests stub the
            # cursor with a Mock that has no ``close`` — guard with
            # try/except for that case.
            if cursor is not None:
                try:
                    await cursor.close()
                except Exception:
                    log.debug(
                        "Cursor close raised (expected on test stubs / dropped sockets)",
                        exc_info=True,
                    )
            try:
                await cursor_conn.close(noreply_wait=False)
            except Exception:
                log.exception("Failed to close changefeed cursor connection")

    async def _publish_change(self, change):
        change_val = change.get("new_val") or change.get("old_val")
        if change_val is None:
            log.debug("Change with neither new_val nor old_val, skipping")
            return
        log.debug(f"Change detected: {change_val}")

        table_name = change_val.get("table")
        subscriber = TABLE_TO_SUBSCRIBER.get(table_name)
        if subscriber is None:
            log.warning(f"No subscriber for table: {table_name}, skipping")
            return

        # Strip configured secret fields (e.g. wireguard private keys) from
        # both sides of the change before it is published/streamed.
        redact = REDACT_FIELDS.get(table_name, [])
        if redact:
            for side in ("new_val", "old_val"):
                side_val = change.get(side)
                if isinstance(side_val, dict):
                    for path in redact:
                        redact_path(side_val, path)

        try:
            payload = subscriber.serialize(sanitize(change))
        except Exception:
            log.exception(
                "Serialization failed for table=%s id=%s; dropping change",
                table_name,
                change_val.get("id"),
            )
            return

        try:
            await self.redis.publish(table_name, payload)
            if table_name in self.stream_tables:
                await self.redis.xadd(
                    f"stream:{table_name}",
                    {"data": payload},
                    maxlen=self._per_table[table_name]["stream_maxlen"],
                    approximate=True,
                )
        except (redis_err.ConnectionError, redis_err.TimeoutError) as emit_err:
            log.warning(
                "Redis publish failed: %s. Attempting to reconnect...", emit_err
            )
            await self.reconnect_redis()

    async def reconnect_redis(self):
        try:
            self.redis = aioredis.from_url(changefeed_url(), decode_responses=True)
            await self.redis.ping()
            log.info("Reconnected to Redis successfully.")
        except Exception as e:
            log.error(f"Failed to reconnect to Redis: {e}")
            raise
