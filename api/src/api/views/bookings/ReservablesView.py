import json
import logging as log

import requests
from flask import request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.api_rest import ApiRest

from api import app

from ...libv2.bookings.api_reservables import Reservables
from ...libv2.bookings.api_reservables_planner import ReservablesPlanner
from ...libv2.bookings.api_reservables_planner_compute import get_subitems_planning
from ..decorators import checkDuplicate, has_token, is_admin

api_ri = Reservables()
api_rp = ReservablesPlanner()

notifier_client = ApiRest("isard-notifier")

#### Endpoints for resources that are reservable


# Gets list of reservables ["gpus","usbs"]
@app.route("/api/v3/admin/reservables", methods=["GET"])
@is_admin
def api_v3_reservables(payload):
    return json.dumps(api_ri.list_reservables()), 200


# Gets list of profiles
@app.route("/api/v3/admin/profiles/<reservable_type>", methods=["GET"])
@is_admin
def api_v3_profiles(payload, reservable_type):
    return json.dumps(api_ri.list_profiles(reservable_type)), 200


# # Gets list of items created from this reservable (card names) [{"id","model"...}]
@app.route("/api/v3/admin/reservables/<reservable_type>", methods=["GET", "POST"])
@is_admin
def api_v3_reservable_types(payload, reservable_type):
    if request.method == "POST":
        data = request.get_json()
        checkDuplicate("gpus", data["name"])
        return json.dumps(api_ri.add_item(reservable_type, data)), 200
    else:
        items = api_ri.list_items(reservable_type)
        for item in items:
            total_plans = api_rp.list_item_plans(item["id"])
            profile = total_plans[0]["subitem_id"] if total_plans else None
            profile = (
                api_ri.get_subitem("gpus", item["id"], profile)["profile"]
                if profile
                else None
            )
            item["plans"] = {
                "current": len(total_plans),
                "active": profile == item["active_profile"],
                "profile": profile,
            }
        return json.dumps(items), 200


# Gets list of subitems available in this item_id (profiles) [{"id","profile","units"}]
@app.route("/api/v3/admin/reservables/<reservable_type>/<item_id>", methods=["GET"])
@app.route(
    "/api/v3/admin/reservables/enable/<reservable_type>/<item_id>/<subitem_id>/notify_user",
    methods=["PUT"],
)
@app.route(
    "/api/v3/admin/reservables/enable/<reservable_type>/<item_id>/<subitem_id>",
    methods=["PUT"],
)
@is_admin
def api_v3_reservable_items(
    payload, reservable_type, item_id, subitem_id=None, notify_user=False
):
    if request.method == "PUT":
        data = request.get_json()
        if "notify_user" in request.url:
            notify_user = True
        if data.get("enabled") == False:
            api_rp.delete_subitem(reservable_type, item_id, subitem_id)

            if notify_user:
                users_items = api_rp.get_item_users(
                    reservable_type, item_id, [], subitem_id
                )
                for user_items in users_items:
                    try:
                        data = {
                            "text": "",
                            "user_id": user_items["user_id"],
                            "bookings": [
                                {
                                    "start": str(booking["start"]),
                                    "end": str(booking["end"]),
                                    "title": str(booking["title"]),
                                }
                                for booking in user_items["bookings"]
                            ],
                            "desktops": [
                                {"name": str(desktop["name"])}
                                for desktop in user_items["desktops"]
                            ],
                            "deployments": [
                                {"name": str(deployment["tag_name"])}
                                for deployment in user_items["deployments"]
                            ],
                        }
                        notifier_client.post("/mail/deleted-gpu", data)
                    except:
                        raise Error(
                            "internal_server",
                            (
                                "Exception when sending verification email to user "
                                + user_items.get("user_id")
                                if user_items
                                else ""
                            ),
                        )
        return (
            json.dumps(
                api_ri.enable_subitems(
                    reservable_type, item_id, subitem_id, data.get("enabled")
                )["id"]
            ),
            200,
        )
    else:
        return json.dumps(api_ri.list_subitems(reservable_type, item_id)), 200


# Gets list of subitems enabled for this item_id (profiles enabled in system) [{"id","profile","units"}]
@app.route(
    "/api/v3/admin/reservables/enabled/<reservable_type>/<item_id>", methods=["GET"]
)
@is_admin
def api_v3_reservable_items_enabled(payload, reservable_type, item_id):
    return json.dumps(api_ri.list_subitems_enabled(reservable_type, item_id)), 200


# Checks if last enabled gpu profile had just been disabled
@app.route(
    "/api/v3/admin/reservables/check/last/<reservable_type>/<subitem_id>/<item_id>",
    methods=["GET"],
)
@is_admin
def api_v3_reservable_check_last_subitem(payload, reservable_type, subitem_id, item_id):
    api_rp.check_subitem_current_plan(subitem_id, item_id)
    data = api_rp.check_subitem_desktops_and_plannings(
        reservable_type, item_id, subitem_id
    )

    return json.dumps(data, default=str), 200


# Checks if last enabled gpu has just been deleted
@app.route(
    "/api/v3/admin/reservables/check/last/<reservable_type>/<item_id>",
    methods=["GET"],
)
@is_admin
def api_v3_reservable_check_last_item(payload, reservable_type, item_id):
    data = {"last": [], "desktops": [], "plans": [], "bookings": [], "deployments": []}
    profiles = api_ri.list_subitems_enabled(reservable_type, item_id)
    for profile in profiles:
        api_rp.check_subitem_current_plan(profile["id"], item_id)
        subitem_data = api_rp.check_subitem_desktops_and_plannings(
            reservable_type, item_id, profile["id"]
        )
        data["last"].extend(subitem_data.get("last", []))
        if True in subitem_data.get("last"):
            data["desktops"].extend(subitem_data.get("desktops", []))
            data["plans"].extend(subitem_data.get("plans", []))
            data["bookings"].extend(subitem_data.get("bookings", []))
            data["deployments"].extend(subitem_data.get("deployments", []))

    return json.dumps(data, default=str), 200


@app.route(
    "/api/v3/admin/reservables/delete/<reservable_type>/<item_id>",
    methods=["DELETE"],
)
@app.route(
    "/api/v3/admin/reservables/delete/<reservable_type>/<item_id>/<notify_user>",
    methods=["DELETE"],
)
@is_admin
def api_v3_reservable_delete_gpu(payload, reservable_type, item_id, notify_user=False):
    if notify_user:
        subitems = [
            subitem["id"]
            for subitem in api_ri.list_subitems_enabled(reservable_type, item_id)
        ]
        users_items = []
        for subitem in subitems:
            api_rp.get_item_users(reservable_type, item_id, users_items, subitem)
        for user_items in users_items:

            try:
                data = {
                    "text": "",
                    "user_id": user_items["user_id"],
                    "bookings": [
                        {
                            "start": str(booking["start"]),
                            "end": str(booking["end"]),
                            "title": str(booking["title"]),
                        }
                        for booking in user_items["bookings"]
                    ],
                    "desktops": [
                        {"name": str(desktop["name"])}
                        for desktop in user_items["desktops"]
                    ],
                    "deployments": [
                        {"name": str(deployment["tag_name"])}
                        for deployment in user_items["deployments"]
                    ],
                }
                notifier_client.post("/mail/deleted-gpu", data)
            except:
                raise Error(
                    "internal_server",
                    "Exception when sending verification email to user "
                    + user_items["user_id"],
                )

    api_rp.delete_item(
        reservable_type,
        item_id,
    )
    return json.dumps({}, default=str), 200


#### Endpoints for planning resources
##########################################################################


# Gets all plans
@app.route("/api/v3/admin/reservables_planner", methods=["GET"])
@is_admin
def api_v3_reservables_planner_get(payload):
    return json.dumps(
        api_rp.list_all_item_plans(),
        sort_keys=True,
        default=str,
    )


# Gets actual plan for item (card) /subitem (profile) reservable resources
@app.route("/api/v3/admin/reservables_planner/actual_plan/<item_id>", methods=["GET"])
@is_admin
def api_v3_reservables_planner_get_item_actual_plan(payload, item_id):
    plan = api_rp.list_item_plans(item_id)
    if not len(plan):
        return json.dumps({})
    return json.dumps(plan[0])


# Gets actual plans for item (card) /subitem (profile) reservable resources
@app.route("/api/v3/admin/reservables_planner/<item_id>", methods=["GET"])
@app.route(
    "/api/v3/admin/reservables_planner/<item_id>/<start>/<end>",
    methods=["GET"],
)
@is_admin
def api_v3_reservables_planner_get_item(payload, item_id, start=None, end=None):
    return json.dumps(
        api_rp.list_item_plans(item_id, start, end),
        indent=4,
        sort_keys=True,
        default=str,
    )


@app.route("/api/v3/admin/reservables_planner/<item_id>/<subitem_id>", methods=["GET"])
@app.route(
    "/api/v3/admin/reservables_planner/<item_id>/<subitem_id>/<start>/<end>",
    methods=["GET"],
)
@is_admin
def api_v3_reservables_planner_get_item_subitem(
    payload, item_id, subitem_id, start=None, end=None
):
    return json.dumps(
        api_rp.list_subitem_plans(item_id, subitem_id, start, end),
        indent=4,
        sort_keys=True,
        default=str,
    )


@app.route("/api/v3/admin/reservables_planner/subitem/<subitem_id>", methods=["GET"])
@app.route(
    "/api/v3/admin/reservables_planner/subitem/<subitem_id>/<start>/<end>",
    methods=["GET"],
)
@is_admin
def api_v3_reservables_planner_get_subitem(payload, subitem_id, start=None, end=None):
    return json.dumps(
        api_rp.get_same_subitems_plans([subitem_id], start, end),
        indent=4,
        sort_keys=True,
        default=str,
    )


# Adds new plan for a profile
@app.route("/api/v3/admin/reservables_planner", methods=["POST"])
@is_admin
def api_v3_reservables_planner_event(payload):
    data = request.get_json()
    return json.dumps(api_rp.add_plan(payload, data))


# Gets bookings in a plan
@app.route("/api/v3/admin/reservables_planner/<plan_id>/bookings", methods=["GET"])
@is_admin
def api_v3_reservables_planner_event_existing_bookings(payload, plan_id):
    return json.dumps(api_rp.get_plan_bookings(plan_id), sort_keys=True, default=str)


# Deletes a plan
@app.route("/api/v3/admin/reservables_planner/<plan_id>", methods=["DELETE"])
@is_admin
def api_v3_reservables_planner_event_delete(payload, plan_id):
    api_rp.delete_plan(plan_id)
    return json.dumps({})


# Updates plan start/end
@app.route("/api/v3/admin/reservables_planner/<plan_id>/<start>/<end>", methods=["PUT"])
@is_admin
def api_v3_reservables_planner_event_update(payload, plan_id, start, end):
    api_rp.update_plan(payload, plan_id, start, end)
    return json.dumps({})


### Booking views
################


## Where can we put a new booking
##
@app.route("/api/v3/admin/reservables_planner/booking_provisioning", methods=["POST"])
@app.route(
    "/api/v3/admin/reservables_planner/booking_provisioning/<start>/<end>",
    methods=["POST"],
)
@has_token
def api_v3_reservables_where_booking_can_be_added(payload, start=None, end=None):
    data = request.get_json()
    return json.dumps(
        api_rp.booking_provisioning(
            payload,
            data["subitems"],  # from desktop/deployment create_dict-reservables
            data["units"],  # units that will need this desktop/deployment
            data["priority"],  # user priority over existing reservations
            data[
                "block_interval"
            ],  # user blocked interval where nothing can be changed
            start,
            end,
        ),
        indent=4,
        sort_keys=True,
        default=str,
    )


# Gets the plans for a resource type (all vgpus, all usbs)
@app.route("/api/v3/admin/reservables_planner/<resource_type>", methods=["GET"])
@is_admin
def api_v3_reservables_planner_get_type(
    payload,
    resource_type,
    start=None,
    end=None,
):
    return json.dumps(
        api_rp.get_resource_type_planning(resource_type, start, end),
        indent=4,
        sort_keys=True,
        default=str,
    )


# Checks planning integrity
@app.route("/api/v3/admin/reservables_planner/check_integrity", methods=["GET"])
@is_admin
def api_v3_reservables_planner_integrity(payload):
    return json.dumps(api_rp.is_any_plan_item_id_overlapped())
