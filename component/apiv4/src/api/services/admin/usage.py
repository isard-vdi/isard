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

from datetime import datetime, timedelta

import pytz
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.lib.usage.common import UsageProcessed
from isardvdi_common.lib.usage.consumption import (
    ConsumptionUsageProcessed,
    subtract_dicts,
)
from isardvdi_common.lib.usage.credits import CreditsUsageProcessed
from isardvdi_common.lib.usage.groupings import GroupingsUsageProcessed
from isardvdi_common.lib.usage.limits import LimitsUsageProcessed, validate_usage_limits
from isardvdi_common.lib.usage.parameters import ParametersUsageProcessed
from isardvdi_common.lib.usage.reset_dates import ResetDatesUsageProcessed


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
        items = ConsumptionUsageProcessed.list_distinct_items(items_ids)

        data = []
        reset_dates = AdminUsageService.get_reset_dates(start_date, end_date)
        for day_offset in range(0, (end_date - start_date).days + 1):
            current_day = start_date + timedelta(days=day_offset)
            for item in items:
                item_data = ConsumptionUsageProcessed.get_item_date_consumption(
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
                                ConsumptionUsageProcessed.get_item_date_consumption(
                                    date,
                                    item["item_id"],
                                    item_type,
                                    item["item_name"],
                                    grouping_params=grouping,
                                )["abs"]
                            )
                            abs_val = subtract_dicts(item_data["abs"], abs_reset_data)
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
        if items_ids is None:
            # ``list_distinct_items_by_consumer`` resolves through to a
            # ``get_all(item_consumer, index="item_consumer")`` rdb
            # query — RethinkDB raises ``ReqlNonExistenceError: Keys
            # cannot be NULL`` if ``item_consumer`` is None, the
            # route's generic ``except Exception`` swallows it, and
            # the caller gets a generic 500 with no hint about what
            # to fix. Validate at the service boundary instead.
            # Tracked as Bug 31.
            if not item_consumer:
                raise Error(
                    "bad_request",
                    "Either items_ids or item_consumer must be provided",
                    description_code="usage_consumer_required",
                )
            items = ConsumptionUsageProcessed.list_distinct_items_by_consumer(
                item_consumer, category_id
            )
        else:
            items = ConsumptionUsageProcessed.list_distinct_items(items_ids)

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
            start_data = ConsumptionUsageProcessed.get_item_date_consumption(
                start_date,
                item["item_id"],
                item_type,
                item["item_name"],
                grouping_params=grouping_params,
            )
            if reset_start_date:
                reset_start_data = ConsumptionUsageProcessed.get_item_date_consumption(
                    reset_start_date,
                    item["item_id"],
                    item_type,
                    item["item_name"],
                    grouping_params=grouping_params,
                )
                start_data["abs"] = subtract_dicts(
                    start_data["abs"], reset_start_data["abs"]
                )
            end_data = ConsumptionUsageProcessed.get_item_date_consumption(
                end_date,
                item["item_id"],
                item_type,
                item["item_name"],
                grouping_params=grouping_params,
            )
            if reset_end_date:
                reset_end_data = ConsumptionUsageProcessed.get_item_date_consumption(
                    reset_end_date,
                    item["item_id"],
                    item_type,
                    item["item_name"],
                    grouping_params=grouping_params,
                )
                end_data["abs"] = subtract_dicts(end_data["abs"], reset_end_data["abs"])
            item_description = ""
            if item_consumer == "category":
                item_description = ConsumptionUsageProcessed.get_category_description(
                    item["item_id"]
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
    def get_usage_consumers(item_type):
        return UsageProcessed.list_consumers(item_type)

    @staticmethod
    def count_usage_consumers():
        return UsageProcessed.count_consumption_rows()

    @staticmethod
    def get_usage_distinct_items(
        item_consumer, start_date, end_date, item_category=None
    ):
        # start/end dates are accepted for the route signature but the
        # underlying query is a distinct on the ``item_consumer`` index;
        # validation still runs to reject malformed strings.
        _parse_iso_date(start_date, "start_date")
        _parse_iso_date(end_date, "end_date")
        return ConsumptionUsageProcessed.list_distinct_consumer_items(
            item_consumer, item_category
        )

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
            beginning_time = UsageProcessed.get_logs_started_time(item_type)
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
        return ParametersUsageProcessed.list_parameters(ids)

    @staticmethod
    def add_usage_parameters(data):
        return ParametersUsageProcessed.create_parameter(data)

    @staticmethod
    def update_usage_parameters(data):
        return ParametersUsageProcessed.update_parameter(data)

    @staticmethod
    def delete_usage_parameters(parameter_id):
        return ParametersUsageProcessed.delete_parameter(parameter_id)

    # =========================================================================
    # LIMITS
    # =========================================================================

    @staticmethod
    def get_usage_limits():
        return LimitsUsageProcessed.list_limits()

    @staticmethod
    def add_usage_limits(name, desc, limits):
        return LimitsUsageProcessed.create_limit(name, desc, limits)

    @staticmethod
    def update_usage_limits(limit_id, name, desc, limits):
        return LimitsUsageProcessed.update_limit(limit_id, name, desc, limits)

    @staticmethod
    def delete_usage_limits(limit_id):
        return LimitsUsageProcessed.delete_limit(limit_id)

    # =========================================================================
    # GROUPINGS
    # =========================================================================

    @staticmethod
    def get_usage_groupings():
        return GroupingsUsageProcessed.list_groupings()

    @staticmethod
    def get_usage_groupings_dropdown():
        return GroupingsUsageProcessed.get_groupings_dropdown()

    @staticmethod
    def get_usage_grouping(grouping_id):
        return GroupingsUsageProcessed.get_grouping(grouping_id)

    @staticmethod
    def add_usage_grouping(data):
        return GroupingsUsageProcessed.create_grouping(data)

    @staticmethod
    def update_usage_grouping(data):
        return GroupingsUsageProcessed.update_grouping(data)

    @staticmethod
    def delete_usage_grouping(grouping_id):
        return GroupingsUsageProcessed.delete_grouping(grouping_id)

    # =========================================================================
    # CREDITS
    # =========================================================================

    @staticmethod
    def get_all_usage_credits():
        return CreditsUsageProcessed.list_all()

    @staticmethod
    def get_usage_credits_by_id(credits_id):
        return CreditsUsageProcessed.get_by_id(credits_id)

    @staticmethod
    def get_usage_credits(item_id, item_type, grouping_id, start_date, end_date):
        start_date = _parse_iso_date(start_date, "start_date")
        end_date = _parse_iso_date(end_date, "end_date")
        return CreditsUsageProcessed.find_in_period(
            item_id, item_type, grouping_id, start_date, end_date
        )

    @staticmethod
    def add_usage_credit(data):
        end_date = data.get("end_date")
        if end_date == "null" or end_date is None:
            end_date = None
        else:
            end_date = _parse_iso_date(end_date, "end_date")
        start_date = _parse_iso_date(data["start_date"], "start_date")
        return CreditsUsageProcessed.create(data, start_date, end_date)

    @staticmethod
    def update_usage_credit(credit_id, data):
        return CreditsUsageProcessed.update(credit_id, data)

    @staticmethod
    def delete_usage_credit(credit_id):
        return CreditsUsageProcessed.delete(credit_id)

    @staticmethod
    def check_overlapping_credits(
        item_id,
        item_type,
        grouping_id,
        start_date,
        end_date,
        credit_id=None,
    ):
        return CreditsUsageProcessed.check_overlapping(
            item_id, item_type, grouping_id, start_date, end_date, credit_id
        )

    # =========================================================================
    # RESET DATES
    # =========================================================================

    @staticmethod
    def get_reset_dates(start_date=None, end_date=None):
        return ResetDatesUsageProcessed.list_reset_dates(start_date, end_date)

    @staticmethod
    def add_reset_dates(date_list):
        ResetDatesUsageProcessed.replace_reset_dates(date_list)

    # =========================================================================
    # MISC
    # =========================================================================

    @staticmethod
    def unify_item_name(item_id):
        return UsageProcessed.unify_item_name(item_id)

    @staticmethod
    def delete_all_consumption_data():
        UsageProcessed.delete_all_consumption()

    @staticmethod
    def check_item_ownership(payload, filters):
        UsageProcessed.check_item_ownership(payload, filters)
