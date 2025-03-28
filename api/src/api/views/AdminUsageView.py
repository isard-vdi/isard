#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import json
from datetime import date, datetime

import gevent
import pytz
from cachetools import TTLCache, cached
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_admin import admin_table_list
from ..libv2.api_usage import (
    add_reset_date,
    add_usage_credit,
    add_usage_grouping,
    add_usage_limits,
    add_usage_parameters,
    check_overlapping_credits,
    consolidate_consumptions,
    count_usage_consumers,
    delete_all_consumption_data,
    delete_usage_credit,
    delete_usage_grouping,
    delete_usage_limits,
    delete_usage_parameters,
    get_all_usage_credits,
    get_reset_dates,
    get_start_end_consumption,
    get_usage_consumers,
    get_usage_consumption_between_dates,
    get_usage_credits,
    get_usage_credits_by_id,
    get_usage_distinct_items,
    get_usage_grouping,
    get_usage_groupings,
    get_usage_groupings_dropdown,
    get_usage_limits,
    get_usage_parameters,
    unify_item_name,
    update_usage_credit,
    update_usage_grouping,
    update_usage_limits,
    update_usage_parameters,
)
from ..libv2.validators import _validate_item
from .decorators import (
    is_admin,
    is_admin_or_manager,
    itemExists,
    ownsCategoryId,
    ownsDomainId,
    ownsUserId,
)

# VIEWS: Usage Consumption


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_usage(payload):
    filters = request.get_json()

    if filters.get("item_ids"):
        if filters["item_type"] == "category":
            for item_id in filters["item_ids"]:
                ownsCategoryId(item_id)
        elif filters["item_type"] == "group":
            for item_id in filters["item_ids"]:
                ownsCategoryId(
                    admin_table_list("groups", pluck="parent_category", id=item_id)[
                        "parent_category"
                    ]
                )
        elif filters["item_type"] == "group":
            for item_id in filters["item_ids"]:
                ownsUserId(item_id)
        elif filters["item_type"] in ["template", "desktop"]:
            for item_id in filters["item_ids"]:
                ownsDomainId(item_id)

    data = get_usage_consumption_between_dates(
        filters.get("start_date", None),
        filters.get("end_date", None),
        filters.get("items_ids", None),
        filters.get("item_type", None),
        filters.get("grouping", None),
    )
    return (
        json.dumps(
            data,
            indent=4,
            sort_keys=True,
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/start_end", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_usage_start_end(payload):
    filters = request.get_json()
    if payload["role_id"] != "admin" and filters["item_consumer"] == "hypervisor":
        raise Error("forbidden", "Not enough rights to access hypervisor usage")
    if filters.get("item_ids"):
        if filters["item_type"] == "category":
            for item_id in filters["item_ids"]:
                ownsCategoryId(item_id)
        elif filters["item_type"] == "group":
            for item_id in filters["item_ids"]:
                ownsCategoryId(
                    admin_table_list("groups", pluck="parent_category", id=item_id)[
                        "parent_category"
                    ]
                )
        elif filters["item_type"] == "user":
            for item_id in filters["item_ids"]:
                ownsUserId(item_id)
        elif filters["item_type"] in ["template", "desktop"]:
            for item_id in filters["item_ids"]:
                ownsDomainId(item_id)

    data = get_start_end_consumption(
        filters.get("start_date", None),
        filters.get("end_date", None),
        filters.get("items_ids", None),
        filters.get("item_type", None),
        filters.get("item_consumer", None),
        filters.get("grouping", None),
        payload["category_id"] if payload["role_id"] == "manager" else None,
    )
    return (
        json.dumps(
            data,
            indent=4,
            sort_keys=True,
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/consumers/<item_type>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_usage_consumers(payload, item_type):
    consumers = get_usage_consumers(
        item_type,
    )
    if payload["role_id"] != "admin" and "hypervisor" in consumers:
        consumers.remove("hypervisor")
    return (
        json.dumps(consumers),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/consumers", methods=["GET"])
@is_admin
def api_v3_admin_usage_consumers_count(payload):
    return (
        json.dumps(count_usage_consumers()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/usage/distinct_items/<item_consumer>/<start>/<end>", methods=["GET"]
)
@is_admin_or_manager
def api_v3_admin_usage_distinct_items(payload, item_consumer, start, end):
    if payload["role_id"] != "admin" and item_consumer == "hypervisor":
        raise Error("forbidden", "Not enough rights to access hypervisor usage")
    return (
        json.dumps(
            get_usage_distinct_items(
                item_consumer,
                start,
                end,
                payload["category_id"] if payload["role_id"] == "manager" else None,
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/consolidate", methods=["PUT"])
@is_admin
def api_v3_admin_consolidate(payload):
    consolidate_consumptions()
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/consolidate/<item_type>/<days>", methods=["PUT"])
@app.route("/api/v3/admin/usage/consolidate/<item_type>", methods=["PUT"])
@is_admin
def api_v3_admin_consolidate_item(payload, item_type, days=29):
    consolidate_consumptions(item_type, days)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


## VIEWS: Usage Parameters


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/parameters", methods=["GET"])
@is_admin
def api_v3_admin_usage_parameters(payload):
    return (
        json.dumps(get_usage_parameters()),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/list_parameters", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_usage_list_parameters(payload):
    data = request.get_json(force=True)
    if data.get("ids"):
        result = get_usage_parameters(data.get("ids"))
    else:
        result = {}

    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/parameters", methods=["POST"])
@is_admin
def api_v3_admin_usage_parameters_add(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")
    data = _validate_item("usage_parameters", data)

    return (
        json.dumps(add_usage_parameters(data)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/parameters/<parameter_id>", methods=["PUT"])
@is_admin
def api_v3_admin_usage_parameters_update(payload, parameter_id):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")
    data = _validate_item("usage_parameters", data)

    return (
        json.dumps(update_usage_parameters(data)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/parameters/<parameter_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_usage_parameters_delete(payload, parameter_id):
    return (
        json.dumps(delete_usage_parameters(parameter_id)),
        200,
        {"Content-Type": "application/json"},
    )


## VIEWS: Usage Limits


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/limits", methods=["GET"])
@is_admin
def api_v3_admin_usage_limits(payload):
    return (
        json.dumps(get_usage_limits()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/limits", methods=["POST"])
@is_admin
def api_v3_admin_usage_limits_add(payload):
    data = request.get_json()
    data = _validate_item("usage_limit", data)

    return (
        json.dumps(add_usage_limits(data["name"], data["desc"], data["limits"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/limits/<limit_id>", methods=["PUT"])
@is_admin
def api_v3_admin_usage_limits_update(payload, limit_id):
    data = request.get_json()
    data = _validate_item("usage_limit", data)

    return (
        json.dumps(
            update_usage_limits(limit_id, data["name"], data["desc"], data["limits"])
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/limits/<limit_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_usage_limits_delete(payload, limit_id):
    return (
        json.dumps(delete_usage_limits(limit_id)),
        200,
        {"Content-Type": "application/json"},
    )


## VIEWS: Usage Groupings


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/groupings", methods=["GET"])
@is_admin
def api_v3_admin_usage_groupings(payload):
    return (
        json.dumps(get_usage_groupings()),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/groupings_dropdown", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_usage_groupings_dropdown(payload):
    return (
        json.dumps(get_usage_groupings_dropdown()),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/grouping/<grouping_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_usage_grouping(payload, grouping_id):
    return (
        json.dumps(get_usage_grouping(grouping_id)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/groupings", methods=["POST"])
@is_admin
def api_v3_admin_usage_groupings_add(payload):
    data = request.get_json()
    data = _validate_item("usage_grouping", data)
    return (
        json.dumps(add_usage_grouping(data)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/groupings/<grouping_id>", methods=["PUT"])
@is_admin
def api_v3_admin_usage_groupings_update(payload, grouping_id):
    data = request.get_json()
    data = _validate_item("usage_grouping", data)
    return (
        json.dumps(update_usage_grouping(data)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/groupings/<grouping_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_usage_groupings_delete(payload, grouping_id):
    return (
        json.dumps(delete_usage_grouping(grouping_id)),
        200,
        {"Content-Type": "application/json"},
    )


## VIEWS: Usage Credits


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route(
    "/api/v3/admin/usage/category_credits",
    methods=["GET"],
)
@is_admin
def api_v3_admin_usage_all_credits(payload):
    return (
        json.dumps(get_all_usage_credits(), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route(
    "/api/v3/admin/usage/category_credits/<category_credit_id>",
    methods=["GET"],
)
@is_admin
def api_v3_admin_usage_credits_by_id(payload, category_credit_id):
    return (
        json.dumps(get_usage_credits_by_id(category_credit_id), default=str),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route(
    "/api/v3/admin/usage/credits/<consumer>/<item_type>/<item_id>/<grouping_id>/<start_date>/<end_date>",
    methods=["GET"],
)
@is_admin_or_manager
def api_v3_admin_usage_credits(
    payload, consumer, item_type, item_id, grouping_id, start_date, end_date
):
    if (
        consumer == "category"
        and payload["role_id"] == "manager"
        and payload["category_id"] != item_id
    ):
        raise Error("forbidden", "You are not allowed to access this category")
    return (
        json.dumps(
            get_usage_credits(item_id, item_type, grouping_id, start_date, end_date)
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route(
    "/api/v3/admin/usage/credits",
    methods=["POST"],
)
@is_admin
def api_v3_admin_usage_credits_add(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    data["end_date"] = data["end_date"] if data["end_date"] != "null" else None

    itemExists("usage_limit", data["limit_id"])

    data = _validate_item("usage_credit", data)

    try:
        data["start_date"] = datetime.strptime(
            data["start_date"], "%Y-%m-%d"
        ).astimezone(pytz.UTC)
        if data["end_date"]:
            data["end_date"] = datetime.strptime(
                data["end_date"], "%Y-%m-%d"
            ).astimezone(pytz.UTC)
    except:
        raise Error("bad_request", "Incorrect date format. Expected format: %Y-%m-%d")

    for item_id in data["item_ids"]:
        data["item_id"] = item_id
        result = add_usage_credit(data)

    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route(
    "/api/v3/admin/usage/credits/<credit_id>",
    methods=["PUT"],
)
@is_admin
def api_v3_admin_usage_credits_update(payload, credit_id):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    itemExists("usage_credit", credit_id)

    if data.get("end_date"):
        data["end_date"] = data["end_date"] if data["end_date"] != "null" else None

    data = _validate_item("usage_credit_update", data)

    if data.get("start_date") or data.get("end_date"):
        try:
            data["start_date"] = datetime.strptime(
                data["start_date"], "%Y-%m-%d"
            ).astimezone(pytz.UTC)
            if data["end_date"]:
                data["end_date"] = datetime.strptime(
                    data["end_date"], "%Y-%m-%d"
                ).astimezone(pytz.UTC)
        except:
            raise Error(
                "bad_request", "Incorrect date format. Expected format: %Y-%m-%d"
            )

    return (
        json.dumps(update_usage_credit(data)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/usage/credits/<credit_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_usage_credits_delete(payload, credit_id):
    return (
        json.dumps(delete_usage_credit(credit_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/unify/<item_id>/item_name", methods=["PUT"])
@is_admin
def api_v3_admin_usage_unify_item_name(payload, item_id):
    return (
        json.dumps({"name": unify_item_name(item_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/reset_date", methods=["GET"])
@app.route("/api/v3/admin/usage/reset_date/<start_date>/<end_date>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_usage_reset_day(payload, start_date=None, end_date=None):
    if start_date and end_date:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=pytz.timezone("UTC")
        )
        end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=pytz.timezone("UTC")
        )
    reset_dates = get_reset_dates(start_date, end_date)
    result = []
    if len(reset_dates):
        for date in reset_dates:
            result.append(date.strftime("%m/%d/%Y"))
    else:
        result = []

    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/reset_dates", methods=["PUT"])
@is_admin
def api_v3_admin_usage_reset_add(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    try:
        parsed_dates = [
            datetime.strptime(date, "%m/%d/%Y") for date in data["date_list"]
        ]
    except:
        parsed_dates = []
    add_reset_date(parsed_dates)

    return (
        json.dumps(data["date_list"]),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/usage/delete_data", methods=["DELETE"])
@is_admin
def api_v3_admin_usage_delete_consumption_data(payload):
    gevent.spawn(delete_all_consumption_data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/usage/check/overlapping/<credit_id>/<start_date>/<end_date>",
    methods=["GET"],
)
@is_admin
def api_v3_admin_usage_check_overlapping(payload, credit_id, start_date, end_date):
    credit = get_usage_credits_by_id(credit_id)
    start_date = start_date if start_date != "null" else None
    end_date = end_date if end_date != "null" else None
    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").astimezone(pytz.UTC)
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d").astimezone(pytz.UTC)
    except:
        raise Error("bad_request", "Incorrect date format. Expected format: %Y-%m-%d")

    return (
        json.dumps(
            check_overlapping_credits(
                credit["item_id"],
                credit["item_type"],
                credit["grouping_id"],
                start_date,
                end_date,
                credit_id,
            ),
            default=str,
        ),
        200,
        {"Content-Type": "application/json"},
    )
