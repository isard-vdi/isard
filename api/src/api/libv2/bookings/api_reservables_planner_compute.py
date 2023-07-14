#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import os
from datetime import datetime, timedelta
from pprint import pformat

import portion as P
import pytz

from ..._common.api_exceptions import Error


## BOOKING PROVISIONING
def booking_provisioning(
    payload,
    item_type,
    item_id,
    subitems,
    units,
    priority,
    fromDate=None,
    toDate=None,
    skip_booking_id=None,
):
    # Resource planner intersection for subitems
    # First find same reservable_type intersection for each type keeping non overlapping
    resource_planner = {}
    for k, v in subitems.items():
        ## NOTE: Here we add all them even if they are in the same item_type
        ##       Maybe an option in resource is needed to define if the resource
        ##       profiles can be multiple and handle here their intersection correctly
        ##       Now the interface doesn't allow for more than one profile in the sam item_type
        if not v or not len(v):
            continue
        # Sum overlapped and keep non overlapped
        for subitem in v:
            all_plans = get_subitems_planning([subitem])
            resource_planner[subitem] = intersect_same_subitem_plan(all_plans, subitem)
            log.debug(
                "Plans for "
                + k
                + "/"
                + subitem
                + ": "
                + str(len(resource_planner[subitem]))
            )

    ## Now remove different subitem non overlapped
    # We have to combine all them and remove non overlapping
    # But only if there is more than one plan (if not we will remove the intervals non overlapped in the only item available)
    if len(resource_planner.keys()) > 1:
        all_plans = []
        for subitem, plans in resource_planner.items():
            all_plans += plans
        resource_planner = intersect_different_subitem_plan(all_plans)
    else:
        resource_planner = resource_planner[list(resource_planner.keys())[0]]

    # Get overridable and nonoverridable bookings
    overridable = get_overridable_bookings(
        priority, subitems, fromDate, toDate, skip_booking_id
    )
    nonoverridable = get_nonoverridable_bookings(
        priority, subitems, fromDate, toDate, skip_booking_id
    )
    # Substract both from resource_planner
    resource_planner = compute_overridable_bookings(
        overridable, nonoverridable, resource_planner, units
    )
    # Remove existing bookings for this item from resource_planner
    if item_id and item_type:
        resource_planner = remove_existing_item_bookings(
            resource_planner, item_type, item_id
        )
    # This will join consecutive plans
    # When debugging it is better to show them splitted (do not join)
    # Removed because it would cause problems with the start now feature
    # if not os.environ.get("LOG_LEVEL") == "DEBUG":
    resource_planner = join_consecutive_plans(resource_planner)
    return resource_planner


## RESOURCE PLANNER INTERSECTIONS
def get_subitems_planning(subitems, start=None, end=None, item_id=None, now=None):
    if not start:
        start = datetime.now(pytz.utc)

    if now:
        end = start

    if item_id:
        query = r.table("resource_planner").get_all(
            [item_id, r.args(subitems)], index="item-subitem"
        )
    else:
        query = r.table("resource_planner").get_all(
            r.args(subitems), index="subitem_id"
        )

    if start:
        query = query.filter(lambda plan: plan["end"] > start)
    if end:
        query = query.filter(lambda plan: plan["start"] < end)

    with app.app_context():
        plans = list(query.run(db.conn))
    if not item_id:
        log.debug("FOUND " + str(len(plans)) + " FOR ALL PROFILES " + str(subitems))
    return plans


def remove_existing_item_bookings(plans, item_type, item_id, start=None, end=None):
    ## Wait!! We should remove all items plannings! not only the plans in the
    ## current reservable the item has now, as it can't be reserved with two
    ## different reservables at the same time
    if not start:
        start = datetime.now(pytz.utc)

    query = r.table("bookings").get_all(item_id, index="item_id")

    with app.app_context():
        bookings = list(query.run(db.conn))

    log.debug("FOUND " + str(len(plans)) + " existing plans_intervals")
    log.debug(
        "FOUND " + str(len(bookings)) + " existing bookings to be removed from planning"
    )
    plans_intervals = convert_plans_to_portions(plans)

    join_plan_op = lambda x, y: {
        "event_type": "unavailable",
    }

    for interval in bookings:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict(
            {
                i: {
                    "units": interval["units"],
                    "id": interval["id"],
                    "event_type": "available",
                }
            }
        )
        plans_intervals = plans_intervals.combine(d, how=join_plan_op)

    items = []
    for interval, value in plans_intervals.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    # When the "start" key it's not there it will be because the interval
    # is not available, but because the item is reserved in another reservable item
    return [item[1] for item in items if "start" in item[1].keys()]


def intersect_same_subitem_plan(plan, plan_name, keep_non_overlapped=True):
    join_plan_op = lambda x, y: {
        "units": x["units"] + y["units"],
        "id": x["id"] + "/" + y["id"],
    }

    output = P.IntervalDict()
    for interval in plan:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
        output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    if not keep_non_overlapped:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "id": plan_name,
                "event_type": "available",
            }
            for item in items
            if len(item[1]["id"].split("/")) > 1
        ]
    else:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "id": plan_name,
                "event_type": "available",
            }
            for item in items
        ]


def count_non_overridable_bookings(plan_id, subitem_id, priority, start, end):
    query = r.table("bookings")
    query = query.filter(r.row["reservables"]["vgpus"].contains(subitem_id))
    query = query.filter(r.row["start"] <= end).filter(r.row["end"] >= start)
    query = query.filter(
        r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
    )
    query = query.filter(
        r.row["plans"].contains(lambda plan: plan["priority"] <= priority)
    )
    with app.app_context():
        bookings = list(query.run(db.conn))
    if not len(bookings):
        log.debug(
            "---> Counting nonoverridables: No bookings for "
            + str(subitem_id)
            + " within: \nStart: "
            + str(start)
            + "\nEnd:"
            + str(end)
        )
        return 0
    # We need to intersect plans and get the max units_booked for all of them
    current_plans = []
    for booking in bookings:
        for plan in booking["plans"]:
            if plan["plan_id"] == plan_id:
                # This is only for already done bookings before this MR
                if not plan.get("units_booked"):
                    plan["units_booked"] = booking["units"]
                plan["start"] = booking["start"]
                plan["end"] = booking["end"]
                current_plans.append(plan)

    # Intersect plans
    join_plan_op = lambda x, y: {
        "units_booked": x["units_booked"] + y["units_booked"],
        "plan_id": x["plan_id"] + "/" + y["plan_id"],
    }

    output = P.IntervalDict()
    for interval in current_plans:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict(
            {
                i: {
                    "units_booked": interval["units_booked"],
                    "plan_id": interval["plan_id"],
                }
            }
        )
        output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()
    log.debug(
        "---> Counting nonoverridables: Found "
        + str(len(bookings))
        + " bookings, getting the max of intersections units_booked: "
        + str([item[1]["units_booked"] for item in items])
        + " within \nStart: "
        + str(start)
        + "\nEnd:"
        + str(end)
    )

    max = 0
    for item in items:
        if item[1]["units_booked"] > max:
            max = item[1]["units_booked"]
    log.debug(
        "-----------> Found " + str(max) + " max units already booked in interval"
    )
    return max


def get_same_plans_for_booking(
    plans,
    subitem_id,
    priority,
    booking_start,
    booking_end,
    units,
    keep_non_overlapped=True,
):
    booking_interval = P.closed(booking_start, booking_end)
    # Remove plans that not fit in date or are full
    for interval in list(plans):
        i = P.closed(interval["start"], interval["end"])
        if booking_interval not in i:
            log.debug("INTERVAL NOT FITS")
            plans.remove(interval)
            continue
    if units > 1:
        # Deployment booking
        log.debug("\n\n\n\n")
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug(
            "--------- START DEPLOYMENT BOOKING FOR "
            + str(units)
            + " UNITS IN "
            + str(len(plans))
            + " PLANS --------"
        )
        log.debug(
            "------------------------------------------------------------------------"
        )
        deployment_plans = []
        remaining_units_to_be_assigned = units
        for plan in plans:
            # Here we decide if it is available or not
            log.debug(
                "-> Remaining units to be assigned: "
                + str(remaining_units_to_be_assigned)
            )
            avail_in_plan = plan["units"] - count_non_overridable_bookings(
                plan["id"], subitem_id, priority, booking_start, booking_end
            )
            log.debug("-> Available plan units: " + str(avail_in_plan))
            if avail_in_plan > 0:
                if remaining_units_to_be_assigned - avail_in_plan > 0:
                    # Reserve all available from this plan an loop another plan for the rest
                    plan["units_booked"] = avail_in_plan
                    remaining_units_to_be_assigned = (
                        remaining_units_to_be_assigned - avail_in_plan
                    )
                    log.debug("---> New plan appended")
                    deployment_plans.append(plan)
                else:
                    # There will be still room left for other bookings in this plan
                    # units_booked=remaining_units_... then break
                    # Reserve all available from this plan an loop another plan for the rest
                    plan["units_booked"] = remaining_units_to_be_assigned
                    log.debug(
                        "---> New plan appended. Last one as fits "
                        + str(remaining_units_to_be_assigned)
                        + " in "
                        + str(avail_in_plan)
                    )
                    remaining_units_to_be_assigned = 0
                    deployment_plans.append(plan)
                    break
            else:
                log.debug(
                    "-> Skipping plan because it is full in this interval: "
                    + str(plan["id"])
                )
        if remaining_units_to_be_assigned > 0:
            log.debug(
                "------------------------------------------------------------------------"
            )
            log.debug(
                "--- END DEPLOY BOOKING. UNABLE TO FIT ALL UNITS IN AVAILABLE PLANS -----"
            )
            log.debug(
                "------------------------------------------------------------------------"
            )
            log.debug("\n\n\n\n")
            return []
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug(
            "--- END DEPLOY BOOKING WITH TOTAL OF "
            + str(len(deployment_plans))
            + " PLANS ---"
        )
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug("\n\n\n\n")
        return deployment_plans
    else:
        # Desktop booking
        log.debug("\n\n\n\n")
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug(
            "--------- START DESKTOP BOOKING FOR "
            + str(units)
            + " UNITS IN "
            + str(len(plans))
            + " PLANS --------"
        )
        log.debug(
            "------------------------------------------------------------------------"
        )
        for plan in plans:
            log.debug("-> Available plan units: " + str(plan["units"]))
            if (
                plan["units"]
                - 1
                - count_non_overridable_bookings(
                    plan["id"], subitem_id, priority, booking_start, booking_end
                )
                >= 0
            ):
                log.debug(
                    "------------------------------------------------------------------------"
                )
                log.debug(
                    "--- END DESKTOP BOOKING WITH ASSIGNED PLAN -----------------------------"
                )
                log.debug(
                    "------------------------------------------------------------------------"
                )
                log.debug("\n\n\n\n")
                plan["units_booked"] = 1
                return [plan]
            else:
                log.debug(
                    "-> Skipping plan because it is full in this interval: "
                    + str(plan["id"])
                )
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug(
            "--- END DESKTOP BOOKING. UNABLE TO FIT 1 UNITS IN AVAILABLE PLANS ------"
        )
        log.debug(
            "------------------------------------------------------------------------"
        )
        log.debug("\n\n\n\n")
        return []


def get_different_plans_for_booking(plans):
    join_plan_op = lambda x, y: {
        "units": min(x["units"], y["units"]),
        "id": x["id"] + "/" + y["id"],
    }

    output = P.IntervalDict()
    for interval in plan:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
        output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    # [{'end': datetime.datetime(2022, 4, 22, 13, 29, 59, tzinfo=<rethinkdb.ast.RqlTzinfo object at 0x7fc440f81df0>),
    #   'event_type': 'available',
    #   'id': '45102a40-f64a-4938-91f1-7247fe73d560',
    #   'item_id': 'nova',
    #   'item_type': 'gpus',
    #   'start': datetime.datetime(2022, 4, 22, 10, 30, tzinfo=<rethinkdb.ast.RqlTzinfo object at 0x7fc440f81d30>),
    #   'subitem_id': 'NVIDIA-A40-16Q',
    #   'units': 2,
    #   'user_id': 'local-default-admin-admin'},

    return [
        {
            "start": P.to_data(item[0])[0][1],
            "end": P.to_data(item[0])[0][2],
            "units": item[1]["units"],
            "ids": item[1]["id"].split("/"),
            "id": item[1]["id"],
            "event_type": "available",
        }
        for item in items
        if len(item[1]["id"].split("/")) > 1
    ]


def join_consecutive_plans(plan):
    join_plan_op = lambda x, y: {
        "units": 1,
        "id": "available",
    }
    output = P.IntervalDict()
    for interval in plan:
        if interval.get("start") and interval.get("units", 0) > 0:
            i = P.closedopen(interval["start"], interval["end"])
            d = P.IntervalDict({i: {"units": 1, "id": "available"}})
            output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    return [
        {
            "start": P.to_data(item[0])[0][1],
            "end": P.to_data(item[0])[0][2],
            "units": "Enough",
            "ids": item[1]["id"].split("/"),
            "id": item[1]["id"],
            "event_type": "available",
        }
        for item in items
    ]


def intersect_different_subitem_plan(plan, keep_non_overlapped=False):
    join_plan_op = lambda x, y: {
        "units": min(x["units"], y["units"]),
        "id": x["id"] + "/" + y["id"],
    }

    output = P.IntervalDict()
    for interval in plan:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
        output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    if not keep_non_overlapped:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "id": item[1]["id"],
                "event_type": "available",
            }
            for item in items
            if len(item[1]["id"].split("/")) > 1
        ]
    else:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "event_type": "available",
            }
            for item in items
        ]


## BOOKINGS PRIORITY RULES
def payload_priority(payload, reservables):
    log.debug("USER PAYLOAD")
    log.debug(payload)
    priority = None
    items_priority = {}
    for k, v in reservables.items():
        for subitem in v:
            with app.app_context():
                reservable = r.table("reservables_" + k).get(subitem).run(db.conn)
                if not reservable.get("priority_id") or reservable["priority_id"] == "":
                    priority_id = "default"
                else:
                    priority_id = reservable.get("priority_id")
                rules = list(
                    r.table("bookings_priority")
                    .get_all(priority_id, index="rule_id")
                    .order_by(r.desc("priority"))
                    .run(db.conn)
                )
            new_priority = user_matches_priority_rule(payload, rules)
            if not new_priority:
                new_priority = get_user_default_priority(payload, subitem)
            tmp_priority = most_restrictive_rule(subitem, new_priority, priority)
            items_priority = {**items_priority, **tmp_priority["priority"]}
            priority = tmp_priority
    priority["priority"] = items_priority
    log.debug("THE RESULTING PRIORITY")
    log.debug(pformat(priority))
    return priority


def min_profile_priority(reservables):
    priority = None
    for k, v in reservables.items():
        for subitem in v:
            with app.app_context():
                reservable = r.table("reservables_" + k).get(subitem).run(db.conn)
                if not reservable.get("priority_id") or reservable["priority_id"] == "":
                    priority_id = "default"
                else:
                    priority_id = reservable.get("priority_id")
                priority = (
                    r.table("bookings_priority")
                    .get_all(priority_id, index="rule_id")
                    .filter(  ## exclude "default admins" priority
                        lambda row: (
                            ~row["allowed"]["roles"] == ["admin"]
                            and row["allowed"]["categories"] == False
                            and row["allowed"]["groups"] == False
                            and row["allowed"]["users"] == False
                        )
                    )
                    .min("forbid_time")
                    .run(db.conn)
                )
    return priority


def get_user_default_priority(payload, subitem):
    # Get defaults
    log.debug("GETTING DEFAULT PRIORITY AS NONE DID MATCH")
    with app.app_context():
        rules = list(
            r.table("bookings_priority")
            .get_all("default", index="rule_id")
            .order_by(r.desc("priority"))
            .run(db.conn)
        )
    priority = user_matches_priority_rule(payload, rules)
    if not priority:
        # Should we hardcode a default if the user removed it?
        return {
            "priority": {subitem: 0},
            "forbid_time": 0,
            "max_time": None,
            "max_items": None,
        }
    return {
        "priority": {subitem: priority["priority"]},
        "forbid_time": priority["forbid_time"],
        "max_time": priority["max_time"],
        "max_items": priority["max_items"],
    }


def compute_user_priority(users, rule_id):
    with app.app_context():
        priority = list(
            r.table("bookings_priority").get_all(rule_id, index="rule_id").run(db.conn)
        )
    priority_columns = []
    for p in priority:
        for user in users:
            priority_columns.append(
                {
                    **{
                        "rule_id": rule_id,
                        "priority": p["priority"],
                        "forbid_time": p["forbid_time"],
                        "max_time": p["max_time"],
                        "max_items": p["max_items"],
                    },
                    **user,
                }
            )
    return priority_columns


def user_matches_priority_rule(payload, rules):
    alloweds = [
        ("users", "user"),
        ("groups", "group"),
        ("categories", "category"),
        ("roles", "role"),
    ]

    log.debug("############ USER PRIORITY ###############")
    log.debug(pformat(payload))
    log.debug("##########################################")
    for allowed_item in alloweds:
        log.debug("##### LOOP FOR " + allowed_item[0])
        for rule in rules:
            log.debug(
                "##### CHECKING ITEM ALLOWED "
                + str(allowed_item[0])
                + ": "
                + str(rule["allowed"][allowed_item[0]])
                + " / "
                + str(payload[allowed_item[1] + "_id"])
            )
            if rule["allowed"][allowed_item[0]] is not False:
                log.debug("Rule is not none")
                log.debug(str(not len(rule["allowed"][allowed_item[0]])))
                log.debug(
                    "If "
                    + str(payload[allowed_item[1] + "_id"])
                    + " not in "
                    + str(rule["allowed"][allowed_item[0]])
                    + " ..."
                )
                log.debug(
                    str(
                        payload[allowed_item[1] + "_id"]
                        not in rule["allowed"][allowed_item[0]]
                    )
                )
                if (
                    len(rule["allowed"][allowed_item[0]]) == 0
                    or payload[allowed_item[1] + "_id"]
                    in rule["allowed"][allowed_item[0]]
                ):
                    log.debug("##### -> RULE MATCH!!! Ending priority search.")
                    return rule
            else:
                log.debug("Rule is NONE")
    return False


def most_restrictive_rule(subitem, new_priority, old_priority=None):
    if not old_priority:
        return {
            "priority": {subitem: new_priority["priority"]},
            "forbid_time": new_priority["forbid_time"],
            "max_time": new_priority["max_time"],
            "max_items": new_priority["max_items"],
        }

    return {
        "priority": {**old_priority["priority"], **{subitem: new_priority["priority"]}},
        "forbid_time": min(new_priority["forbid_time"], old_priority["forbid_time"]),
        "max_time": min(new_priority["max_time"], old_priority["max_time"]),
        "max_items": min(new_priority["max_items"], new_priority["max_items"]),
    }


## OVERRIDABLES
def get_overridable_bookings(
    priority, reservables, fromDate, toDate, skip_booking_id=None
):
    bookings = []
    for k, v in reservables.items():
        for subitem in v:
            query = r.table("bookings")
            # This index should be multi I think, then will get the items that have all the v.
            # Now I think it will get all the ones that have any v.
            query = query.get_all([subitem], index="reservables_" + k)
            query = query.filter(
                r.row["start"]
                <= datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            ).filter(
                r.row["end"]
                >= datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            )
            query = query.filter(
                r.row["plans"].contains(
                    lambda plan: plan["priority"] < priority["priority"][subitem]
                )
            )

            with app.app_context():
                bookings += list(query.run(db.conn))
            log.debug(
                "compute get_overridable_bookings for: "
                + subitem
                + " IN INDEX: reservables_"
                + k
                + " IN TABLE: bookings TOTAL: "
                + str(len(bookings))
            )
    total_overridable = 0
    for booking in bookings:
        total_overridable += booking["units"]
    log.debug("TOTAL OVERRIDABLE BOOKINGS: " + str(total_overridable))
    return bookings


def get_nonoverridable_bookings(
    priority, reservables, start, end, skip_booking_id=None
):
    bookings = []
    for k, v in reservables.items():
        for subitem in v:
            query = r.table("bookings")
            # This index should be multi I think, then will get the items that have all the v.
            # Now I think it will get all the ones that have any v.
            query = query.get_all([subitem], index="reservables_" + k)
            query = query.filter(
                r.row["start"]
                <= datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            ).filter(
                r.row["end"]
                >= datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            )
            query = query.filter(
                r.row["plans"].contains(
                    lambda plan: plan["priority"] >= priority["priority"][subitem]
                )
            )

            with app.app_context():
                bookings += list(query.run(db.conn))
            log.debug(
                "compute get_nonoverridable_bookings for: "
                + subitem
                + " IN INDEX: reservables_"
                + k
                + " IN TABLE: bookings TOTAL: "
                + str(len(bookings))
            )
    total_nonoverridable = 0
    for booking in bookings:
        total_nonoverridable += booking["units"]
    log.debug("TOTAL NONOVERRIDABLE BOOKINGS: " + str(total_nonoverridable))
    return bookings


def compute_overridable_bookings(overridable, nonoverridable, plans, units):
    log.debug("NON OVERRIDABLE PLANS: " + str(len(nonoverridable)))
    log.debug("OVERRIDABLE PLANS: " + str(len(overridable)))
    plans = convert_plans_to_portions(plans)
    join_plan_op = lambda x, y: {
        "units": x["units"] - y["units"],
        "id": x["id"] + "/" + y["id"],
        "event_type": "available"
        if x["units"] - (units + y["units"]) > 0
        else "unavailable",
    }

    for interval in overridable:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict(
            {
                i: {
                    "units": interval["units"],
                    "id": interval["id"],
                    "event_type": "available",
                }
            }
        )
        plans = plans.combine(d, how=join_plan_op)

    # There are 3 out of 6 in current plan (-3 nonoverridable)
    # We want to fit 4 that have higher priority (overrridable)
    # Let's think there aren't nonoverridable ones and we want to
    # add 2 but there are 2 overridable already.
    join_plan_op = lambda x, y: {
        "units": x["units"] - y["units"],
        "id": x["id"] + "/" + y["id"],
        "event_type": "unavailable"
        if x["units"] - (units + y["units"]) < 0
        else "overridable"
        if x["units"] - (units + y["units"]) < 0
        else "available",
    }

    for interval in nonoverridable:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict(
            {
                i: {
                    "units": interval["units"],
                    "id": interval["id"],
                    "event_type": "available",
                }
            }
        )
        plans = plans.combine(d, how=join_plan_op)

    items = []
    if len(plans):
        for interval, value in plans.items():
            for atomic in interval:
                items.append((atomic, value))
        items.sort()
    else:
        log.debug("NO PLANS FOUND")

    log.debug("Intervals found:")
    log.debug([{"units": item[1]["units"]} for item in items])
    log.debug("Intervals found with only available units:")
    log.debug(
        [{"units": item[1]["units"]} for item in items if item[1]["units"] >= units]
    )
    return [
        {
            "start": P.to_data(item[0])[0][1],
            "end": P.to_data(item[0])[0][2],
            "units": item[1]["units"],
            "ids": item[1]["id"].split("/"),
            "event_type": item[1]["event_type"],
        }
        for item in items
        if item[1]["units"] >= units
    ]


## PLANS FUNCTIONS
def join_existing_plan_after_new_plan_start(plan):
    new_plan = None
    with app.app_context():
        joined_plan_start = list(
            (
                r.table("resource_planner")
                .get_all(plan["item_id"], index="item_id")
                .filter({"subitem_id": plan["subitem_id"]})
                .filter(r.row["start"] == plan["end"] + timedelta(0, 1))
            ).run(db.conn)
        )
        if len(joined_plan_start):
            r.table("resource_planner").get(joined_plan_start[0]["id"]).update(
                {"start": plan["start"]}
            ).run(db.conn)
            new_plan = joined_plan_start[0]
            ## Missing update scheduler!
            ## There was an scheduler for joined_plan_start[0]["id"] that needs updating date to plan["start"]
    return new_plan


def join_existing_plan_before_new_plan_end(plan):
    new_plan = None
    with app.app_context():
        joined_plan_end = list(
            (
                r.table("resource_planner")
                .get_all(plan["item_id"], index="item_id")
                .filter({"subitem_id": plan["subitem_id"]})
                .filter(r.row["end"] == plan["start"] - timedelta(0, 1))
            ).run(db.conn)
        )
        if len(joined_plan_end):
            r.table("resource_planner").get(joined_plan_end[0]["id"]).update(
                {"end": plan["end"]}
            ).run(db.conn)
            new_plan = joined_plan_end[0]
            ## Missing update scheduler!
            ## There was probably a default plan at end that needs updating date to plan["end"]

    return new_plan


## HELPERS
def convert_plans_to_portions(plans):
    portions = P.IntervalDict()
    for interval in plans:
        portions[P.closed(interval["start"], interval["end"])] = interval
    return portions


def intersect_nonoverridable_with_plan(plan, units, keep_non_overlapped=False):
    log.debug("THE INCOMING UNITS NONOVERRIDABLE: " + str(units))
    join_plan_op = lambda x, y: {
        "units": y["units"] - x["units"],
        "id": y["id"] + "/" + x["id"],
        "event_type": "available"
        if y["units"] - (units + x["units"]) > 0
        else "unavailable",
    }

    output = P.IntervalDict()
    for interval in plan:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict(
            {
                i: {
                    "units": interval["units"],
                    "id": interval["id"],
                    "event_type": "available",
                }
            }
        )
        output = output.combine(d, how=join_plan_op)

    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))
    items.sort()

    if not keep_non_overlapped:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "id": item[1]["id"],
                "event_type": item[1]["event_type"],
            }
            for item in items
            if len(item[1]["id"].split("/")) > 1
        ]
    else:
        return [
            {
                "start": P.to_data(item[0])[0][1],
                "end": P.to_data(item[0])[0][2],
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "event_type": item[1]["event_type"],
            }
            for item in items
        ]
