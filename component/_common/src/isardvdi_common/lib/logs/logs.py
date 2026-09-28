#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Layer 2 queries for the apiv4 admin logs endpoints.

Mirrors the table-level reads/writes against ``logs_desktops`` /
``logs_users`` that previously lived inline in apiv4's
``services/admin/domains.py``. The DataTables form parser stays in
apiv4 — only the rdb-shaped operations move here.

Tables touched:
* ``logs_desktops`` / ``logs_users`` — read paginated, count, group_by,
  batch delete.
* ``categories`` — read id+name map for ``category_grouping`` view.
"""

import time
from typing import TYPE_CHECKING, Optional

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r

if TYPE_CHECKING:
    from isardvdi_common.helpers.backup_writer import BackupWriter


# Fields each grouping view reduces to, and so the ones its DataTables order
# can name.
_DESKTOP_GROUP_FIELDS = (
    "count",
    "desktop_name",
    "desktop_id",
    "owner_user_name",
    "owner_user_id",
    "owner_group_name",
    "owner_group_id",
    "owner_category_name",
    "owner_category_id",
    "starting_time",
)
_USER_GROUP_FIELDS = (
    "count",
    "owner_user_name",
    "owner_user_id",
    "owner_group_name",
    "owner_group_id",
    "owner_category_name",
    "owner_category_id",
    "started_time",
)


class LogsProcessed(RethinkSharedConnection):
    """Table-level queries for ``logs_desktops`` / ``logs_users``.

    The DataTables form contract is opaque here: the caller hands a
    ``parsed`` dict (already-flattened form data) and ``view`` keyword;
    this class translates it into the right rdb chain.
    """

    @staticmethod
    def _order_from_parsed(parsed: dict) -> tuple:
        """``(field, descending)`` of the first DataTables order clause."""
        if not parsed.get("order") or not len(parsed["order"]):
            return None, False
        columns = parsed["columns"]
        if isinstance(columns, dict):
            columns = list(columns.values())
        col_idx = int(parsed["order"][0]["column"])
        field = columns[col_idx]["data"] if col_idx < len(columns) else None
        return field, parsed["order"][0]["dir"] == "desc"

    @staticmethod
    def _order_grouped(query, parsed: dict, fields: tuple):
        """Order an ungrouped result by the DataTables column, if it is one.

        The grouped result is an array already, so any of its fields can
        be sorted on — but only its own: the raw table columns the order
        may name do not survive the grouping.
        """
        field, descending = LogsProcessed._order_from_parsed(parsed)
        if field not in fields:
            return query
        return query.order_by(r.desc(field) if descending else r.asc(field))

    @classmethod
    def _build_query(
        cls,
        table: str,
        parsed: dict,
        scope_category_id: str | None = None,
        ordered: bool = True,
    ) -> tuple:
        """Build the base rdb query for ``parsed`` DataTables payload.

        ``scope_category_id`` restricts the query to rows whose
        ``owner_category_id`` matches — used to scope managers to
        their own category before any DataTables filter / order is
        applied. ``ordered=False`` leaves the ordering off, for the
        grouping views: their DataTables order names a column of the
        grouped result, which means nothing to a row of the table.

        Returns ``(query, table_indexes)``. Internal helper — held in
        the same connection scope as the count/data run that consumes
        it (see ``query_paginated``).
        """
        with cls._rdb_context():
            table_indexes = r.table(table).index_list().run(cls._rdb_connection)

        query = r.table(table)

        order_field, descending = cls._order_from_parsed(parsed)
        if not ordered:
            order_field = None
        indexed_order = order_field in table_indexes

        range_start = range_end = range_field = None
        if parsed.get("range"):
            s = parsed["range"].get("start")
            e = parsed["range"].get("end")
            range_field = parsed["range"].get("field")
            if s and e and range_field:
                range_start = r.iso8601((s if "T" in s else s + "T00:00:00") + "Z")
                range_end = r.iso8601((e if "T" in e else e + "T23:59:59") + "Z")
            else:
                range_field = None

        # between() reads an index off the table itself, and a table can only be
        # walked through one index, so it is available whenever the ordering is
        # not claiming a different one.
        range_on_index = range_field is not None and (
            not indexed_order or order_field == range_field
        )
        if range_on_index:
            query = query.between(range_start, range_end, index=range_field)

        # An indexed order goes on the table first and keeps the query a lazy
        # stream, so the filters below cost nothing to add. A non-indexed one
        # has to materialise and sort whatever reaches it, which trips rethink's
        # 100k array limit on these tables — it is applied last, once the
        # filters have narrowed the set.
        if indexed_order:
            direction = r.desc if descending else r.asc
            query = query.order_by(index=direction(order_field))

        # Filter by category
        if scope_category_id is not None:
            query = query.filter({"owner_category_id": scope_category_id})

        if range_field is not None and not range_on_index:
            query = query.filter(
                lambda doc: doc[range_field].during(range_start, range_end)
            )

        # Add search filters
        if parsed.get("columns"):
            columns_iter = parsed["columns"]
            if isinstance(columns_iter, dict):
                columns_iter = columns_iter.values()
            for column in columns_iter:
                if (
                    column.get("data", "") != ""
                    and column.get("search", {}).get("value", "") != ""
                ):
                    col_data = column["data"]
                    search_val = column["search"]["value"]
                    query = query.filter(
                        lambda doc, cd=col_data, sv=search_val: doc[cd].match(sv)
                    )

        # Add single-field filter (e.g. filter by desktop_id)
        if parsed.get("filter_field") and parsed.get("filter_value"):
            ff = parsed["filter_field"]
            fv = parsed["filter_value"]
            query = query.filter(lambda doc: doc[ff] == fv)

        if order_field is not None and not indexed_order:
            orders = parsed["order"]
            if isinstance(orders, dict):
                orders = orders.values()
            for order in orders:
                col_idx = int(order["column"])
                cols = parsed["columns"]
                if isinstance(cols, dict):
                    cols = list(cols.values())
                col_data = cols[col_idx]["data"] if col_idx < len(cols) else None
                if col_data:
                    direction = r.desc if order["dir"] == "desc" else r.asc
                    query = query.order_by(direction(col_data))

        # Add pluck
        if parsed.get("pluck"):
            query = query.pluck(parsed["pluck"])

        return query, table_indexes

    @classmethod
    def query_paginated(
        cls,
        table: str,
        parsed: dict,
        view: str = "raw",
        scope_category_id: str | None = None,
    ) -> dict:
        """Execute a DataTables logs query.

        ``view`` selects the result shape:
        - ``"raw"`` — paginated rows + total/filtered counts.
        - ``"desktop_grouping"`` (logs_desktops only) — group by
          desktop_id with count + last starting_time.
        - ``"user_grouping"`` (logs_users only) — group by owner_user_id
          with count + last started_time.
        - ``"category_grouping"`` — distinct entity counts per category
          with totals.

        ``scope_category_id`` restricts the result to rows belonging to
        a single category — apiv4 routes pass it through for managers
        so they only see their own category's logs (apiv3 used
        ``@is_admin_or_manager`` with category-scoping inside the view).
        """
        if view == "raw":
            query, table_indexes = cls._build_query(
                table, parsed, scope_category_id=scope_category_id
            )
            with cls._rdb_context():
                total = r.table(table).count().run(cls._rdb_connection)
                filtered = query.count().run(cls._rdb_connection)
                paged_query = query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged_query.run(cls._rdb_connection))
            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": total,
                "recordsFiltered": filtered,
                "data": data,
                "indexs": table_indexes,
            }

        if view == "desktop_grouping" and table == "logs_desktops":
            # Grouping the bare table materialises one element per group, past
            # rethink's 100k array limit on a table this size, and silently
            # drops the date range the caller asked for. Group what the
            # filters left instead.
            group_query, _ = cls._build_query(
                table, parsed, scope_category_id=scope_category_id, ordered=False
            )
            group_query = (
                group_query.group("desktop_id")
                .map(
                    lambda log_entry: {
                        "count": 1,
                        "desktop_name": log_entry["desktop_name"],
                        "desktop_id": log_entry["desktop_id"],
                        "owner_user_name": log_entry["owner_user_name"],
                        "owner_user_id": log_entry["owner_user_id"],
                        "owner_group_name": log_entry["owner_group_name"],
                        "owner_group_id": log_entry["owner_group_id"],
                        "owner_category_name": log_entry["owner_category_name"],
                        "owner_category_id": log_entry["owner_category_id"],
                        "starting_time": log_entry["starting_time"],
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "desktop_name": left["desktop_name"],
                        "desktop_id": left["desktop_id"],
                        "owner_user_name": left["owner_user_name"],
                        "owner_user_id": left["owner_user_id"],
                        "owner_group_name": left["owner_group_name"],
                        "owner_group_id": left["owner_group_id"],
                        "owner_category_name": left["owner_category_name"],
                        "owner_category_id": left["owner_category_id"],
                        "starting_time": right["starting_time"],
                    }
                )
                .ungroup()["reduction"]
            )
            group_query = cls._order_grouped(group_query, parsed, _DESKTOP_GROUP_FIELDS)
            with cls._rdb_context():
                # Both counts are groups: the rows behind them are not what
                # this view paginates.
                groups = group_query.count().run(cls._rdb_connection)
                paged = group_query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged.run(cls._rdb_connection))
            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": groups,
                "recordsFiltered": groups,
                "data": data,
                "indexs": [],
            }

        if view == "user_grouping" and table == "logs_users":
            # Grouping the bare table materialises one element per group, past
            # rethink's 100k array limit on a table this size, and silently
            # drops the date range the caller asked for. Group what the
            # filters left instead.
            group_query, _ = cls._build_query(
                table, parsed, scope_category_id=scope_category_id, ordered=False
            )
            group_query = (
                group_query.group("owner_user_id")
                .map(
                    lambda log_entry: {
                        "count": 1,
                        "owner_user_name": log_entry["owner_user_name"],
                        "owner_user_id": log_entry["owner_user_id"],
                        "owner_group_name": log_entry["owner_group_name"],
                        "owner_group_id": log_entry["owner_group_id"],
                        "owner_category_name": log_entry["owner_category_name"],
                        "owner_category_id": log_entry["owner_category_id"],
                        "started_time": log_entry["started_time"],
                    }
                )
                .reduce(
                    lambda left, right: {
                        "count": left["count"] + right["count"],
                        "owner_user_name": left["owner_user_name"],
                        "owner_user_id": left["owner_user_id"],
                        "owner_group_name": left["owner_group_name"],
                        "owner_group_id": left["owner_group_id"],
                        "owner_category_name": left["owner_category_name"],
                        "owner_category_id": left["owner_category_id"],
                        "started_time": right["started_time"],
                    }
                )
                .ungroup()["reduction"]
            )
            group_query = cls._order_grouped(group_query, parsed, _USER_GROUP_FIELDS)
            with cls._rdb_context():
                # Both counts are groups: the rows behind them are not what
                # this view paginates.
                groups = group_query.count().run(cls._rdb_connection)
                paged = group_query.skip(int(parsed.get("start", 0))).limit(
                    int(parsed.get("length", 25))
                )
                data = list(paged.run(cls._rdb_connection))
            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": groups,
                "recordsFiltered": groups,
                "data": data,
                "indexs": [],
            }

        if view == "category_grouping":
            with cls._rdb_context():
                categories = {
                    item["id"]: item["name"]
                    for item in r.table("categories")
                    .pluck("id", "name")
                    .run(cls._rdb_connection)
                }

            pluck_field = "desktop_id" if table == "logs_desktops" else "owner_user_id"
            cat_query = r.table(table)
            if scope_category_id is not None:
                cat_query = cat_query.filter({"owner_category_id": scope_category_id})
            cat_query = cat_query.group(index="owner_category_id")

            if parsed.get("range"):
                s = parsed["range"]["start"]
                e = parsed["range"]["end"]
                start_str = (s if "T" in s else s + "T00:00:00") + "Z"
                end_str = (e if "T" in e else e + "T23:59:59") + "Z"
                cat_query = cat_query.filter(
                    lambda doc: doc[parsed["range"]["field"]].during(
                        r.iso8601(start_str), r.iso8601(end_str)
                    )
                )

            cat_query = cat_query.pluck(pluck_field).distinct().count()

            with cls._rdb_context():
                cat_data = cat_query.run(cls._rdb_connection, array_limit=500000)

            group_index = "owner_category_id"
            totals_query = r.table(table).group(index=group_index)
            totals_query = (
                totals_query.map(lambda log_entry: {"count": 1})
                .reduce(lambda left, right: {"count": left["count"] + right["count"]})
                .ungroup()["reduction"]
            )

            with cls._rdb_context():
                totals = list(totals_query.run(cls._rdb_connection))

            result_data = [
                {
                    "total": next(
                        (
                            t.get("count", 0)
                            for t in totals
                            if t.get("owner_category_id") == key
                        ),
                        0,
                    ),
                    "count": value,
                    "owner_category_name": categories.get(key, "[DELETED]" + key),
                    "owner_category_id": key,
                }
                for key, value in cat_data.items()
            ]

            if parsed.get("order") and len(parsed["order"]):
                col = parsed["order"][0].get("column", "0")
                if col == "1":
                    order_key = "total"
                elif col == "2":
                    order_key = "count"
                elif col == "3":
                    order_key = "owner_category_name"
                else:
                    order_key = "count"
                reverse = parsed["order"][0].get("dir", "asc") == "desc"
                result_data = sorted(
                    result_data, key=lambda x: x[order_key], reverse=reverse
                )

            return {
                "draw": int(parsed.get("draw", 1)),
                "recordsTotal": len(result_data),
                "recordsFiltered": len(result_data),
                "data": result_data,
                "indexs": [],
            }

        return {}

    @staticmethod
    def _ordered_log_table(
        table: str,
        time_index: str,
        start_date: str | None,
        end_date: str | None,
    ):
        """Table ordered newest-first by ``time_index``, narrowed to the date range.

        ``order_by`` without ``index=`` materialises the whole table before
        sorting, which blows past rethink's 100k array limit on these tables.
        Going through the index keeps the query a lazy stream, so the
        ``limit`` downstream stops the scan early.
        """
        query = r.table(table)
        if start_date or end_date:
            start = r.minval
            end = r.maxval
            if start_date:
                s = (
                    start_date if "T" in start_date else start_date + "T00:00:00"
                ) + "Z"
                start = r.iso8601(s)
            if end_date:
                e = (end_date if "T" in end_date else end_date + "T23:59:59") + "Z"
                end = r.iso8601(e)
            query = query.between(start, end, index=time_index, right_bound="closed")
        return query.order_by(index=r.desc(time_index))

    @classmethod
    def list_simple_desktop(
        cls,
        category_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
        desktop_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Plain (non-DataTables) list of desktop logs.

        ``category_id`` scopes managers to their own category; admins
        pass ``None``.
        """
        query = cls._ordered_log_table(
            "logs_desktops", "starting_time", start_date, end_date
        )
        if category_id:
            query = query.filter({"owner_category_id": category_id})
        if desktop_id:
            query = query.filter({"desktop_id": desktop_id})
        if user_id:
            query = query.filter({"owner_user_id": user_id})
        query = query.skip(offset).limit(limit)
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def list_simple_user(
        cls,
        category_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 100,
        offset: int = 0,
        user_id: str | None = None,
        group_id: str | None = None,
    ) -> list[dict]:
        """Plain (non-DataTables) list of user logs.

        ``category_id`` scopes managers to their own category; admins
        pass ``None``.
        """
        query = cls._ordered_log_table(
            "logs_users", "started_time", start_date, end_date
        )
        if category_id:
            query = query.filter({"owner_category_id": category_id})
        if user_id:
            query = query.filter({"owner_user_id": user_id})
        if group_id:
            query = query.filter({"owner_group_id": group_id})
        query = query.skip(offset).limit(limit)
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def delete_batch(
        cls,
        table: str,
        ids: list[str],
        batch_size: int = 50000,
        *,
        backup: "Optional[BackupWriter]" = None,
    ) -> None:
        """Delete a batch of log rows from ``table``.

        Splits ``ids`` into ``batch_size`` chunks so very large
        deletions don't blow rdb's array_limit. Used by the async
        ``delete_old_*_logs`` endpoints.

        When ``backup`` is provided, each chunk is fetched in full
        and streamed to the writer BEFORE the delete fires, so an
        admin always has a recoverable JSONL.gz dump of every row
        that disappeared from ``logs_desktops`` / ``logs_users``.
        Both reads and writes use the same outer ``_rdb_context``,
        so the fetch + delete are sequential on a single
        connection — no risk of the row vanishing between the two
        statements.
        """
        with cls._rdb_context():
            for i in range(0, len(ids), batch_size):
                batch_ids = ids[i : i + batch_size]
                if backup is not None:
                    rows = list(
                        r.table(table)
                        .get_all(r.args(batch_ids))
                        .run(cls._rdb_connection)
                    )
                    backup.write_rows(rows)
                r.table(table).get_all(r.args(batch_ids)).delete().run(
                    cls._rdb_connection
                )

    # Retention delete tuning — hardcoded defaults (promotable to the
    # ``config`` table later without a schema change if operators need it).
    #
    # Per-table retention index: the earliest ALWAYS-PRESENT, indexed lifecycle
    # timestamp. A row is old iff any of its event times precede the cutoff,
    # which — that field being the row's minimum and always present — is exactly
    # ``<field> < cutoff``. ``logs_desktops`` always has ``starting_time``,
    # while an incomplete session never reaches ``started_time``, so keying on
    # ``started_time`` would leak those rows; ``logs_users`` always has
    # ``started_time``.
    RETENTION_INDEX = {
        "logs_desktops": "starting_time",
        "logs_users": "started_time",
    }
    RETENTION_PAGE_SIZE = 2000
    RETENTION_PAGE_PAUSE = 0.1

    @classmethod
    def count_older(cls, table: str, cutoff) -> int:
        """Count rows older than ``cutoff`` via the table's retention index.

        Server-side range count on the earliest-timestamp index — never
        materialises ids, so it stays cheap even on a multi-million-row
        ``logs_desktops``.
        """
        with cls._rdb_context():
            return (
                r.table(table)
                .between(r.minval, cutoff, index=cls.RETENTION_INDEX[table])
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    def delete_old_streamed(
        cls,
        table: str,
        cutoff,
        *,
        backup: "Optional[BackupWriter]" = None,
        page_size: int = RETENTION_PAGE_SIZE,
        pause: float = RETENTION_PAGE_PAUSE,
    ) -> int:
        """Delete rows older than ``cutoff`` in paced, index-bounded pages.

        Retention keys on the table's earliest ALWAYS-PRESENT indexed lifecycle
        timestamp (``RETENTION_INDEX``): a row is old iff any event timestamp
        precedes ``cutoff``, which — that field being the row's minimum and
        always present — is exactly ``<field> < cutoff``. Each iteration deletes
        the oldest ``page_size`` rows of that index range with a fresh pooled
        connection and ``durability='soft'`` (logs are disposable), so peak
        memory is O(page) and there is no full-table scan. Naturally resumable:
        deleted rows leave the range, so a crash/redeploy just continues from
        the current oldest. With ``backup`` the deleted rows come back via
        ``return_changes`` in the same op and are streamed out before the next
        page.
        """
        deleted = 0
        while True:
            with cls._rdb_context():
                res = (
                    r.table(table)
                    .between(r.minval, cutoff, index=cls.RETENTION_INDEX[table])
                    .limit(page_size)
                    .delete(return_changes=bool(backup), durability="soft")
                    .run(cls._rdb_connection)
                )
            if backup is not None:
                backup.write_rows(
                    [c["old_val"] for c in res.get("changes", []) if c.get("old_val")]
                )
            n = res.get("deleted", 0)
            deleted += n
            if n < page_size:
                break
            time.sleep(pause)
        return deleted
