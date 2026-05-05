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
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pprint import pformat

import portion as P
import pytz
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.bookings import Bookings as BookingsHelpers
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.scheduler import Scheduler as SchedulerHelper
from isardvdi_common.lib.bookings.reservables import Reservables as ReservablesProccess
from isardvdi_common.lib.bookings.reservables_planner_compute import (
    ReservablesPlannerCompute,
)
from isardvdi_common.models.booking import Booking
from isardvdi_common.models.planning import ResourcePlanner
from rethinkdb import r


class ReservablesPlannerProccess(RethinkSharedConnection):

    MIN_AUTOBOOKING_TIME = 30
    MAX_BOOKING_TIME = 12 * 60  # 12h
    ROUND_MINUTES = 5
    reservables = ReservablesProccess()

    @classmethod
    def ceil_dt(cls, dt):
        return dt + (datetime.min.replace(tzinfo=pytz.UTC) - dt) % timedelta(
            minutes=cls.ROUND_MINUTES
        )

    ## Reservables View endpoints
    @classmethod
    def list_item_plans(cls, item_id, start=None, end=None):
        start = start if start else datetime.now(pytz.utc)
        end = end if end else start

        if start > end:
            raise Error(
                "bad_request",
                "Start date must not be later than end date.",
                description_code="invalid_date_range",
            )

        start = start.astimezone(pytz.UTC)
        end = end.astimezone(pytz.UTC)

        return ResourcePlanner.get_plans(item_id, start, end)

    @classmethod
    def list_all_item_plans(cls):
        with cls._rdb_context():
            plans = list(
                r.table("resource_planner")
                .merge(
                    lambda plan: {
                        "item": r.table("gpus")
                        .get(plan["item_id"])
                        .default({"name": "[DELETED]"})["name"]
                    }
                )
                .run(cls._rdb_connection)
            )
        for plan in plans:
            plan["bookings"] = len(cls.get_plan_bookings(plan["id"]))

        return plans

    @classmethod
    def list_subitem_plans(
        cls, item_id, subitem_id, start=None, end=None, getUsername=None
    ):
        query = r.table("resource_planner").get_all(
            [item_id, subitem_id], index="item-subitem"
        )
        if not start:
            start = datetime.now(pytz.utc)
        else:
            start = datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
        if not end:
            end = start
        else:
            end = datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)

        if getUsername:
            query = query.merge(
                lambda p: {"user_name": r.table("users").get(p["user_id"])["username"]}
            )
        with cls._rdb_context():
            data = list(
                query.filter(r.row["start"] <= end)
                .filter(r.row["end"] >= start)
                .run(cls._rdb_connection)
            )
        ## An item/subitem planning should not overlap
        return data

    @classmethod
    def add_plan(
        cls,
        payload,
        data,
    ):
        # Round start/end dates to self.round_minutes
        try:
            start = cls.ceil_dt(data["start"]).astimezone(pytz.UTC)
        except ValueError:
            log.debug(traceback.format_exc())
            raise Error(
                "bad_request",
                "Start date invalid.",
                description_code="invalid_start_date",
            )
        try:
            end = cls.ceil_dt(data["end"]).astimezone(pytz.UTC) - timedelta(0, 1)
        except ValueError:
            raise Error(
                "bad_request", "End date invalid.", description_code="invalid_end_date"
            )

        # Plan data structure
        try:
            plan = {
                "id": str(uuid.uuid4()),
                "item_type": data["item_type"],
                "item_id": data["item_id"],
                "subitem_id": data["subitem_id"],
                "units": cls.reservables.get_subitem_units(
                    data["item_type"], data["item_id"], data["subitem_id"]
                ),
                "start": start,
                "end": end,
                "user_id": payload["user_id"],
                "event_type": "available",
            }
        except Exception:
            raise Error(
                "bad_request",
                "New plan body data incorrect",
                traceback.format_exc(),
                description_code="incorrect_new_plan_body_data",
            )
        ## Get item behaviours
        item_can_overlap = cls.reservables.planning_item_can_overlap(
            data["item_type"], data["item_id"]
        )
        subitem_can_overlap = cls.reservables.planning_subitem_can_overlap(
            data["item_type"], data["item_id"], data["subitem_id"]
        )
        subitem_join_before = cls.reservables.planning_subitem_join_before(
            data["item_type"], data["item_id"], data["subitem_id"]
        )
        subitem_join_after = cls.reservables.planning_subitem_join_after(
            data["item_type"], data["item_id"], data["subitem_id"]
        )
        subitem_shedule = cls.reservables.planning_schedule_subitem(
            data["item_type"], data["item_id"], data["subitem_id"]
        )
        ## Execute item behaviours
        if not item_can_overlap:
            cls.check_plan_item_id_overlapped(plan)
        if not subitem_can_overlap:
            cls.check_plan_subitem_id_overlapped(plan)

        replanned = False
        if subitem_join_before:
            joined_plan = (
                ReservablesPlannerCompute.join_existing_plan_after_new_plan_start(plan)
            )
            if joined_plan:
                print(
                    "Existing plan "
                    + joined_plan["id"]
                    + " moved start time to new plan "
                    + plan["id"]
                )
                if subitem_shedule:
                    cls.reschedule_existing_plan_start(plan, joined_plan)
                replanned = joined_plan["id"]

        if subitem_join_after:
            joined_plan = (
                ReservablesPlannerCompute.join_existing_plan_before_new_plan_end(plan)
            )
            if joined_plan:
                print(
                    "Existing plan "
                    + joined_plan["id"]
                    + " moved end time to new plan "
                    + plan["id"]
                )
                if subitem_shedule:
                    cls.reschedule_existing_plan_end(plan, joined_plan)
                replanned = joined_plan["id"]

        if replanned:
            # It has been already updated at scheduler and db
            return replanned
        else:
            if subitem_shedule:
                cls.new_subitem_schedule(plan)

            if not ResourcePlanner.insert_plan(plan):
                raise Error(
                    "internal_error",
                    "Could not insert plan in database",
                    description_code="unable_to_insert",
                )
            return plan["id"]

    @classmethod
    def update_plan(cls, payload, plan_id, start, end):
        """
        Update an existing plan

        Args:
            payload (dict): User payload from authentication
            plan_id (str): The planning ID to update
            start (datetime): New start datetime for the planning
            end (datetime): New end datetime for the planning
        """
        with cls._rdb_context():
            bookings_in_actual_plan = list(
                r.table("bookings")
                .filter(
                    r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
                )
                .filter(r.row["start"] <= start)
                .filter(r.row["end"] >= end)
                .run(cls._rdb_connection)
            )
        if len(bookings_in_actual_plan):
            with cls._rdb_context():
                bookings_failing_in_new_range = list(
                    r.table("bookings")
                    .filter(
                        r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
                    )
                    .filter(lambda b: (b["start"] < start) | (b["end"] > end))
                    .run(cls._rdb_connection)
                )
            if len(bookings_in_actual_plan) != len(bookings_failing_in_new_range):
                # The difference will imply to remove those bookings
                bookings2remove = [
                    b["id"]
                    for b in bookings_in_actual_plan
                    if b not in bookings_failing_in_new_range
                ]
                with cls._rdb_context():
                    r.table("bookings").get_all(
                        r.args(bookings2remove), index="id"
                    ).delete().run(cls._rdb_connection)
        with cls._rdb_context():
            plan = r.table("resource_planner").get(plan_id).run(cls._rdb_connection)
        cls.add_plan(payload, plan)

    @classmethod
    def delete_plan(cls, plan_id):
        result = ResourcePlanner.delete_plan_by_id(plan_id)
        if not result.get("deleted", 0) > 0:
            raise Error("not_found", "Plan not found. Could not be deleted")

        SchedulerHelper.remove_scheduler_startswith_id(plan_id)

        result = ResourcePlanner.delete_bookings_by_plan_id(plan_id)

        if result.get("changes"):
            booking_ids = [b["old_val"]["id"] for b in result["changes"]]
            for booking_id in booking_ids:
                SchedulerHelper.remove_scheduler_startswith_id(booking_id)

    @classmethod
    def get_plan_bookings(cls, plan_id):
        with cls._rdb_context():
            return list(
                r.table("bookings")
                .filter(
                    r.row["plans"].contains(lambda plan: plan["plan_id"] == plan_id)
                )
                .merge(
                    lambda booking: {
                        "username": r.table("users")
                        .get(booking["user_id"])
                        .default({"username": "[Deleted]"})["username"],
                        "category": r.table("categories")
                        .get(
                            r.table("users")
                            .get(booking["user_id"])
                            .default({"category": "[Deleted]"})["category"]
                        )
                        .default({"name": "[Deleted]"})["name"],
                    }
                )
                .without("reservables", "plans")
                .run(cls._rdb_connection)
            )

    @classmethod
    def check_subitem_current_plan(cls, subitem_id, item_id):
        plans = cls.get_subitems_planning([subitem_id], item_id=item_id, now=True)
        if plans and any(
            booking["start"] <= datetime.now(pytz.utc) <= booking["end"]
            for plan in plans
            for booking in cls.get_plan_bookings(plan["id"])
        ):
            raise Error(
                "bad_request",
                description="There's currently an ongoing booking with this GPU profile",
            )

    @classmethod
    def check_subitem_desktops_and_plannings(cls, reservable_type, item_id, subitem_id):
        data = {
            "last": [],
            "desktops": [],
            "plans": [],
            "bookings": [],
            "deployments": [],
        }
        data["last"].append(
            cls.reservables.check_last_subitem(reservable_type, subitem_id)
        )
        data["desktops"].extend(
            cls.reservables.check_desktops_with_profile(reservable_type, subitem_id)
        )
        data["plans"].extend(
            cls.list_subitem_plans(
                item_id,
                subitem_id,
                start=datetime.fromtimestamp(0, pytz.timezone("UTC")).strftime(
                    "%Y-%m-%dT%H:%M%z"
                ),
                getUsername=True,
            )
        )
        data["deployments"].extend(
            cls.reservables.check_deployments_with_profile(reservable_type, subitem_id)
        )
        for plan in data["plans"]:
            data["bookings"].extend(cls.get_plan_bookings(plan["id"]))

        return data

    @classmethod
    def delete_subitem(cls, item_type, item_id, subitem_id, data=None):
        with cls._rdb_context():
            if not data:
                data = cls.check_subitem_desktops_and_plannings(
                    item_type, item_id, subitem_id
                )
        if True in data["last"]:
            # unassign from desktops
            desktops_ids = (
                [desktop["id"] for desktop in data["desktops"]]
                if data.get("desktops")
                else None
            )
            if desktops_ids:
                cls.reservables.deassign_desktops_with_gpu(
                    item_type, subitem_id, desktops_ids
                )
            # TODO: Test when changing to apiv4
            # unassign from deployments
            deployments_ids = (
                [deployment["id"] for deployment in data["deployments"]]
                if data.get("deployments")
                else None
            )
            if deployments_ids:
                cls.reservables.deassign_deployments_with_gpu(
                    item_type, subitem_id, deployments_ids
                )
            # delete plans and its bookings
            if data.get("plans"):
                for plan in data["plans"]:
                    cls.delete_plan(plan["id"])

    @classmethod
    def delete_item(cls, item_type, item_id, subitems=None, data=None):
        if not subitems:
            with cls._rdb_context():
                subitems = (
                    r.table("gpus")
                    .get(item_id)["profiles_enabled"]
                    .run(cls._rdb_connection)
                )

        for subitem in subitems:
            cls.delete_subitem(item_type, item_id, subitem, data)
            cls.reservables.enable_subitems(item_type, item_id, subitem, False)

        with cls._rdb_context():
            r.table("gpus").get(item_id).delete().run(cls._rdb_connection)

    @classmethod
    def get_item_users(cls, item_type, item_id, items_users_list, subitem, data=None):
        data = (
            data
            if data
            else cls.check_subitem_desktops_and_plannings(item_type, item_id, subitem)
        )
        for key in ["plans", "bookings", "desktops", "deployments"]:
            for item in data.get(key, []):
                try:
                    user_id = item["user_id"]
                except KeyError:
                    user_id = item["user"]
                user_dict = next(
                    (u for u in items_users_list if u["user_id"] == user_id), None
                )
                if not user_dict:
                    user_dict = {
                        "user_id": user_id,
                        "bookings": [],
                        "plans": [],
                        "desktops": [],
                        "deployments": [],
                    }
                    items_users_list.append(user_dict)
                user_dict[key].append(item)
        return items_users_list

    ## Bookings functions
    #######################################################

    @classmethod
    def get_item_availability(
        cls,
        payload,
        item_type,
        item_id,
        fromDate,
        toDate,
        returnUnavailable=False,
        subitems=None,
    ):
        if not subitems:
            subitems, units, item_name = BookingsHelpers._get_reservables(
                item_type, item_id
            )
        else:
            units = 1
        priority = ReservablesPlannerCompute.payload_priority(payload, subitems)
        # {'priority': {'NVIDIA-A40-1Q': 45}, 'forbid_time': 24, 'max_time': 2, 'max_items': 30}
        planning = ReservablesPlannerCompute.booking_provisioning(
            payload, item_type, item_id, subitems, units, priority, fromDate, toDate
        )

        format_planning = []
        for plan in planning:
            if not returnUnavailable and plan["event_type"] == "unavailable":
                continue
            format_planning.append(
                {
                    "start": plan["start"].strftime("%Y-%m-%dT%H:%M%z"),
                    "end": plan["end"].strftime("%Y-%m-%dT%H:%M%z"),
                    "event_type": plan["event_type"],
                    "units": plan["units"],
                }
            )
        return format_planning

    @classmethod
    def existing_booking_update_fits(
        cls, payload, booking, new_start=None, new_end=None
    ):
        # When new_start/new_end are passed, validate the new window;
        # otherwise fall back to the booking's stored dates.
        start = new_start if new_start is not None else booking["start"]
        end = new_end if new_end is not None else booking["end"]

        plans = ReservablesPlannerCompute.booking_provisioning(
            payload,
            booking["item_type"],
            booking["item_id"],
            booking["reservables"],
            booking["units"],
            ReservablesPlannerCompute.payload_priority(payload, booking["reservables"]),
            start,
            end,
            skip_booking_id=booking["id"],
        )
        portion_plans = ReservablesPlannerCompute.convert_plans_to_portions(plans)
        new_booking = P.closed(start, end)
        fits = [p for p in portion_plans if p.contains(new_booking)]
        if len(fits) == 1:
            return True
        if not len(fits):
            return False
        log.error("The booking fits in more than one plan!?!?")
        return False

    @classmethod
    def new_booking_plans(cls, payload, booking):
        subitems = booking["reservables"]
        units = booking["units"]
        priority = ReservablesPlannerCompute.payload_priority(
            payload, booking["reservables"]
        )
        start = booking["start"]
        end = booking["end"]

        plans = {}
        for k, v in subitems.items():
            if not v or not len(v):
                continue
            # Get overlapped and keep non overlapped
            for subitem in v:
                all_plans = ReservablesPlannerCompute.get_subitems_planning([subitem])
                plans[subitem] = ReservablesPlannerCompute.get_same_plans_for_booking(
                    all_plans,
                    subitem,
                    priority["priority"][subitem],
                    start,
                    end,
                    units,
                )
                log.debug(
                    "Plans for " + k + "/" + subitem + ": " + str(len(plans[subitem]))
                )
        if len(plans.keys()) == 0:
            return []
        elif len(plans.keys()) == 1:
            return plans
        else:
            log.error(
                "Trying to book desktop with multiple reservables"
                + str(list(plans.keys()))
                + ". Not implemented"
            )
            return []

    ##### Scheduling
    @classmethod
    def reschedule_existing_plan_start(cls, new_plan, existing_plan):
        # Card will be set to default profile between plans
        # If event is added, at start time an scheduler is added (15/5/2/1 minutes before start as kwargs/plan_id index key)
        # existing_plan start is now new_plan start (moved before)
        # we need to reeschedule plan_id to new start time
        SchedulerHelper.bookings_reschedule_item_id(
            existing_plan["item_id"], existing_plan["start"]
        )

    @classmethod
    def reschedule_existing_plan_end(cls, new_plan, existing_plan):
        # Card will be set to default profile between plans
        # If event is added, at start time an scheduler is added (15/5/2/1 minutes before start as kwargs/plan_id index key)
        # existing_plan end is now new_plan end (moved after)
        # Remove existing default profile scheduler if exists at end for existing plan
        SchedulerHelper.bookings_remove_scheduler_item_id(existing_plan["item_id"])
        # If there is no plan just after new end, schedule default
        with cls._rdb_context():
            joined_plan_end = list(
                (
                    r.table("resource_planner")
                    .get_all(new_plan["item_id"], index="item_id")
                    .filter({"subitem_id": new_plan["subitem_id"]})
                    .filter(r.row["end"] == existing_plan["end"])
                ).run(cls._rdb_connection)
            )
        if not len(joined_plan_end):
            SchedulerHelper.bookings_schedule_subitem(
                new_plan["id"],
                new_plan["item_type"],
                new_plan["item_id"],
                ReservablesProccess.get_default_subitem(
                    new_plan["item_type"], new_plan["item_id"]
                ),
                new_plan["end"],
            )

    @classmethod
    def new_subitem_schedule(cls, plan):
        SchedulerHelper.bookings_schedule_subitem(
            plan["id"],
            plan["item_type"],
            plan["item_id"],
            plan["subitem_id"],
            plan["start"],
        )

    ###### Plan & booking checks
    @classmethod
    def check_plan_item_id_overlapped(cls, plan):
        # We can't overlap in gpu, but we can merge existing plan with new plan if they have the same subitem_id (profile)
        # We will only join if:
        #   - new plan ends just when another plan with same profile starts
        #   . new plan starts just after another plan with same profile ends
        # So, the case where they both overlaps but they have the same subitem_id will be taken as an overlap conflict here now.
        with cls._rdb_context():
            overlaps_start = list(
                (
                    r.table("resource_planner")
                    .get_all(plan["item_id"], index="item_id")
                    .filter(
                        r.row["start"].during(
                            plan["start"],
                            plan["end"],
                        )
                    )
                    .run(cls._rdb_connection)
                )
            )
        with cls._rdb_context():
            overlaps_end = list(
                (
                    r.table("resource_planner")
                    .get_all(plan["item_id"], index="item_id")
                    .filter(
                        r.row["end"].during(
                            plan["start"],
                            plan["end"],
                        )
                    )
                    .run(cls._rdb_connection)
                )
            )
        with cls._rdb_context():
            overlaps_completely = list(
                (
                    r.table("resource_planner")
                    .get_all(plan["item_id"], index="item_id")
                    .filter(
                        (r.row["start"] <= plan["start"])
                        & (r.row["end"] >= plan["end"])
                    )
                    .run(cls._rdb_connection)
                )
            )
        if len(overlaps_start):
            overlaps_start = overlaps_start[0]
            raise Error(
                "conflict",
                "The current item planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps starting time with "
                + overlaps_start["item_id"]
                + " / "
                + overlaps_start["subitem_id"]
                + " plan "
                + overlaps_start["id"]
                + ": ["
                + overlaps_start["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_start["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )
        if len(overlaps_end):
            overlaps_end = overlaps_end[0]
            raise Error(
                "conflict",
                "The current item planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps end time with "
                + overlaps_end["item_id"]
                + " / "
                + overlaps_end["subitem_id"]
                + " plan "
                + overlaps_end["id"]
                + ": ["
                + overlaps_end["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_end["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )
        if len(overlaps_completely):
            overlaps_completely = overlaps_completely[0]
            raise Error(
                "conflict",
                "The current item planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps completely with "
                + overlaps_completely["item_id"]
                + " / "
                + overlaps_completely["subitem_id"]
                + " plan "
                + overlaps_completely["id"]
                + ": ["
                + overlaps_completely["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_completely["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )

    @classmethod
    def check_plan_subitem_id_overlapped(cls, plan):
        # We can't overlap in gpu, but we can merge existing plan with new plan if they have the same subitem_id (profile)
        # We will only join if:
        #   - new plan ends just when another plan with same profile starts
        #   . new plan starts just after another plan with same profile ends
        # So, the case where they both overlaps but they have the same subitem_id will be taken as an overlap conflict here now.
        with cls._rdb_context():
            overlaps_start = list(
                (
                    r.table("resource_planner")
                    .get_all(
                        [plan["item_type"], plan["item_id"], plan["subitem_id"]],
                        index="type-item-subitem",
                    )
                    .filter(
                        r.row["start"].during(
                            plan["start"],
                            plan["end"],
                        )
                    )
                    .run(cls._rdb_connection)
                )
            )
        with cls._rdb_context():
            overlaps_end = list(
                (
                    r.table("resource_planner")
                    .get_all(
                        [plan["item_type"], plan["item_id"], plan["subitem_id"]],
                        index="type-item-subitem",
                    )
                    .filter(
                        r.row["end"].during(
                            plan["start"],
                            plan["end"],
                        )
                    )
                    .run(cls._rdb_connection)
                )
            )
        with cls._rdb_context():
            overlaps_completely = list(
                (
                    r.table("resource_planner")
                    .get_all(
                        [plan["item_type"], plan["item_id"], plan["subitem_id"]],
                        index="type-item-subitem",
                    )
                    .filter(
                        (r.row["start"] <= plan["start"])
                        & (r.row["end"] >= plan["end"])
                    )
                    .run(cls._rdb_connection)
                )
            )
        if len(overlaps_start):
            overlaps_start = overlaps_start[0]
            raise Error(
                "conflict",
                "The current subitem planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps starting time with "
                + overlaps_start["item_id"]
                + " / "
                + overlaps_start["subitem_id"]
                + " plan "
                + overlaps_start["id"]
                + ": ["
                + overlaps_start["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_start["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )
        if len(overlaps_end):
            overlaps_end = overlaps_end[0]
            raise Error(
                "conflict",
                "The current subitem planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps end time with "
                + overlaps_end["item_id"]
                + " / "
                + overlaps_end["subitem_id"]
                + " plan "
                + overlaps_end["id"]
                + ": ["
                + overlaps_end["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_end["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )
        if len(overlaps_completely):
            overlaps_completely = overlaps_completely[0]
            raise Error(
                "conflict",
                "The current subitem planning for "
                + plan["item_id"]
                + " / "
                + plan["subitem_id"]
                + " ["
                + plan["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + plan["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "] overlaps completely with "
                + overlaps_completely["item_id"]
                + " / "
                + overlaps_completely["subitem_id"]
                + " plan "
                + overlaps_completely["id"]
                + ": ["
                + overlaps_completely["start"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "/"
                + overlaps_completely["end"].strftime("%Y-%m-%dT%H:%M:%S%z")
                + "]",
            )

    @classmethod
    def is_any_plan_item_id_overlapped(cls):
        conflicts = {}
        with cls._rdb_context():
            plans = r.table("resource_planner").run(cls._rdb_connection)
        for plan in plans:
            if not conflicts.get(plan["item_id"]):
                conflicts[plan["item_id"]] = {"start": [], "end": []}
            with cls._rdb_context():
                start = list(
                    (
                        r.table("resource_planner")
                        .get_all(plan["item_id"], index="item_id")
                        .filter(lambda iplan: r.not_(iplan["id"] == plan["id"]))
                        .filter(
                            r.row["start"].during(
                                plan["start"],
                                plan["end"],
                            )
                        )
                        .run(cls._rdb_connection)
                    )
                )
            with cls._rdb_context():
                end = list(
                    (
                        r.table("resource_planner")
                        .get_all(plan["item_id"], index="item_id")
                        .filter(
                            r.row["end"].during(
                                plan["start"],
                                plan["end"],
                            )
                        )
                        .run(cls._rdb_connection)
                    )
                )
            if len(start):
                log.debug("------------------- START CONFLICTS")
                log.debug(pformat(plan))
                log.debug(pformat(start))
            if len(end):
                log.debug("------------------- END CONFLICTS")
                log.debug(pformat(plan))
                log.debug(pformat(end))

        return conflicts

    # TODO: Evalute moving to Reservables class? (Currently not done due circular import)
    @classmethod
    def get_available_reservables(cls, payload):
        # Get all users reservables
        allowed_reservables = {
            "vgpus": Alloweds.get_items_allowed(
                payload,
                "reservables_vgpus",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
            )
        }
        available = []
        fromDate = datetime.now(timezone.utc)
        toDate = fromDate + timedelta(minutes=cls.MAX_BOOKING_TIME)
        fromDate = fromDate.strftime("%Y-%m-%dT%H:%M%z")
        toDate = toDate.strftime("%Y-%m-%dT%H:%M%z")
        for k, v in allowed_reservables.items():
            for reservable in v:
                priority = ReservablesPlannerCompute.payload_priority(
                    payload, {"vgpus": [reservable["id"]]}
                )
                # Check if the reservable is currently planned
                current_plan = ReservablesPlannerProccess.get_item_availability(
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

                if max_booking_time >= cls.MIN_AUTOBOOKING_TIME:
                    max_booking_time = min(max_booking_time, cls.MAX_BOOKING_TIME)

                    max_booking_date = datetime.strftime(
                        datetime.now(timezone.utc)
                        + timedelta(minutes=max_booking_time),
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

        if not len(available):
            raise Error(
                "precondition_required",
                "There's no gpu profile available to start the desktop now",
                description_code="no_available_profile",
            )

        return available
