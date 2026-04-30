#
#   Copyright © 2025 IsardVDI
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
import traceback
from datetime import datetime, timedelta

import pytz
from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


def _parse_iso_date(value, field_name="date"):
    """Parse a YYYY-MM-DD string, raising a typed 400 when invalid.

    The routes accept date fragments as path/query parameters, so a
    client sending anything else (or the audit sending a stub "x")
    used to hit `datetime.strptime`'s ValueError and bubble out as a
    500. Route-level typed error is the correct contract.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=pytz.utc)
    except (ValueError, TypeError):
        raise Error(
            "bad_request",
            f"Invalid {field_name} '{value}': expected YYYY-MM-DD",
            description_code="invalid_date",
        )


class AdminUsageService:
    """Service for usage consumption, parameters, limits, groupings, and credits."""

    # =========================================================================
    # CONSUMPTION
    # =========================================================================

    @staticmethod
    def get_usage_consumption_between_dates(
        start_date, end_date, items_ids, item_type, grouping=None
    ):
        if not start_date or not end_date:
            raise Error(
                "bad_request",
                "start_date and end_date are required (YYYY-MM-DD)",
                description_code="usage_dates_required",
            )
        start_date = _parse_iso_date(start_date, "start_date")
        end_date = _parse_iso_date(end_date, "end_date")
        with RethinkSharedConnection._rdb_context():
            if items_ids is None:
                items = list(
                    r.table("usage_consumption")
                    .pluck("item_id", "item_name")
                    .distinct()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            else:
                items = list(
                    r.table("usage_consumption")
                    .get_all(r.args(items_ids), index="item_id")
                    .pluck("item_id", "item_name")
                    .distinct()
                    .run(RethinkSharedConnection._rdb_connection)
                )

        data = []
        reset_dates = AdminUsageService.get_reset_dates(start_date, end_date)
        for day_offset in range(0, (end_date - start_date).days + 1):
            current_day = start_date + timedelta(days=day_offset)
            for item in items:
                item_data = AdminUsageService._get_item_date_consumption(
                    current_day,
                    item["item_id"],
                    item_type,
                    item["item_name"],
                    grouping_params=grouping,
                )
                abs_val = item_data["abs"]
                if item_type in ["desktop", "user"] and len(reset_dates):
                    for date in reset_dates:
                        if current_day >= date:
                            abs_reset_data = (
                                AdminUsageService._get_item_date_consumption(
                                    date,
                                    item["item_id"],
                                    item_type,
                                    item["item_name"],
                                    grouping_params=grouping,
                                )["abs"]
                            )
                            abs_val = AdminUsageService._substract_dicts(
                                item_data["abs"], abs_reset_data
                            )
                            break
                data.append(
                    {
                        "name": item["item_name"],
                        "date": current_day,
                        "inc": item_data["inc"],
                        "abs": abs_val,
                        "item_id": item["item_id"],
                    }
                )
        return data

    @staticmethod
    def get_start_end_consumption(
        start_date,
        end_date,
        items_ids=None,
        item_type=None,
        item_consumer=None,
        grouping_params=None,
        category_id=None,
    ):
        if not start_date or not end_date:
            raise Error(
                "bad_request",
                "start_date and end_date are required (YYYY-MM-DD)",
                description_code="usage_dates_required",
            )
        start_date = _parse_iso_date(start_date, "start_date")
        end_date = _parse_iso_date(end_date, "end_date")
        with RethinkSharedConnection._rdb_context():
            if items_ids is None:
                query = r.table("usage_consumption").get_all(
                    item_consumer, index="item_consumer"
                )
                if category_id:
                    query = query.pluck(
                        "item_id", "item_name", "item_consumer_category_id"
                    ).filter({"item_consumer_category_id": category_id})
                else:
                    query = query.pluck("item_id", "item_name")
                items = list(
                    query.distinct().run(RethinkSharedConnection._rdb_connection)
                )
            else:
                items = list(
                    r.table("usage_consumption")
                    .get_all(r.args(items_ids), index="item_id")
                    .pluck("item_id", "item_name")
                    .distinct()
                    .run(RethinkSharedConnection._rdb_connection)
                )

        data = []
        reset_dates = AdminUsageService.get_reset_dates(start_date, end_date)
        reset_start_date = None
        reset_end_date = None
        if item_type in ["desktop", "user"] and len(reset_dates):
            for reset_date in reset_dates:
                if reset_date <= start_date:
                    reset_start_date = reset_date
                    break
            if reset_dates[0] < end_date:
                reset_end_date = reset_dates[0]

        items_ids_list = [d["item_id"] for d in items]
        duplicated_items_ids = list(
            set([d["item_id"] for d in items if items_ids_list.count(d["item_id"]) > 1])
        )
        for item in items:
            start_data = AdminUsageService._get_item_date_consumption(
                start_date,
                item["item_id"],
                item_type,
                item["item_name"],
                grouping_params=grouping_params,
            )
            if reset_start_date:
                reset_start_data = AdminUsageService._get_item_date_consumption(
                    reset_start_date,
                    item["item_id"],
                    item_type,
                    item["item_name"],
                    grouping_params=grouping_params,
                )
                start_data["abs"] = AdminUsageService._substract_dicts(
                    start_data["abs"], reset_start_data["abs"]
                )
            end_data = AdminUsageService._get_item_date_consumption(
                end_date,
                item["item_id"],
                item_type,
                item["item_name"],
                grouping_params=grouping_params,
            )
            if reset_end_date:
                reset_end_data = AdminUsageService._get_item_date_consumption(
                    reset_end_date,
                    item["item_id"],
                    item_type,
                    item["item_name"],
                    grouping_params=grouping_params,
                )
                end_data["abs"] = AdminUsageService._substract_dicts(
                    end_data["abs"], reset_end_data["abs"]
                )
            item_description = ""
            if item_consumer == "category":
                with RethinkSharedConnection._rdb_context():
                    item_description = (
                        r.table("categories")
                        .get(item["item_id"])
                        .default({"description": ""})["description"]
                        .run(RethinkSharedConnection._rdb_connection)
                    )
            data.append(
                {
                    "item_id": item["item_id"],
                    "item_name": item["item_name"],
                    "item_description": item_description,
                    "item_consumer": item_consumer,
                    "start": start_data,
                    "end": end_data,
                    "duplicated_item_id": item["item_id"] in duplicated_items_ids,
                }
            )
        return data

    @staticmethod
    def _get_item_date_consumption(
        date, item_id, item_type, item_name, grouping_params=None
    ):
        if isinstance(date, str):
            date = _parse_iso_date(date, "date")
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
            AdminUsageService._get_default_consumption(grouping_params)
            if grouping_params
            else AdminUsageService._get_default_consumption()
        )
        with RethinkSharedConnection._rdb_context():
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
                .run(RethinkSharedConnection._rdb_connection)
            )
        with RethinkSharedConnection._rdb_context():
            data["inc"] = (
                r.table("usage_consumption")
                .get_all(item_id, index="item_id")
                .pluck(pluck)
                .filter((r.row["date"] == date) & (r.row["item_type"] == item_type))
                .nth(0)
                .default({"inc": default_consumption})["inc"]
                .run(RethinkSharedConnection._rdb_connection)
            )
        return data

    @staticmethod
    def _get_default_consumption(grouping_params=None):
        """Return a default consumption dict with zeros for all params."""
        if grouping_params:
            return {p: 0 for p in grouping_params}
        # Get all parameters from usage_parameter table
        with RethinkSharedConnection._rdb_context():
            params = list(
                r.table("usage_parameter")
                .pluck("id")
                .run(RethinkSharedConnection._rdb_connection)
            )
        return {p["id"]: 0 for p in params}

    @staticmethod
    def _substract_dicts(dict1, dict2):
        """Subtract values in dict2 from dict1."""
        result = {}
        for key in dict1:
            if isinstance(dict1[key], dict):
                result[key] = AdminUsageService._substract_dicts(
                    dict1[key], dict2.get(key, {})
                )
            elif isinstance(dict1[key], (int, float)):
                result[key] = dict1[key] - dict2.get(key, 0)
            else:
                result[key] = dict1[key]
        return result

    @staticmethod
    def get_usage_consumers(item_type):
        with RethinkSharedConnection._rdb_context():
            return list(
                r.table("usage_consumption")
                .get_all(item_type, index="item_type")
                .pluck("item_consumer")
                .distinct()["item_consumer"]
                .run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def count_usage_consumers():
        with RethinkSharedConnection._rdb_context():
            return (
                r.table("usage_consumption")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def get_usage_distinct_items(
        item_consumer, start_date, end_date, item_category=None
    ):
        start_date = _parse_iso_date(start_date, "start_date")
        end_date = _parse_iso_date(end_date, "end_date")
        with RethinkSharedConnection._rdb_context():
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
            return list(query.distinct().run(RethinkSharedConnection._rdb_connection))

    @staticmethod
    def consolidate_consumptions(item_type=None, total_days=2):
        """Trigger consumption consolidation.

        Called by the scheduler via PUT /admin/usage/consolidate.
        """
        from api.services.usage.desktop import ConsolidateDesktopConsumption
        from api.services.usage.media import ConsolidateMediaConsumption
        from api.services.usage.storage import ConsolidateStorageConsumption
        from api.services.usage.user import ConsolidateUserConsumption

        if total_days == "all":
            with RethinkSharedConnection._rdb_context():
                beginning_time = (
                    r.table("logs_" + item_type)
                    .order_by(index="started_time")
                    .nth(0)["started_time"]
                    .run(RethinkSharedConnection._rdb_connection)
                )
            total_days = int(
                (datetime.now(pytz.utc) - beginning_time).total_seconds() / 60 / 60 / 24
            )
        else:
            total_days = int(total_days)

        if not item_type:
            ConsolidateStorageConsumption()
            ConsolidateMediaConsumption()
            for i in list(reversed(range(1, total_days))):
                ConsolidateDesktopConsumption(days_before=i)
                ConsolidateUserConsumption(days_before=i)
        elif item_type == "desktops":
            for i in list(reversed(range(1, total_days))):
                ConsolidateDesktopConsumption(days_before=i)
        elif item_type == "users":
            for i in list(reversed(range(1, total_days))):
                ConsolidateUserConsumption(days_before=i)
        elif item_type == "storage":
            ConsolidateStorageConsumption()
        elif item_type == "media":
            ConsolidateMediaConsumption()
        else:
            raise Error(
                "bad_request",
                "Item type "
                + str(item_type)
                + " not valid for consumption calculation",
            )

    # =========================================================================
    # PARAMETERS
    # =========================================================================

    @staticmethod
    def get_usage_parameters(ids=None):
        with RethinkSharedConnection._rdb_context():
            if ids:
                return list(
                    r.table("usage_parameter")
                    .get_all(r.args(ids))
                    .run(RethinkSharedConnection._rdb_connection)
                )
            else:
                return list(
                    r.table("usage_parameter").run(
                        RethinkSharedConnection._rdb_connection
                    )
                )

    @staticmethod
    def add_usage_parameters(data):
        with RethinkSharedConnection._rdb_context():
            r.table("usage_parameter").insert(
                {
                    "custom": data["custom"],
                    "default": 0,
                    "desc": data["desc"],
                    "formula": data["formula"],
                    "id": data["id"],
                    "item_type": data["item_type"],
                    "name": data["name"],
                    "units": data["units"],
                }
            ).run(RethinkSharedConnection._rdb_connection)
        return True

    @staticmethod
    def update_usage_parameters(data):
        if data["custom"]:
            with RethinkSharedConnection._rdb_context():
                r.table("usage_parameter").get(data["id"]).update(data).run(
                    RethinkSharedConnection._rdb_connection
                )
        else:
            raise Error("forbidden", "Only custom parameters can be edited")
        return True

    @staticmethod
    def delete_usage_parameters(parameter_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("usage_parameter")
                .get(parameter_id)
                .delete()
                .run(RethinkSharedConnection._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Parameter with ID " + parameter_id + " not found in database",
            )
        return True

    # =========================================================================
    # LIMITS
    # =========================================================================

    @staticmethod
    def get_usage_limits():
        with RethinkSharedConnection._rdb_context():
            return list(
                r.table("usage_limit").run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def add_usage_limits(name, desc, limits):
        AdminUsageService._check_usage_limits(limits)
        with RethinkSharedConnection._rdb_context():
            r.table("usage_limit").insert(
                {"name": name, "desc": desc, "limits": limits}
            ).run(RethinkSharedConnection._rdb_connection)
        return True

    @staticmethod
    def update_usage_limits(limit_id, name, desc, limits):
        AdminUsageService._check_usage_limits(limits)
        with RethinkSharedConnection._rdb_context():
            r.table("usage_limit").get(limit_id).update(
                {"name": name, "desc": desc, "limits": limits}
            ).run(RethinkSharedConnection._rdb_connection)
        return True

    @staticmethod
    def delete_usage_limits(limit_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("usage_limit")
                .get(limit_id)
                .delete()
                .run(RethinkSharedConnection._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Limit with ID " + limit_id + " not found in database",
            )
        return True

    @staticmethod
    def _check_usage_limits(limits):
        if not all(
            [
                limits["hard"] >= limits["exp_min"],
                limits["hard"] >= limits["exp_max"],
                limits["hard"] >= limits["soft"],
            ]
        ):
            raise Error(
                "bad_request",
                "The hard limit must be higher than or equal to all other limit values.",
            )
        if not (limits["exp_max"] > limits["exp_min"]):
            raise Error(
                "bad_request",
                "Expected maximum must be greater than the expected minimum",
            )
        if not (limits["soft"] > limits["exp_min"]):
            raise Error(
                "bad_request",
                "Expected minimum can not be greater than the soft limit",
            )

    # =========================================================================
    # GROUPINGS
    # =========================================================================

    @staticmethod
    def get_usage_groupings():
        groupings = AdminUsageService._get_system_usage_groupings()
        with RethinkSharedConnection._rdb_context():
            groupings = groupings + list(
                r.table("usage_grouping").run(RethinkSharedConnection._rdb_connection)
            )
        return groupings

    @staticmethod
    def _get_system_usage_groupings():
        params = AdminUsageService._get_params()
        groupings = []
        for item_type in params.keys():
            system_parameters = [
                sp["id"] for sp in params[item_type] if not sp["custom"]
            ]
            custom_parameters = [cp["id"] for cp in params[item_type] if cp["custom"]]
            groupings = groupings + [
                {
                    "id": "_all",
                    "item_type": item_type,
                    "item_sub_type": "all",
                    "name": f"All {item_type} parameters",
                    "desc": f"All {item_type} system and custom parameters",
                    "parameters": system_parameters + custom_parameters,
                },
                {
                    "id": "_system",
                    "name": f"All {item_type} system parameters",
                    "item_type": item_type,
                    "item_sub_type": "system",
                    "desc": f"All {item_type} system parameters",
                    "parameters": system_parameters,
                },
                {
                    "id": "_custom",
                    "name": f"All {item_type} custom parameters",
                    "item_type": item_type,
                    "item_sub_type": "custom",
                    "desc": f"All {item_type} custom parameters",
                    "parameters": custom_parameters,
                },
            ]
        return groupings

    @staticmethod
    def _get_params():
        with RethinkSharedConnection._rdb_context():
            params_list = list(
                r.table("usage_parameter").run(RethinkSharedConnection._rdb_connection)
            )
        params = {}
        for p in params_list:
            if p["item_type"] not in params:
                params[p["item_type"]] = []
            params[p["item_type"]].append(p)
        return params

    @staticmethod
    def get_usage_groupings_dropdown():
        params = AdminUsageService._get_params()
        groupings = {"system": {}, "custom": {}}
        for item_type in params:
            system_parameters = [
                sp["id"] for sp in params[item_type] if not sp["custom"]
            ]
            custom_parameters = [cp["id"] for cp in params[item_type] if cp["custom"]]
            groupings["system"][item_type] = [
                {
                    "id": "_all",
                    "name": f"All {item_type} parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} system and custom parameters",
                    "parameters": system_parameters + custom_parameters,
                },
                {
                    "id": "_system",
                    "name": f"All {item_type} system parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} system parameters",
                    "parameters": system_parameters,
                },
                {
                    "id": "_custom",
                    "name": f"All {item_type} custom parameters",
                    "item_type": item_type,
                    "desc": f"All {item_type} custom parameters",
                    "parameters": custom_parameters,
                },
            ]
            with RethinkSharedConnection._rdb_context():
                groupings["custom"][item_type] = list(
                    r.table("usage_grouping")
                    .filter({"item_type": item_type})
                    .run(RethinkSharedConnection._rdb_connection)
                )
        return groupings

    @staticmethod
    def get_usage_grouping(grouping_id):
        with RethinkSharedConnection._rdb_context():
            grouping = (
                r.table("usage_grouping")
                .get(grouping_id)
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not grouping:
            groupings = AdminUsageService._get_system_usage_groupings()
            matches = [g for g in groupings if g.get("id") == grouping_id]
            if matches:
                grouping = matches[0]
            else:
                raise Error("not_found", "Grouping not found")
        return grouping

    @staticmethod
    def add_usage_grouping(data):
        with RethinkSharedConnection._rdb_context():
            r.table("usage_grouping").insert(data).run(
                RethinkSharedConnection._rdb_connection
            )
        return True

    @staticmethod
    def update_usage_grouping(data):
        with RethinkSharedConnection._rdb_context():
            r.table("usage_grouping").get(data["id"]).update(data).run(
                RethinkSharedConnection._rdb_connection
            )
        return True

    @staticmethod
    def delete_usage_grouping(grouping_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("usage_grouping")
                .get(grouping_id)
                .delete()
                .run(RethinkSharedConnection._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Parameter grouping with ID " + grouping_id + " not found in database",
            )
        return True

    # =========================================================================
    # CREDITS
    # =========================================================================

    @staticmethod
    def get_all_usage_credits():
        with RethinkSharedConnection._rdb_context():
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
                .run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def get_usage_credits_by_id(credits_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("usage_credit")
                .get(credits_id)
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not result:
            raise Error("not_found", "Category credit ID not found in database")
        return result

    @staticmethod
    def get_usage_credits(item_id, item_type, grouping_id, start_date, end_date):
        start_date = _parse_iso_date(start_date, "start_date")
        end_date = _parse_iso_date(end_date, "end_date")
        with RethinkSharedConnection._rdb_context():
            credit = list(
                r.table("usage_credit")
                .get_all(
                    [item_id, item_type, grouping_id],
                    index="item_id-item_type-grouping",
                )
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not len(credit):
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
        if len(outer):
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

        if not len(before + inner + after):
            return [
                {
                    "limits": None,
                    "start_date": start_date.strftime("%Y-%m-%d %H:%M%z"),
                    "end_date": end_date.strftime("%Y-%m-%d %H:%M%z"),
                }
            ]
        if len(before):
            before[0]["start_date"] = start_date
        else:
            before = [
                {
                    "limits": None,
                    "start_date": start_date,
                    "end_date": (
                        inner[0]["start_date"]
                        if len(inner)
                        else after[0]["start_date"] if len(after) else end_date
                    ),
                }
            ]
        if len(after):
            after[0]["end_date"] = end_date
        else:
            after = [
                {
                    "limits": None,
                    "start_date": (
                        inner[-1]["end_date"]
                        if len(inner)
                        else (before[0]["end_date"] if len(before) else start_date)
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

    @staticmethod
    def add_usage_credit(data):
        end_date = data.get("end_date")
        if end_date == "null" or end_date is None:
            end_date = None
        else:
            end_date = _parse_iso_date(end_date, "end_date")

        start_date = _parse_iso_date(data["start_date"], "start_date")

        # Validate limit exists
        with RethinkSharedConnection._rdb_context():
            limit = (
                r.table("usage_limit")
                .get(data["limit_id"])
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not limit:
            raise Error("not_found", "Usage limit not found")

        result = None
        for item_id in data["item_ids"]:
            AdminUsageService._cut_existing_usage_credits(
                item_id,
                data["item_type"],
                data["grouping_id"],
                start_date,
                end_date,
            )
            with RethinkSharedConnection._rdb_context():
                limits = (
                    r.table("usage_limit")
                    .get(data["limit_id"])
                    .pluck("id", "name", "desc", "limits")
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
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
                ).run(RethinkSharedConnection._rdb_connection)
            result = True
        return result

    @staticmethod
    def update_usage_credit(credit_id, data):
        # Validate credit exists
        with RethinkSharedConnection._rdb_context():
            existing = (
                r.table("usage_credit")
                .get(credit_id)
                .run(RethinkSharedConnection._rdb_connection)
            )
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

            AdminUsageService._cut_existing_usage_credits(
                item_id,
                item_type,
                grouping_id,
                data.get("start_date", credit["start_date"]),
                data.get("end_date", credit.get("end_date")),
                credit_id,
            )

        if data.get("limits"):
            AdminUsageService._check_usage_limits(data["limits"])

        with RethinkSharedConnection._rdb_context():
            r.table("usage_credit").get(credit_id).update(data).run(
                RethinkSharedConnection._rdb_connection
            )
        return True

    @staticmethod
    def delete_usage_credit(credit_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("usage_credit")
                .get(credit_id)
                .delete()
                .run(RethinkSharedConnection._rdb_connection)
            )
        if result.get("deleted", 0) == 0:
            raise Error(
                "not_found",
                "Credit with ID " + credit_id + " not found in database",
            )
        return True

    @staticmethod
    def _cut_existing_usage_credits(
        item_id,
        item_type,
        grouping_id,
        start_date,
        end_date,
        credit_id=None,
    ):
        if not end_date:
            end_date = datetime.now(pytz.utc)

        overlap = AdminUsageService.check_overlapping_credits(
            item_id, item_type, grouping_id, start_date, end_date, credit_id
        )
        if not overlap:
            return

        if overlap["action"] == "cut":
            with RethinkSharedConnection._rdb_context():
                if overlap.get("start_date"):
                    r.table("usage_credit").get(overlap["credit_id"]).update(
                        {"start_date": overlap.get("start_date")}
                    ).run(RethinkSharedConnection._rdb_connection)
                elif overlap.get("end_date"):
                    r.table("usage_credit").get(overlap["credit_id"]).update(
                        {"end_date": overlap.get("end_date")}
                    ).run(RethinkSharedConnection._rdb_connection)
                else:
                    r.table("usage_credit").get(overlap["credit_id"]).delete().run(
                        RethinkSharedConnection._rdb_connection
                    )
        elif overlap["action"] == "deleted":
            with RethinkSharedConnection._rdb_context():
                r.table("usage_credit").get(overlap["credit_id"]).delete().run(
                    RethinkSharedConnection._rdb_connection
                )

    @staticmethod
    def check_overlapping_credits(
        item_id,
        item_type,
        grouping_id,
        start_date,
        end_date,
        credit_id=None,
    ):
        if not end_date:
            end_date = datetime.now(pytz.utc)

        with RethinkSharedConnection._rdb_context():
            credit = list(
                r.table("usage_credit")
                .get_all(
                    [item_id, item_type, grouping_id],
                    index="item_id-item_type-grouping",
                )
                .run(RethinkSharedConnection._rdb_connection)
            )

        if not len(credit):
            return None

        outer = [
            c
            for c in credit
            if c["start_date"] <= start_date
            and (not c["end_date"] or c["end_date"] >= end_date)
            and credit_id != c["id"]
        ]
        if len(outer):
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
        if len(before):
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
        if len(inner):
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
        if len(after):
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

    # =========================================================================
    # RESET DATES
    # =========================================================================

    @staticmethod
    def get_reset_dates(start_date=None, end_date=None):
        with RethinkSharedConnection._rdb_context():
            if start_date and end_date:
                within = list(
                    r.table("usage_reset_dates")
                    .filter((r.row["date"] <= end_date))
                    .order_by(r.desc("date"))["date"]
                    .run(RethinkSharedConnection._rdb_connection)
                )
            else:
                within = list(
                    r.table("usage_reset_dates")
                    .order_by(r.desc("date"))["date"]
                    .run(RethinkSharedConnection._rdb_connection)
                )
        if len(within):
            result = within
            result.reverse()
            return result
        return []

    @staticmethod
    def add_reset_dates(date_list):
        with RethinkSharedConnection._rdb_context():
            r.table("usage_reset_dates").delete().run(
                RethinkSharedConnection._rdb_connection
            )
        for date in set(date_list):
            date = date.replace(tzinfo=pytz.timezone("UTC"))
            with RethinkSharedConnection._rdb_context():
                r.table("usage_reset_dates").insert({"date": date}).run(
                    RethinkSharedConnection._rdb_connection
                )

    # =========================================================================
    # MISC
    # =========================================================================

    @staticmethod
    def unify_item_name(item_id):
        with RethinkSharedConnection._rdb_context():
            rows = list(
                r.table("usage_consumption")
                .get_all(item_id, index="item_id")
                .order_by("date")
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not rows:
            raise Error(
                "not_found",
                f"No consumption data for item {item_id}",
                description_code="consumption_not_found",
            )
        current_name = rows[-1]["item_name"]
        with RethinkSharedConnection._rdb_context():
            r.table("usage_consumption").get_all(item_id, index="item_id").filter(
                lambda uc: uc["item_name"] != current_name
            ).update({"item_name": current_name}).run(
                RethinkSharedConnection._rdb_connection
            )
        return current_name

    @staticmethod
    def delete_all_consumption_data():
        with RethinkSharedConnection._rdb_context():
            r.table("usage_consumption").delete().run(
                RethinkSharedConnection._rdb_connection
            )

    @staticmethod
    def check_item_ownership(payload, filters):
        """Validate that a manager has access to the items in the filter."""
        if not filters.get("item_ids"):
            return
        item_type = filters.get("item_type")
        if item_type == "category":
            for item_id in filters["item_ids"]:
                if (
                    payload["role_id"] == "manager"
                    and payload["category_id"] != item_id
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this category",
                    )
        elif item_type == "group":
            for item_id in filters["item_ids"]:
                with RethinkSharedConnection._rdb_context():
                    group = (
                        r.table("groups")
                        .get(item_id)
                        .pluck("parent_category")
                        .run(RethinkSharedConnection._rdb_connection)
                    )
                if (
                    group
                    and payload["role_id"] == "manager"
                    and payload["category_id"] != group.get("parent_category")
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this group",
                    )
        elif item_type == "user":
            for item_id in filters["item_ids"]:
                with RethinkSharedConnection._rdb_context():
                    user = (
                        r.table("users")
                        .get(item_id)
                        .pluck("category")
                        .run(RethinkSharedConnection._rdb_connection)
                    )
                if (
                    user
                    and payload["role_id"] == "manager"
                    and payload["category_id"] != user.get("category")
                ):
                    raise Error(
                        "forbidden",
                        "You are not allowed to access this user",
                    )
