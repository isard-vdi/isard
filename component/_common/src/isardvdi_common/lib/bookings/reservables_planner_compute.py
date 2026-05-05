#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging as log
from datetime import datetime, timedelta
from pprint import pformat

import portion as P
import pytz
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


def _sorted_atomic_items(interval_dict):
    """Extract and sort atomic intervals from a P.IntervalDict.

    Each key in an IntervalDict can be a compound interval
    (e.g. ``I.closed(1, 3) | I.closed(5, 7)``); this helper splits
    every compound key into its atomic components and returns the
    full list of ``(atomic_interval, value)`` pairs sorted by lower
    bound. Callers (e.g. ``ReservablesPlannerCompute.intersect_*``)
    then index ``item[0].lower`` / ``item[0].upper`` and
    ``item[1]["units"]`` / ``item[1]["id"]``.
    """
    items = []
    for interval, value in interval_dict.items():
        # portion.Interval is iterable — iterating yields its atomic
        # (connected, non-empty) components.
        for atomic in interval:
            items.append((atomic, value))
    items.sort(key=lambda pair: pair[0].lower)
    return items


class ReservablesPlannerCompute(RethinkSharedConnection):

    ## BOOKING PROVISIONING
    @classmethod
    def booking_provisioning(
        cls,
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
                all_plans = cls.get_subitems_planning([subitem])
                resource_planner[subitem] = cls.intersect_same_subitem_plan(
                    all_plans, subitem
                )
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
            resource_planner = cls.intersect_different_subitem_plan(all_plans)
        else:
            resource_planner = resource_planner[list(resource_planner.keys())[0]]

        # Get overridable and nonoverridable bookings
        overridable = cls.get_overridable_bookings(
            priority, subitems, fromDate, toDate, skip_booking_id
        )
        nonoverridable = cls.get_nonoverridable_bookings(
            priority, subitems, fromDate, toDate, skip_booking_id
        )
        # Substract both from resource_planner
        resource_planner = cls.compute_overridable_bookings(
            overridable, nonoverridable, resource_planner, units
        )
        # Remove existing bookings for this item from resource_planner
        if item_id and item_type:
            resource_planner = cls.remove_existing_item_bookings(
                resource_planner, item_type, item_id, fromDate, toDate
            )
        # This will join consecutive plans
        # When debugging it is better to show them splitted (do not join)
        # Removed because it would cause problems with the start now feature
        # if not os.environ.get("LOG_LEVEL") == "DEBUG":
        resource_planner = cls.join_consecutive_plans(resource_planner)
        return resource_planner

    ## RESOURCE PLANNER INTERSECTIONS
    @classmethod
    def get_subitems_planning(
        cls, subitems, start=None, end=None, item_id=None, now=None
    ):
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

        with cls._rdb_context():
            plans = list(query.run(cls._rdb_connection))
        if not item_id:
            log.debug("FOUND " + str(len(plans)) + " FOR ALL PROFILES " + str(subitems))
        return plans

    @classmethod
    def remove_existing_item_bookings(
        cls, plans, item_type, item_id, start=None, end=None
    ):
        ## Wait!! We should remove all items plannings! not only the plans in the
        ## current reservable the item has now, as it can't be reserved with two
        ## different reservables at the same time
        if not start:
            start = datetime.now(pytz.utc)

        query = r.table("bookings").get_all(item_id, index="item_id")
        if start and end:
            query = query.filter(
                lambda booking: (booking["start"] < end) & (booking["end"] > start)
            )

        with cls._rdb_context():
            bookings = list(query.run(cls._rdb_connection))

        log.debug("FOUND " + str(len(plans)) + " existing plans_intervals")
        log.debug(
            "FOUND "
            + str(len(bookings))
            + " existing bookings to be removed from planning"
        )
        plans_intervals = cls.convert_plans_to_portions(plans)

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

        items = _sorted_atomic_items(plans_intervals)

        # When the "start" key it's not there it will be because the interval
        # is not available, but because the item is reserved in another reservable item
        return [item[1] for item in items if "start" in item[1].keys()]

    @classmethod
    def intersect_same_subitem_plan(cls, plan, plan_name, keep_non_overlapped=True):
        join_plan_op = lambda x, y: {
            "units": x["units"] + y["units"],
            "id": x["id"] + "/" + y["id"],
        }

        output = P.IntervalDict()
        for interval in plan:
            i = P.closed(interval["start"], interval["end"])
            d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
            output = output.combine(d, how=join_plan_op)

        items = _sorted_atomic_items(output)

        if not keep_non_overlapped:
            return [
                {
                    "start": item[0].lower,
                    "end": item[0].upper,
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
                    "start": item[0].lower,
                    "end": item[0].upper,
                    "units": item[1]["units"],
                    "ids": item[1]["id"].split("/"),
                    "id": plan_name,
                    "event_type": "available",
                }
                for item in items
            ]

    @classmethod
    def count_non_overridable_bookings(cls, plan_id, subitem_id, priority, start, end):
        query = r.table("bookings")
        query = query.filter(r.row["reservables"]["vgpus"].contains(subitem_id))
        query = query.filter(r.row["start"] <= end).filter(r.row["end"] >= start)
        query = query.filter(
            r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
        )
        query = query.filter(
            r.row["plans"].contains(lambda plan: plan["priority"] <= priority)
        )
        with cls._rdb_context():
            bookings = list(query.run(cls._rdb_connection))
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

        items = _sorted_atomic_items(output)
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

        max_units = max((item[1]["units_booked"] for item in items), default=0)
        log.debug(
            "-----------> Found "
            + str(max_units)
            + " max units already booked in interval"
        )
        return max_units

    @classmethod
    def get_same_plans_for_booking(
        cls,
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
                avail_in_plan = plan["units"] - cls.count_non_overridable_bookings(
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
                    - cls.count_non_overridable_bookings(
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

    @classmethod
    def get_different_plans_for_booking(cls, plans):
        join_plan_op = lambda x, y: {
            "units": min(x["units"], y["units"]),
            "id": x["id"] + "/" + y["id"],
        }

        output = P.IntervalDict()
        for interval in plans:
            i = P.closed(interval["start"], interval["end"])
            d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
            output = output.combine(d, how=join_plan_op)

        items = _sorted_atomic_items(output)

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
                "start": item[0].lower,
                "end": item[0].upper,
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "id": item[1]["id"],
                "event_type": "available",
            }
            for item in items
            if len(item[1]["id"].split("/")) > 1
        ]

    @classmethod
    def join_consecutive_plans(cls, plan):
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

        items = _sorted_atomic_items(output)

        return [
            {
                "start": item[0].lower,
                "end": item[0].upper,
                "units": "Enough",
                "ids": item[1]["id"].split("/"),
                "id": item[1]["id"],
                "event_type": "available",
            }
            for item in items
        ]

    @classmethod
    def intersect_different_subitem_plan(cls, plan, keep_non_overlapped=False):
        join_plan_op = lambda x, y: {
            "units": min(x["units"], y["units"]),
            "id": x["id"] + "/" + y["id"],
        }

        output = P.IntervalDict()
        for interval in plan:
            i = P.closed(interval["start"], interval["end"])
            d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
            output = output.combine(d, how=join_plan_op)

        items = _sorted_atomic_items(output)

        if not keep_non_overlapped:
            return [
                {
                    "start": item[0].lower,
                    "end": item[0].upper,
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
                    "start": item[0].lower,
                    "end": item[0].upper,
                    "units": item[1]["units"],
                    "ids": item[1]["id"].split("/"),
                    "event_type": "available",
                }
                for item in items
            ]

    ## BOOKINGS PRIORITY RULES
    @classmethod
    def payload_priority(cls, payload, reservables):
        log.debug("USER PAYLOAD")
        log.debug(payload)
        priority = None
        items_priority = {}
        for k, v in reservables.items():
            for subitem in v:
                with cls._rdb_context():
                    reservable = (
                        r.table("reservables_" + k)
                        .get(subitem)
                        .run(cls._rdb_connection)
                    )
                if not reservable.get("priority_id") or reservable["priority_id"] == "":
                    priority_id = "default"
                else:
                    priority_id = reservable.get("priority_id")
                with cls._rdb_context():
                    rules = list(
                        r.table("bookings_priority")
                        .get_all(priority_id, index="rule_id")
                        .order_by(r.desc("priority"))
                        .run(cls._rdb_connection)
                    )
                new_priority = cls.user_matches_priority_rule(payload, rules)
                if not new_priority:
                    new_priority = cls.get_user_default_priority(payload, subitem)
                tmp_priority = cls.most_restrictive_rule(
                    subitem, new_priority, priority
                )
                items_priority = {**items_priority, **tmp_priority["priority"]}
                priority = tmp_priority
        priority["priority"] = items_priority
        log.debug("THE RESULTING PRIORITY")
        log.debug(pformat(priority))
        return priority

    @classmethod
    def min_profile_priority(cls, reservables):
        priority = None
        for k, v in reservables.items():
            for subitem in v:
                with cls._rdb_context():
                    reservable = (
                        r.table("reservables_" + k)
                        .get(subitem)
                        .run(cls._rdb_connection)
                    )
                if not reservable.get("priority_id") or reservable["priority_id"] == "":
                    priority_id = "default"
                else:
                    priority_id = reservable.get("priority_id")
                # Exclude default admins priority
                with cls._rdb_context():
                    priority = (
                        r.table("bookings_priority")
                        .get_all(priority_id, index="rule_id")
                        .filter(lambda row: row["id"] != "default admins")
                        .filter(lambda row: row["max_time"] != 0)
                        .min("forbid_time")
                        .run(cls._rdb_connection)
                    )
        return priority

    @classmethod
    def get_user_default_priority(cls, payload, subitem):
        # Get defaults
        log.debug("GETTING DEFAULT PRIORITY AS NONE DID MATCH")
        with cls._rdb_context():
            rules = list(
                r.table("bookings_priority")
                .get_all("default", index="rule_id")
                .order_by(r.desc("priority"))
                .run(cls._rdb_connection)
            )
        priority = cls.user_matches_priority_rule(payload, rules)
        if not priority:
            # Should we hardcode a default if the user removed it?
            return {
                "priority": 0,
                "forbid_time": 0,
                "max_time": None,
                "max_items": None,
            }
        return {
            "priority": priority["priority"],
            "forbid_time": priority["forbid_time"],
            "max_time": priority["max_time"],
            "max_items": priority["max_items"],
        }

    @classmethod
    def compute_user_priority(cls, users, rule_id):
        with cls._rdb_context():
            priority = list(
                r.table("bookings_priority")
                .get_all(rule_id, index="rule_id")
                .run(cls._rdb_connection)
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

    @classmethod
    def user_matches_priority_rule(cls, payload, rules):
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

    @classmethod
    def most_restrictive_rule(cls, subitem, new_priority, old_priority=None):
        if not old_priority:
            return {
                "priority": {subitem: new_priority["priority"]},
                "forbid_time": new_priority["forbid_time"],
                "max_time": new_priority["max_time"],
                "max_items": new_priority["max_items"],
            }

        return {
            "priority": {
                **old_priority["priority"],
                **{subitem: new_priority["priority"]},
            },
            "forbid_time": min(
                new_priority["forbid_time"], old_priority["forbid_time"]
            ),
            "max_time": min(new_priority["max_time"], old_priority["max_time"]),
            "max_items": min(new_priority["max_items"], old_priority["max_items"]),
        }

    ## OVERRIDABLES
    @classmethod
    def get_overridable_bookings(
        cls, priority, reservables, fromDate, toDate, skip_booking_id=None
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
                    <= datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                ).filter(
                    r.row["end"]
                    >= datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                if skip_booking_id:
                    query = query.filter(
                        lambda booking: booking["id"] != skip_booking_id
                    )
                query = query.filter(
                    r.row["plans"].contains(
                        lambda plan: plan["priority"] < priority["priority"][subitem]
                    )
                )

                with cls._rdb_context():
                    bookings += list(query.run(cls._rdb_connection))
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

    @classmethod
    def get_nonoverridable_bookings(
        cls, priority, reservables, start, end, skip_booking_id=None
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
                if skip_booking_id:
                    query = query.filter(
                        lambda booking: booking["id"] != skip_booking_id
                    )
                query = query.filter(
                    r.row["plans"].contains(
                        lambda plan: plan["priority"] >= priority["priority"][subitem]
                    )
                )

                with cls._rdb_context():
                    bookings += list(query.run(cls._rdb_connection))
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

    @classmethod
    def compute_overridable_bookings(cls, overridable, nonoverridable, plans, units):
        log.debug("NON OVERRIDABLE PLANS: " + str(len(nonoverridable)))
        log.debug("OVERRIDABLE PLANS: " + str(len(overridable)))
        plans = cls.convert_plans_to_portions(plans)
        join_plan_op = lambda x, y: {
            "units": x["units"] - y["units"],
            "id": x["id"] + "/" + y["id"],
            "event_type": (
                "unavailable"
                if x["units"] - y["units"] <= 0
                else "overridable" if x["units"] - y["units"] < units else "available"
            ),
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
            "event_type": (
                "unavailable"
                if x["units"] - (units + y["units"]) < 0
                else (
                    "overridable"
                    if x["units"] - (units + y["units"]) < 0
                    else "available"
                )
            ),
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
                "start": item[0].lower,
                "end": item[0].upper,
                "units": item[1]["units"],
                "ids": item[1]["id"].split("/"),
                "event_type": item[1]["event_type"],
            }
            for item in items
            if item[1]["units"] >= units
        ]

    ## PLANS FUNCTIONS
    @classmethod
    def join_existing_plan_after_new_plan_start(cls, plan):
        new_plan = None
        with cls._rdb_context():
            joined_plan_start = list(
                (
                    r.table("resource_planner")
                    .get_all(plan["item_id"], index="item_id")
                    .filter({"subitem_id": plan["subitem_id"]})
                    .filter(r.row["start"] == plan["end"] + timedelta(0, 1))
                ).run(cls._rdb_connection)
            )
        if len(joined_plan_start):
            with cls._rdb_context():
                r.table("resource_planner").get(joined_plan_start[0]["id"]).update(
                    {"start": plan["start"]}
                ).run(cls._rdb_connection)
            new_plan = joined_plan_start[0]
            ## Missing update scheduler!
            ## There was an scheduler for joined_plan_start[0]["id"] that needs updating date to plan["start"]
        return new_plan

    @classmethod
    def join_existing_plan_before_new_plan_end(cls, plan):
        new_plan = None
        with cls._rdb_context():
            joined_plan_end = list(
                (
                    r.table("resource_planner")
                    .get_all(plan["item_id"], index="item_id")
                    .filter({"subitem_id": plan["subitem_id"]})
                    .filter(r.row["end"] == plan["start"] - timedelta(0, 1))
                ).run(cls._rdb_connection)
            )
        if len(joined_plan_end):
            with cls._rdb_context():
                r.table("resource_planner").get(joined_plan_end[0]["id"]).update(
                    {"end": plan["end"]}
                ).run(cls._rdb_connection)
            new_plan = joined_plan_end[0]
            ## Missing update scheduler!
            ## There was probably a default plan at end that needs updating date to plan["end"]

        return new_plan

    ## HELPERS
    @classmethod
    def convert_plans_to_portions(cls, plans):
        portions = P.IntervalDict()
        for interval in plans:
            portions[P.closed(interval["start"], interval["end"])] = interval
        return portions

    def intersect_nonoverridable_with_plan(cls, plan, units, keep_non_overlapped=False):
        log.debug("THE INCOMING UNITS NONOVERRIDABLE: " + str(units))
        join_plan_op = lambda x, y: {
            "units": y["units"] - x["units"],
            "id": y["id"] + "/" + x["id"],
            "event_type": (
                "available" if y["units"] - (units + x["units"]) > 0 else "unavailable"
            ),
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

        items = _sorted_atomic_items(output)

        if not keep_non_overlapped:
            return [
                {
                    "start": item[0].lower,
                    "end": item[0].upper,
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
                    "start": item[0].lower,
                    "end": item[0].upper,
                    "units": item[1]["units"],
                    "ids": item[1]["id"].split("/"),
                    "event_type": item[1]["event_type"],
                }
                for item in items
            ]
