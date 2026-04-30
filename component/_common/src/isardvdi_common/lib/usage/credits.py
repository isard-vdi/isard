#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage-credit CRUD + interval reconciliation (table ``usage_credit``).

A credit links an item (category / user / group / etc.) to a usage
limit over a date interval. Credits cannot overlap on the same
``(item_id, item_type, grouping_id)`` triple — overlapping rows are
either trimmed or deleted via ``_cut_existing_credits`` to keep the
interval set well-ordered.
"""

from datetime import datetime, timedelta

import pytz
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.lib.usage.limits import validate_usage_limits
from rethinkdb import r


class CreditsUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for ``usage_credit`` rows."""

    @classmethod
    def list_all(cls) -> list[dict]:
        """Return every credit row, merged with category + grouping names."""
        with cls._rdb_context():
            return list(
                r.table("usage_credit")
                .merge(
                    lambda row: {
                        "category_name": r.table("categories")
                        .get(row["item_id"])
                        .default({"name": ""})["name"],
                        "item_description": r.table("categories")
                        .get(row["item_id"])
                        .default({"description": ""})["description"],
                    }
                )
                .merge(
                    lambda row: {
                        "grouping_name": r.table("usage_grouping")
                        .get(row["grouping_id"])
                        .default({"name": row["grouping_id"]})["name"]
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_by_id(cls, credit_id: str) -> dict:
        """Return one credit by id; raises ``not_found`` when missing."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = r.table("usage_credit").get(credit_id).run(cls._rdb_connection)
        if not result:
            raise Error("not_found", "Category credit ID not found in database")
        return result

    @classmethod
    def find_in_period(
        cls,
        item_id: str,
        item_type: str,
        grouping_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        """Return the ordered credit-interval breakdown across ``[start, end]``.

        Reads every credit on the ``(item_id, item_type, grouping_id)``
        triple, then reconciles them into ``before``/``inner``/``after``
        slices clamped to the request window. Always returns at least
        one entry — falls back to a ``"limits": None`` placeholder row
        when no credit applies.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            credit = list(
                r.table("usage_credit")
                .get_all(
                    [item_id, item_type, grouping_id],
                    index="item_id-item_type-grouping",
                )
                .run(cls._rdb_connection)
            )
        if not credit:
            return [
                {
                    "limits": None,
                    "start_date": start_date.strftime("%Y-%m-%d %H:%M%z"),
                    "end_date": end_date.strftime("%Y-%m-%d %H:%M%z"),
                }
            ]

        outer = [
            c
            for c in credit
            if c["start_date"] <= start_date
            and (not c["end_date"] or c["end_date"] >= end_date)
        ]
        if outer:
            if len(outer) > 1:
                raise Error(
                    "internal_server",
                    "More than one outer credit interval found",
                )
            outer[0]["start_date"] = start_date.strftime("%Y-%m-%d %H:%M%z")
            outer[0]["end_date"] = end_date.strftime("%Y-%m-%d %H:%M%z")
            return outer

        before = [
            c
            for c in credit
            if c["start_date"] <= start_date
            and (
                c["end_date"]
                and (c["end_date"] >= start_date and c["end_date"] <= end_date)
            )
        ]
        if len(before) > 1:
            raise Error(
                "internal_server",
                "More than one before credit interval found",
            )
        inner = [
            c
            for c in credit
            if c["start_date"] >= start_date
            and (c["end_date"] and c["end_date"] <= end_date)
        ]
        after = [
            c
            for c in credit
            if c["start_date"] <= end_date
            and (not c["end_date"] or c["end_date"] >= end_date)
        ]
        if len(after) > 1:
            raise Error(
                "internal_server",
                "More than one after credit interval found",
            )

        if not (before or inner or after):
            return [
                {
                    "limits": None,
                    "start_date": start_date.strftime("%Y-%m-%d %H:%M%z"),
                    "end_date": end_date.strftime("%Y-%m-%d %H:%M%z"),
                }
            ]
        if before:
            before[0]["start_date"] = start_date
        else:
            before = [
                {
                    "limits": None,
                    "start_date": start_date,
                    "end_date": (
                        inner[0]["start_date"]
                        if inner
                        else after[0]["start_date"] if after else end_date
                    ),
                }
            ]
        if after:
            after[0]["end_date"] = end_date
        else:
            after = [
                {
                    "limits": None,
                    "start_date": (
                        inner[-1]["end_date"]
                        if inner
                        else (before[0]["end_date"] if before else start_date)
                    ),
                    "end_date": end_date,
                }
            ]
        all_intervals = before + inner + after
        for interval in all_intervals:
            interval["start_date"] = (
                interval["start_date"].strftime("%Y-%m-%d %H:%M%z")
                if not isinstance(interval["start_date"], str)
                else interval["start_date"]
            )
            interval["end_date"] = (
                interval["end_date"].strftime("%Y-%m-%d %H:%M%z")
                if not isinstance(interval["end_date"], str)
                else interval["end_date"]
            )
        return all_intervals

    @classmethod
    def create(
        cls,
        data: dict,
        start_date: datetime,
        end_date: datetime | None,
    ) -> bool:
        """Insert one credit per item id; cuts overlapping rows first.

        ``data`` must carry ``item_ids``, ``item_consumer``, ``item_type``,
        ``grouping_id``, ``limit_id``. Validates that the referenced
        ``usage_limit`` exists, then inserts a credit per item id with
        the resolved limit fields denormalized into the credit row.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            limit = (
                r.table("usage_limit").get(data["limit_id"]).run(cls._rdb_connection)
            )
        if not limit:
            raise Error("not_found", "Usage limit not found")

        result = None
        for item_id in data["item_ids"]:
            cls._cut_existing(
                item_id,
                data["item_type"],
                data["grouping_id"],
                start_date,
                end_date,
            )
            with cls._rdb_context():
                limits = (
                    r.table("usage_limit")
                    .get(data["limit_id"])
                    .pluck("id", "name", "desc", "limits")
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                r.table("usage_credit").insert(
                    {
                        "item_id": item_id,
                        "item_consumer": data["item_consumer"],
                        "item_type": data["item_type"],
                        "grouping_id": data["grouping_id"],
                        "start_date": start_date,
                        "end_date": end_date,
                        "limits": limits.get("limits"),
                        "limits_id": limits.get("id"),
                        "limits_desc": limits.get("desc"),
                        "limits_name": limits.get("name"),
                    }
                ).run(cls._rdb_connection)
            result = True
        return result

    @classmethod
    def update(cls, credit_id: str, data: dict) -> bool:
        """Update an existing credit; reconciles overlapping rows.

        Validates the credit exists, parses the new dates, cuts any
        overlapping credits on the new ``(item_id, item_type, grouping_id,
        start_date, end_date)`` window, then writes ``data`` to the row.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            existing = r.table("usage_credit").get(credit_id).run(cls._rdb_connection)
        if not existing:
            raise Error("not_found", "Usage credit not found")

        if data.get("end_date"):
            data["end_date"] = data["end_date"] if data["end_date"] != "null" else None

        if (
            data.get("item_id")
            or data.get("item_type")
            or data.get("grouping_id")
            or data.get("start_date")
            or data.get("end_date")
        ):
            credit = existing
            grouping_id = data.get("grouping_id", credit["grouping_id"])
            item_type = data.get("item_type", credit["item_type"])
            item_id = data.get("item_id", credit["item_id"])

            start_date_str = data.get("start_date")
            end_date_str = data.get("end_date")

            if start_date_str or end_date_str:
                try:
                    if start_date_str:
                        data["start_date"] = datetime.strptime(
                            start_date_str, "%Y-%m-%d"
                        ).astimezone(pytz.UTC)
                    if end_date_str:
                        data["end_date"] = datetime.strptime(
                            end_date_str, "%Y-%m-%d"
                        ).astimezone(pytz.UTC)
                except Exception:
                    raise Error(
                        "bad_request",
                        "Incorrect date format. Expected format: %Y-%m-%d",
                    )

            cls._cut_existing(
                item_id,
                item_type,
                grouping_id,
                data.get("start_date", credit["start_date"]),
                data.get("end_date", credit.get("end_date")),
                credit_id,
            )

        if data.get("limits"):
            validate_usage_limits(data["limits"])

        with cls._rdb_context():
            r.table("usage_credit").get(credit_id).update(data).run(cls._rdb_connection)
        return True

    @classmethod
    def delete(cls, credit_id: str) -> bool:
        """Delete a credit; raises ``not_found`` when nothing was deleted."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = (
                r.table("usage_credit").get(credit_id).delete().run(cls._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Credit with ID " + credit_id + " not found in database",
            )
        return True

    @classmethod
    def _cut_existing(
        cls,
        item_id: str,
        item_type: str,
        grouping_id: str,
        start_date: datetime,
        end_date: datetime | None,
        credit_id: str | None = None,
    ) -> None:
        """Trim or delete the credit overlapping the given window, if any."""
        if not end_date:
            end_date = datetime.now(pytz.utc)

        overlap = cls.check_overlapping(
            item_id, item_type, grouping_id, start_date, end_date, credit_id
        )
        if not overlap:
            return

        if overlap["action"] == "cut":
            with cls._rdb_context():
                if overlap.get("start_date"):
                    r.table("usage_credit").get(overlap["credit_id"]).update(
                        {"start_date": overlap.get("start_date")}
                    ).run(cls._rdb_connection)
                elif overlap.get("end_date"):
                    r.table("usage_credit").get(overlap["credit_id"]).update(
                        {"end_date": overlap.get("end_date")}
                    ).run(cls._rdb_connection)
                else:
                    r.table("usage_credit").get(overlap["credit_id"]).delete().run(
                        cls._rdb_connection
                    )
        elif overlap["action"] == "deleted":
            with cls._rdb_context():
                r.table("usage_credit").get(overlap["credit_id"]).delete().run(
                    cls._rdb_connection
                )

    @classmethod
    def check_overlapping(
        cls,
        item_id: str,
        item_type: str,
        grouping_id: str,
        start_date: datetime,
        end_date: datetime | None,
        credit_id: str | None = None,
    ) -> dict | None:
        """Return the overlap descriptor for any conflicting credit, or ``None``.

        Categories of overlap:

        * **outer**  — existing credit fully contains the new window;
          shrinks the existing one to ``end_date - 1 day``.
        * **before** — existing credit's tail crosses the new window's
          start; shrinks it to ``start_date - 1 day``.
        * **inner**  — existing credit is fully inside the new window;
          deleted.
        * **after**  — existing credit's head crosses the new window's
          end; shrinks it to ``end_date + 1 day``.
        """
        from isardvdi_common.helpers.error_factory import Error

        if not end_date:
            end_date = datetime.now(pytz.utc)

        with cls._rdb_context():
            credit = list(
                r.table("usage_credit")
                .get_all(
                    [item_id, item_type, grouping_id],
                    index="item_id-item_type-grouping",
                )
                .run(cls._rdb_connection)
            )

        if not credit:
            return None

        outer = [
            c
            for c in credit
            if c["start_date"] <= start_date
            and (not c["end_date"] or c["end_date"] >= end_date)
            and credit_id != c["id"]
        ]
        if outer:
            if len(outer) > 1:
                raise Error(
                    "internal_server",
                    "More than one outer credit interval found",
                )
            return {
                "credit_id": outer[0]["id"],
                "action": "cut",
                "end_date": (end_date + timedelta(days=-1)),
            }

        before = [
            c
            for c in credit
            if c["start_date"] <= start_date
            and (
                c["end_date"]
                and (c["end_date"] >= start_date and c["end_date"] <= end_date)
            )
            and credit_id != c["id"]
        ]
        if before:
            if len(before) > 1:
                raise Error(
                    "internal_server",
                    "More than one before credit interval found",
                )
            return {
                "credit_id": before[0]["id"],
                "action": "cut",
                "end_date": (start_date + timedelta(days=-1)),
            }

        inner = [
            c
            for c in credit
            if c["start_date"] >= start_date
            and (c["end_date"] and c["end_date"] <= end_date)
            and credit_id != c["id"]
        ]
        if inner:
            if len(inner) > 1:
                raise Error(
                    "internal_server",
                    "More than one inner credit interval found",
                )
            return {"credit_id": inner[0]["id"], "action": "deleted"}

        after = [
            c
            for c in credit
            if c["start_date"] <= end_date
            and (not c["end_date"] or c["end_date"] >= end_date)
            and credit_id != c["id"]
        ]
        if after:
            if len(after) > 1:
                raise Error(
                    "internal_server",
                    "More than one after credit interval found",
                )
            return {
                "credit_id": after[0]["id"],
                "action": "cut",
                "start_date": (end_date + timedelta(days=1)),
            }

        return None
