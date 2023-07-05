import datetime
import json
import logging as log
from datetime import datetime, timedelta, timezone

import pytz
from flask import request

from api import app

from ..._common.api_exceptions import Error
from ...libv2.api_allowed import ApiAllowed
from ...libv2.api_desktops_persistent import ApiDesktopsPersistent
from ...libv2.bookings.api_booking import Bookings
from ...libv2.bookings.api_reservables_planner_compute import payload_priority
from ...libv2.deployments.api_deployments import get
from ..decorators import (
    has_token,
    is_admin,
    ownsBookingId,
    ownsDeploymentId,
    ownsDomainId,
)

allowed = ApiAllowed()


apib = Bookings()
desktops = ApiDesktopsPersistent()

MIN_AUTOBOOKING_TIME = 30
MAX_BOOKING_TIME = 12 * 60  # 12h


@app.route("/api/v3/bookings/priority/<item_type>/<item_id>", methods=["GET"])
@has_token
def api_v3_user_priority(payload, item_type, item_id):
    if item_type == "desktop":
        name = desktops.Get(item_id)["name"]
    else:
        name = get(item_id, False)["name"]
    return json.dumps(
        {
            **apib.get_user_priority(payload, item_type, item_id),
            **{"name": name},
        }
    )


@app.route("/api/v3/bookings/priorities", methods=["POST"])
@is_admin
def api_v3_user_priorities(payload):
    data = request.get_json()
    return json.dumps(apib.get_users_priorities(data["rule_id"]))


# Gets list of priorities rules
@app.route("/api/v3/admin/priority/rules", methods=["GET"])
@is_admin
def api_v3_priority_rules(payload):
    return json.dumps(apib.list_priority_rules()), 200


# Gets all desktops/deployments bookings for only for one item_id
@app.route("/api/v3/bookings/user", methods=["GET"])
@app.route("/api/v3/bookings/user/<item_id>/<item_type>", methods=["GET"])
@app.route("/api/v3/bookings/user/<item_id>/<item_type>/<returnType>", methods=["GET"])
@has_token
def api_v3_bookings_user(payload, item_type=None, item_id=None, returnType=None):
    data = request.args
    start_date = data.get("startDate")
    end_date = data.get("endDate")

    if not start_date or not end_date:
        Error("bad_request", "Missing start or end date.")

    # Get all user bookings
    if not item_type and not item_id:
        return json.dumps(
            apib.get_user_bookings(start_date, end_date, payload["user_id"])
        )
    if item_type == "desktop":
        ownsDomainId(payload, item_id)
    elif item_type == "deployment":
        ownsDeploymentId(payload, item_id)

    # Get bookings for one item
    if item_id:
        return json.dumps(
            apib.get_item_bookings(
                payload,
                start_date,
                end_date,
                item_type,
                item_id,
                returnType,
            )
        )


# Gets desktop/item availability (crosses info with resource planner)
@app.route("/api/v3/bookings/availability/<item_type>/<item_id>", methods=["GET"])
@has_token
def api_v3_bookings_availability(payload, item_type, item_id):
    return json.dumps(
        apib.get_item_availability(item_type, item_id),
        indent=4,
        sort_keys=True,
        default=str,
    )


# Gets one booking_id info, Updates or deletes
@app.route("/api/v3/booking/event/<booking_id>", methods=["GET", "PUT", "DELETE"])
@has_token
def api_v3_booking_event_id(payload, booking_id):
    ownsBookingId(payload, booking_id)
    if request.method == "GET":
        return json.dumps(apib.get(booking_id))

    if request.method == "DELETE":
        if booking_id == False:
            log.error("Incorrect access parameters. Check your query.")
            return (
                json.dumps(
                    {
                        "error": "bad_request",
                        "msg": "Incorrect access parameters. Check your query.",
                    }
                ),
                400,
                {"Content-Type": "application/json"},
            )
        apib.delete(booking_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}

    if request.method == "PUT":
        data = request.form
        title = data.get("title")
        start = data.get("start")
        end = data.get("end")
        try:
            apib.update(booking_id, title, start, end)
        except:
            log.error("Event " + booking_id + " update failed.")
            raise Error("internal_server", "Event update failed")
        return json.dumps({}), 200, {"Content-Type": "application/json"}


# Adds a booking event for an item
@app.route("/api/v3/booking/event", methods=["POST"])
@has_token
def api_v3_booking_event(payload):
    # CHECK: User is allowed to book event for:
    #        - those resources
    #        - his category
    #        - the amount of resources available
    data = request.get_json()
    return json.dumps(
        apib.add(
            payload,
            data["start"],
            data["end"],
            data["element_type"],
            data["element_id"],
            data.get("title", None),
            data.get("now", False),
        )
    )


########## ADMIN ENDPOINTS


## List categories/groups/users with reservations available
## Filtering calendar
@app.route("/api/v3/booking/admin/categories", methods=["GET"])
@is_admin
def api_v3_booking_admin_categories(payload):
    return json.dumps(apib.get_categories())


@app.route("/api/v3/booking/admin/groups", methods=["GET"])
@app.route("/api/v3/booking/admin/groups/<category_id>", methods=["GET"])
@is_admin
def api_v3_booking_admin_groups(payload, category_id=False):
    return json.dumps(apib.get_groups(category_id))


@app.route("/api/v3/booking/admin/users", methods=["GET"])
@app.route("/api/v3/booking/admin/users/<group_id>", methods=["GET"])
@is_admin
def api_v3_booking_admin_users(payload, group_id=False):
    return json.dumps(apib.get_users(group_id))


## Admin can get all events
@app.route("/api/v3/booking/admin/events", methods=["GET"])
@is_admin
def api_v3_booking_admin_events(payload):
    data = request.args

    return json.dumps(apib.get())


@app.route("/api/v3/booking/admin/event/<event_id>", methods=["GET", "PUT", "DELETE"])
@is_admin
def api_v3_admin_booking_event(payload, event_id):
    if request.method == "GET":
        return json.dumps(data[""][2])

    if request.method == "DELETE":
        None
    if request.method == "PUT":
        data = request.args
        title = data.get("title")
        start = data.get("start")
        end = data.get("end")


@app.route("/api/v3/booking/max_booking_date/<desktop_id>", methods=["GET"])
@has_token
def api_v3_admin_booking_max_booking_date(payload, desktop_id):
    return desktops.check_max_booking_date(payload, desktop_id)


@app.route("/api/v3/booking/reservables_available", methods=["GET"])
@has_token
def api_v3_admin_booking_reservables_available(payload):
    # Get all users reservables
    allowed_reservables = {
        "vgpus": allowed.get_items_allowed(
            payload,
            "reservables_vgpus",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
    }
    available = []
    fromDate = datetime.now(timezone.utc)
    toDate = fromDate + timedelta(minutes=MAX_BOOKING_TIME)
    fromDate = fromDate.strftime("%Y-%m-%dT%H:%M%z")
    toDate = toDate.strftime("%Y-%m-%dT%H:%M%z")
    for k, v in allowed_reservables.items():
        for reservable in v:
            priority = payload_priority(payload, {"vgpus": [reservable["id"]]})
            # Check if the reservable is currently planned
            current_plan = apib.reservables_planner.get_item_availability(
                payload,
                None,
                None,
                fromDate,
                toDate,
                subitems={"vgpus": [reservable["id"]]},
            )
            if not current_plan or current_plan[0]["start"] > fromDate:
                continue

            # If so, compute the maximum booking time
            forbid_time = priority["forbid_time"]
            max_time = priority["max_time"]
            available_time = int(
                (
                    datetime.strptime(
                        current_plan[0]["end"], "%Y-%m-%dT%H:%M%z"
                    ).astimezone(pytz.UTC)
                    - datetime.now(timezone.utc)
                ).total_seconds()
                / 60
            )
            if payload["role_id"] == "admin":
                max_booking_time = min(max_time, available_time)
            else:
                max_booking_time = min(forbid_time, max_time, available_time)

            if max_booking_time >= MIN_AUTOBOOKING_TIME:
                max_booking_time = min(max_booking_time, MAX_BOOKING_TIME)

                max_booking_date = datetime.strftime(
                    datetime.now(timezone.utc) + timedelta(minutes=max_booking_time),
                    "%Y-%m-%dT%H:%M%z",
                )
                available.append(
                    {
                        "id": reservable["id"],
                        "name": reservable["name"],
                        "description": reservable["description"],
                        "max_booking_date": max_booking_date,
                    }
                )

    if len(available):
        return json.dumps({"reservables_available": available})
    else:
        raise Error(
            "precondition_required",
            "There's no gpu profile available to start the desktop now",
            description_code="no_available_profile",
        )


@app.route("/api/v3/orchestrator/gpu/bookings", methods=["GET"])
@is_admin
def api_v3_profile_units(payload):
    return json.dumps(apib.get_booking_profile_count_within_one_hour())
