import json
import logging as log

from flask import request

from api import app

from ..._common.api_exceptions import Error
from ...libv2.bookings.api_reservables import Reservables
from ...libv2.bookings.api_reservables_planner import ReservablesPlanner
from ..decorators import checkDuplicate, has_token, is_admin

api_ri = Reservables()
api_rp = ReservablesPlanner()

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
        return json.dumps(api_ri.list_items(reservable_type)), 200


# Gets list of subitems available in this item_id (profiles) [{"id","profile","units"}]
@app.route("/api/v3/admin/reservables/<reservable_type>/<item_id>", methods=["GET"])
@app.route(
    "/api/v3/admin/reservables/enable/<reservable_type>/<item_id>/<subitem_id>",
    methods=["PUT"],
)
@is_admin
def api_v3_reservable_items(payload, reservable_type, item_id, subitem_id=None):
    if request.method == "PUT":
        data = request.get_json()
        if reservable_type == "gpus":
            if data.get("enabled") == False:
                desktops_ids = (
                    [desktop["id"] for desktop in data["desktops"]]
                    if data.get("desktops")
                    else None
                )
                if desktops_ids:
                    api_ri.deassign_desktops_with_gpu(
                        reservable_type, subitem_id, desktops_ids
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
    "/api/v3/admin/reservables/check/last/<reservable_type>/<subitem_id>",
    methods=["GET"],
)
@is_admin
def api_v3_reservable_check_last(payload, reservable_type, subitem_id):
    data = {}
    data["last"] = api_ri.check_last_subitem(reservable_type, subitem_id)
    data["desktops"] = api_ri.check_desktops_with_profile(reservable_type, subitem_id)

    return json.dumps(data), 200


#### Endpoints for planning resources
##########################################################################

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


# Deletes a plan
@app.route("/api/v3/admin/reservables_planner/<plan_id>", methods=["DELETE"])
@is_admin
def api_v3_reservables_planner_event_delete(payload, plan_id):
    api_rp.delete_plan(plan_id)
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
