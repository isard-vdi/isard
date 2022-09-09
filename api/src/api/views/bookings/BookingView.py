import json
import logging as log

from flask import request

from api import app

from ...libv2.api_exceptions import Error
from ...libv2.bookings.api_booking import Bookings
from ..decorators import has_token, is_admin

apib = Bookings()


@app.route("/api/v3/bookings/priority/<item_type>/<item_id>", methods=["GET"])
@has_token
def api_v3_user_priority(payload, item_type, item_id):
    return json.dumps(apib.get_user_priority(payload, item_type, item_id))


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

    # Get bookings for one item
    if item_id:
        return json.dumps(
            apib.get_item_bookings(
                payload, start_date, end_date, item_type, item_id, returnType
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
    # CHECK: owns booking_id
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
        except UpdateFailed:
            log.error("Event " + booking_id + " update failed.")
            return (
                json.dumps({"error": "undefined_error", "msg": "Event update failed"}),
                404,
                {"Content-Type": "application/json"},
            )
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
