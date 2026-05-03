#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Consumption time-series readers (table ``usage_consumption``).

The admin "usage" UI surfaces three views over the consolidated time-
series:

* per-day consumption between two dates,
* start/end snapshots for a window (used by credit dashboards), and
* the distinct-items list backing the consumer dropdown.

This module owns the rdb queries; the apiv4 service-layer keeps the
date-string parsing and any cross-batch orchestration (loops over
items / dates) where it stays close to the route signatures.
"""

from datetime import datetime

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.lib.usage.retention import (
    Tier,
    bucket_for,
    classify_tier,
    load_config,
)
from rethinkdb import r


def _zero_consumption(parameter_ids: list[str] | None = None) -> dict:
    """Return ``{param_id: 0}`` for the given ids, or for every parameter.

    Backs the ``.default(...)`` placeholder used when no consumption
    row exists for a given (item_id, item_type, date) — admin UI shows
    zeros instead of an empty cell. Distinct from
    ``UsageProcessed.get_default_consumption`` which returns the
    parameter's configured ``default`` value (not zero).
    """
    if parameter_ids:
        return {p: 0 for p in parameter_ids}
    with ConsumptionUsageProcessed._rdb_context():
        params = list(
            r.table("usage_parameter")
            .pluck("id")
            .run(ConsumptionUsageProcessed._rdb_connection)
        )
    return {p["id"]: 0 for p in params}


def subtract_dicts(dict1: dict, dict2: dict) -> dict:
    """Return ``dict1 - dict2`` recursively over numeric leaves.

    Used by the consumption series to apply reset-date subtraction:
    if a desktop's absolute consumption resets at date D, the post-D
    absolute is ``current_abs - reset_abs`` per parameter.
    """
    result: dict = {}
    for key in dict1:
        if isinstance(dict1[key], dict):
            result[key] = subtract_dicts(dict1[key], dict2.get(key, {}))
        elif isinstance(dict1[key], (int, float)):
            result[key] = dict1[key] - dict2.get(key, 0)
        else:
            result[key] = dict1[key]
    return result


class ConsumptionUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for ``usage_consumption`` reads."""

    @classmethod
    def list_distinct_items(cls, items_ids: list[str] | None = None) -> list[dict]:
        """Return distinct ``(item_id, item_name)`` pairs, optionally filtered.

        Called by the per-day consumption view to know which items to
        iterate over. When ``items_ids`` is ``None`` the full table is
        scanned (admin global view); otherwise the ``item_id`` index is
        hit so the read is cheap.
        """
        with cls._rdb_context():
            if items_ids is None:
                return list(
                    r.table("usage_consumption")
                    .pluck("item_id", "item_name")
                    .distinct()
                    .run(cls._rdb_connection)
                )
            return list(
                r.table("usage_consumption")
                .get_all(r.args(items_ids), index="item_id")
                .pluck("item_id", "item_name")
                .distinct()
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_distinct_items_by_consumer(
        cls,
        item_consumer: str,
        category_id: str | None = None,
    ) -> list[dict]:
        """Return distinct items for a given consumer (optionally per category).

        Drives the consumer dropdown's "items in this consumer" list.
        Without ``category_id`` returns ``(item_id, item_name)`` pairs;
        with it the result also carries ``item_consumer_category_id``
        so the manager scope is preserved client-side.
        """
        with cls._rdb_context():
            query = r.table("usage_consumption").get_all(
                item_consumer, index="item_consumer"
            )
            if category_id:
                query = query.pluck(
                    "item_id", "item_name", "item_consumer_category_id"
                ).filter({"item_consumer_category_id": category_id})
            else:
                query = query.pluck("item_id", "item_name")
            return list(query.distinct().run(cls._rdb_connection))

    @classmethod
    def get_item_date_consumption(
        cls,
        date: datetime,
        item_id: str,
        item_type: str,
        item_name: str,
        grouping_params: list[str] | None = None,
    ) -> dict:
        """Return the most-recent ``(abs, inc)`` consumption ``<= date``.

        Two queries: the first picks the latest absolute value before
        the cutoff (so the displayed ``abs`` reflects the running
        total), the second picks the same-day ``inc`` value if it
        exists (so the daily delta is exact, not extrapolated).
        Falls back to a zeros placeholder when no row matches.
        """
        if grouping_params:
            pluck = (
                {"abs": grouping_params, "inc": grouping_params},
                "date",
                "item_name",
                "item_id",
                "item_type",
                "item_consumer",
            )
        else:
            pluck = (
                "date",
                "inc",
                "abs",
                "item_name",
                "item_id",
                "item_type",
                "item_consumer",
            )

        default_consumption = (
            _zero_consumption(grouping_params)
            if grouping_params
            else _zero_consumption()
        )
        with cls._rdb_context():
            data = (
                r.table("usage_consumption")
                .get_all(item_id, index="item_id")
                .pluck(pluck)
                .filter((r.row["date"] <= date) & (r.row["item_type"] == item_type))
                .order_by("date")
                .nth(-1)
                .default(
                    {
                        "name": item_name,
                        "date": date,
                        "inc": default_consumption,
                        "abs": default_consumption,
                        "item_id": item_id,
                        "item_type": item_type,
                    }
                )
                .run(cls._rdb_connection)
            )
        # When old daily rows have been rolled up into weekly /
        # monthly buckets, the requested ``date`` no longer matches a
        # row's stored date. Resolve the date to its bucket boundary
        # for the same age before the equality check, so the lookup
        # finds the aggregate row instead of falling through to the
        # zero default.
        with cls._rdb_context():
            retention = load_config(cls._rdb_connection)
        tier = classify_tier(date, retention)
        bucketed_date = (
            bucket_for(date, tier) if tier in (Tier.WEEKLY, Tier.MONTHLY) else date
        )
        with cls._rdb_context():
            data["inc"] = (
                r.table("usage_consumption")
                .get_all(item_id, index="item_id")
                .pluck(pluck)
                .filter(
                    (r.row["date"] == bucketed_date) & (r.row["item_type"] == item_type)
                )
                .nth(0)
                .default({"inc": default_consumption})["inc"]
                .run(cls._rdb_connection)
            )
        # Surface the granularity so the UI can label aggregated
        # points (e.g. "September 2025: monthly aggregate"). Daily
        # rows behave identically to the pre-rollup contract.
        data["granularity"] = tier.value
        return data

    @classmethod
    def list_distinct_consumer_items(
        cls,
        item_consumer: str,
        item_category: str | None = None,
    ) -> list[dict]:
        """Return distinct consumer items annotated with category + username.

        Single rdb query that joins ``usage_consumption`` with
        ``categories`` / ``domains`` to produce the dropdown shape the
        admin UI consumes: ``{item_id, item_name, category_name,
        username}``.
        """
        with cls._rdb_context():
            query = (
                r.table("usage_consumption")
                .get_all(item_consumer, index="item_consumer")
                .merge(
                    lambda doc: {
                        "category_name": r.branch(
                            doc["item_consumer_category_id"].ne(None)
                            and (
                                doc["item_consumer"]
                                in ["desktop", "template", "user", "group"]
                            ),
                            r.table("categories")
                            .get(doc["item_consumer_category_id"])
                            .default({"name": None})["name"],
                            None,
                        ),
                        "username": r.branch(
                            doc["item_consumer"] in ["desktop", "template"]
                            and doc["item_id"] != "_total_",
                            r.table("domains")
                            .get(doc["item_id"])
                            .default({"username": None})["username"],
                            None,
                        ),
                    }
                )
            )
            if item_category:
                query = query.pluck(
                    "item_id",
                    "item_name",
                    "item_consumer_category_id",
                    "category_name",
                    "username",
                ).filter({"item_consumer_category_id": item_category})
            else:
                query = query.pluck("item_id", "item_name", "category_name", "username")
            return list(query.distinct().run(cls._rdb_connection))

    @classmethod
    def get_category_description(cls, category_id: str) -> str:
        """Return a category's ``description`` field, or empty string if missing."""
        with cls._rdb_context():
            return (
                r.table("categories")
                .get(category_id)
                .default({"description": ""})["description"]
                .run(cls._rdb_connection)
            )
