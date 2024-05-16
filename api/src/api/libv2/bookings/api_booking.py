#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback
from datetime import datetime, timedelta, timezone

import portion as P
import pytz
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import uuid

from ..api_scheduler import Scheduler
from ..helpers import _check, _get_reservables
from .api_reservables import Reservables
from .api_reservables_planner import ReservablesPlanner
from .api_reservables_planner_compute import (
    compute_user_priority,
    min_profile_priority,
    payload_priority,
)

scheduler = Scheduler()


def is_future(event):
    return True if event["start"] > datetime.now(pytz.utc) else False


class Bookings:
    def __init__(self):
        self.reservables = Reservables()
        self.reservables_planner = ReservablesPlanner()
        self.resources_scheduler = Scheduler()

    def get_all(self):
        with app.app_context():
            return list(
                r.table("bookings")
                .merge(
                    lambda booking: {
                        "username": r.table("users").get(booking["user_id"])[
                            "username"
                        ],
                        "category": r.table("categories").get(
                            r.table("users").get(booking["user_id"])["category"]
                        )["name"],
                    }
                )
                .run(db.conn)
            )

    def get_user_priority(self, payload, item_type, item_id):
        reservables, units, item_name = _get_reservables(item_type, item_id)
        return payload_priority(payload, reservables)

    def get_min_profile_priority(self, item_type, item_id):
        reservables, units, item_name = _get_reservables(item_type, item_id)
        return min_profile_priority(reservables)

    def get_users_priorities(self, rule_id):
        with app.app_context():
            priority = list(
                r.table("bookings_priority")
                .get_all(rule_id, index="rule_id")
                .run(db.conn)
            )
        users = {}
        kind = ""
        for p in priority:
            allowed = p["allowed"]
            for key, value in allowed.items():
                if value == False:
                    continue
                if len(value) > 0:
                    if key == "users":
                        for item in value:
                            with app.app_context():
                                user = (
                                    r.table("users")
                                    .get(item)
                                    .pluck(
                                        "id", "role", "category", "username", "group"
                                    )
                                    .run(db.conn)
                                )
                                users.append(user)
                            if len(users) == 2:
                                return compute_user_priority(users, rule_id)
                    if key == "categories":
                        kind == "category"
                    if key == "groups":
                        kind == "group"
                    if key == "roles":
                        kind = "role"
                    with app.app_context():
                        users = list(
                            r.table("users")
                            .filter({kind: value[0]})
                            .sample(2)
                            .pluck("id", "role", "category", "username", "group")
                            .run(db.conn)
                        )
                    return compute_user_priority(users, rule_id)

                else:
                    with app.app_context():
                        users = list(
                            r.table("users")
                            .sample(2)
                            .pluck("id", "role", "category", "username", "group")
                            .run(db.conn)
                        )
                    return compute_user_priority(users, rule_id)

    def delete_users_priority(self, priority_id):
        with app.app_context():
            r.table("bookings_priority").get(priority_id).delete().run(db.conn)

    def list_priority_rules(self):
        return list(
            r.table("bookings_priority").pluck("rule_id").distinct().run(db.conn)
        )

    def get_minumum_forbid_time(self):
        return list(r.table("bookings_priority")["forbid_time"].min())

    def add(
        self,
        payload,
        start,
        end,
        item_type,  # desktop/deployment
        item_id,  # id
        title=None,
        now=False,
    ):
        # CHECK: There is still empty room for this desktop resources.

        reservables, units, item_name = _get_reservables(item_type, item_id)

        # Has enough quota to do another booking?
        priorities = self.get_user_priority(payload, item_type, item_id)
        if priorities["max_items"] <= self.get_total_user_bookings_count(
            payload["user_id"]
        ):
            raise Error(
                "precondition_required",
                "The user " + payload["user_id"] + " has reached max_items bookings.",
                description_code="booking_max_items_exceeded",
            )

        booking = {
            "id": str(uuid.uuid4()),
            "item_id": item_id,
            "item_type": item_type,
            "units": units,
            "reservables": reservables,
            "start": datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC),
            "end": datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC),
            "title": title if title else item_name,
            "user_id": payload["user_id"],
        }

        # Overlap this plan with existing ones and check which ones have room from the new booking
        plans = self.reservables_planner.new_booking_plans(payload, booking)
        ## TODO: We should check if all the keys have an empty list, not only the first one!
        if not len(plans[list(plans.keys())[0]]):
            raise Error(
                "conflict",
                "The booking does not fit in requested date",
                description_code="booking_does_not_fit_date",
            )

        # We are adding all the plans for each item.
        # TODO: Check if we really need to append them. I think it's not checked/used anywhere
        priorities = priorities["priority"]
        new_planning = []
        for k, v in plans.items():
            for item in v:
                new_planning.append(
                    {
                        "plan_id": item["id"],
                        "item_id": item["item_id"],
                        "subitem_id": item["subitem_id"],
                        "priority": priorities[item["subitem_id"]],
                        "units_booked": item["units_booked"],
                    }
                )

        booking["plans"] = new_planning
        with app.app_context():
            if not _check(r.table("bookings").insert(booking).run(db.conn), "inserted"):
                raise Error(
                    "internal_server",
                    "Unable to insert booking in database.",
                    description_code="unable_to_insert",
                )
        if now:
            if item_type == "desktop":
                r.table("domains").get(item_id).update(
                    {"booking_id": booking["id"]}
                ).run(db.conn)
            else:
                raise Error(
                    "bad_request", "Can't set a booking starting now in a deployment"
                )
        self.resources_scheduler.bookings_schedule(
            booking["id"], item_type, item_id, booking["start"], booking["end"]
        )
        return {
            **booking,
            **{"editable": is_future(booking), "start": start, "end": end},
        }

    def update(
        self,
        booking_id,
        title,
        start,
        end,
    ):
        with app.app_context():
            booking = r.table("bookings").get(booking_id).run(db.conn)
        if not self.reservables_planner.existing_booking_update_fits(payload, booking):
            raise Error(
                "conflict",
                "The booking update does not fit in requested date",
                description_code="booking_does_not_fit_date",
            )

        if not _check(
            r.table("bookings")
            .get(booking_id)
            .update(
                {
                    "title": title,
                    "start": datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    ),
                    "end": datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    ),
                }
            )
            .run(db.conn),
            "replaced",
        ):
            raise UpdateFailed

    def delete(
        self,
        booking_id,
    ):
        with app.app_context():
            booking = r.table("bookings").get(booking_id).run(db.conn)
        if booking == None:
            raise Error(
                "not_found",
                "Booking not found",
                traceback.format_stack(),
                description_code="not_found",
            )
        if booking.get("start") <= datetime.now(pytz.utc) and booking.get(
            "end"
        ) >= datetime.now(pytz.utc):
            if booking.get("item_type") == "desktop":
                desktop = r.table("domains").get(booking.get("item_id")).run(db.conn)
                if desktop.get("status") not in ["Stopped", "Failed"]:
                    raise Error(
                        "precondition_required",
                        "In order to remove a booking in progress its desktop must be stopped",
                        traceback.format_stack(),
                        description_code="booking_desktop_delete_stop",
                    )
                else:
                    scheduler.remove_desktop_timeouts(booking.get("item_id"))
            elif booking.get("item_type") == "deployment":
                desktops = (
                    r.table("domains")
                    .get_all(booking.get("item_id"), index="tag")
                    .filter(
                        lambda desktop: r.not_(
                            r.expr(["Stopped", "Failed"]).contains(desktop["status"])
                        )
                    )
                    .count()
                    .run(db.conn)
                )
                if desktops:
                    raise Error(
                        "precondition_required",
                        "In order to remove a booking in progress the deployment desktops must be stopped",
                        traceback.format_stack(),
                        description_code="booking_deployment_delete_stop",
                    )

        if not _check(
            r.table("bookings").get(booking_id).delete().run(db.conn), "deleted"
        ):
            raise Error(
                "internal_server", "Unable to delete booking", traceback.format_stack()
            )

        self.resources_scheduler.remove_scheduler_startswith_id(booking_id)

    def get_item_bookings(
        self,
        payload,
        fromDate,
        toDate,
        item_type,
        item_id,
        returnType="all",
        returnUnavailable=None,
    ):
        with app.app_context():
            bookings = list(
                r.table("bookings")
                .get_all(item_id, index="item_id")
                .filter(
                    r.row["start"]
                    <= datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .filter(
                    r.row["end"]
                    >= datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .run(db.conn)
            )

        reservable_plan = self.reservables_planner.get_item_availability(
            payload, item_type, item_id, fromDate, toDate, returnUnavailable
        )
        if not returnType or returnType == "all":
            return [
                {
                    **booking,
                    **{
                        "editable": is_future(booking),
                        "event_type": "event",
                        "start": booking["start"].strftime("%Y-%m-%dT%H:%M%z"),
                        "end": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                    },
                }
                for booking in bookings
            ] + reservable_plan
        if returnType == "event":
            return [
                {
                    **booking,
                    **{
                        "editable": is_future(booking),
                        "event_type": "event",
                        "start": booking["start"].strftime("%Y-%m-%dT%H:%M%z"),
                        "end": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                    },
                }
                for booking in bookings
            ]
        if returnType == "availability":
            return reservable_plan

    def delete_item_bookings(self, item_type, item_id):
        with app.app_context():
            if not _check(
                r.table("bookings")
                .get_all([item_type, item_id], index="item_type-id")
                .delete()
                .run(db.conn),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Unable to delete item bookings",
                    traceback.format_stack(),
                )
        self.resources_scheduler.bookings_remove_scheduled_jobs(item_id)

    def get_user_bookings(self, fromDate, toDate, user_id):
        with app.app_context():
            bookings = list(
                r.table("bookings")
                .get_all(["desktop", user_id], index="item_type_user")
                .filter(
                    r.row["start"]
                    <= datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .filter(
                    r.row["end"]
                    >= datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .run(db.conn)
            )

        with app.app_context():
            deployment_desktops_tags = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .filter(lambda desktop: r.not_(desktop["tag"] == False))["tag"]
                .run(db.conn)
            )
        with app.app_context():
            bookings.extend(
                r.table("bookings")
                .get_all(
                    ["deployment", r.args(deployment_desktops_tags)],
                    index="item_type-id",
                )
                .filter(
                    r.row["start"]
                    <= datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .filter(
                    r.row["end"]
                    >= datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                        pytz.UTC
                    )
                )
                .run(db.conn)
            )
        return [
            {
                **booking,
                **{
                    "editable": is_future(booking),
                    "event_type": "event",
                    "start": booking["start"].strftime("%Y-%m-%dT%H:%M%z"),
                    "end": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                },
            }
            for booking in bookings
        ]

    def get_total_user_bookings_count(self, user_id):
        start = datetime.now(pytz.utc)
        # Count the bookings the user already has
        with app.app_context():
            return (
                r.table("bookings")
                .get_all(user_id, index="user_id")
                .filter(r.row["start"] > start)
                .count()
                .run(db.conn)
            )

    def get_booking_plans(self, booking_id):
        with app.app_context():
            plan_ids = [
                plan["plan_id"]
                for plan in list(
                    r.table("bookings").get(booking_id)["plans"].run(db.conn)
                )
            ]
            app.logger.error(plan_ids)
            return list(
                r.db("isard")
                .table("resource_planner")
                .get_all(*plan_ids)
                .merge(
                    lambda plan: {"item": r.table("gpus").get(plan["item_id"])["name"]}
                )
                .run(db.conn)
            )

    """
      Orchestrator provisioning
    """

    def get_booking_profile_count_within_one_hour(self):
        with app.app_context():
            forecast_0 = list(
                r.table("bookings")
                .filter(r.row["start"] <= r.now())
                .filter(r.row["end"] >= r.now())
                .merge({"profile": r.row["reservables"]["vgpus"][0]})
                .pluck(
                    "id",
                    "units",
                    "profile",
                    "start",
                    "end",
                )
                .group("profile")
                .ungroup()
                .run(db.conn)
            )

            forecast_30 = list(
                r.table("bookings")
                .filter(r.row["start"] <= r.now().add(60 * 30))
                .filter(r.row["end"] >= r.now())
                .merge({"profile": r.row["reservables"]["vgpus"][0]})
                .pluck(
                    "id",
                    "units",
                    "profile",
                    "start",
                    "end",
                )
                .group("profile")
                .ungroup()
                .run(db.conn)
            )

            forecast_60 = list(
                r.table("bookings")
                .filter(r.row["start"] <= r.now().add(60 * 60))
                .filter(r.row["end"] >= r.now())
                .merge({"profile": r.row["reservables"]["vgpus"][0]})
                .pluck(
                    "id",
                    "units",
                    "profile",
                    "start",
                    "end",
                )
                .group("profile")
                .ungroup()
                .run(db.conn)
            )

        # We get the full list of profiles from the largest forecast
        profiles = [p["group"] for p in forecast_60]

        profiles_forecast = []
        for profile in profiles:
            forecast_0_plans = [
                fp["reduction"] for fp in forecast_0 if fp["group"] == profile
            ]
            forecast_0_plans = forecast_0_plans[0] if forecast_0_plans else []
            forecast_30_plans = [
                fp["reduction"] for fp in forecast_30 if fp["group"] == profile
            ]
            forecast_30_plans = forecast_30_plans[0] if forecast_30_plans else []
            forecast_60_plans = [
                fp["reduction"] for fp in forecast_60 if fp["group"] == profile
            ]
            forecast_60_plans = forecast_60_plans[0] if forecast_60_plans else []
            profile = {
                "brand": profile.split("-")[-3],
                "model": profile.split("-")[-2],
                "profile": profile.split("-")[-1],
                "now": {
                    "units": bookings_max_units(forecast_0_plans),
                    "date": datetime.now().astimezone().isoformat(),
                },
                "to_create": {
                    "units": bookings_max_units(forecast_30_plans),
                    "date": (
                        datetime.now().astimezone() + timedelta(minutes=30)
                    ).isoformat(),
                },
                "to_destroy": {
                    "units": bookings_max_units(forecast_60_plans),
                    "date": (
                        datetime.now().astimezone() + timedelta(minutes=60)
                    ).isoformat(),
                },
            }
            profiles_forecast.append(profile)
        return profiles_forecast

    def empty_planning(self, plan_id):
        bookings = self.reservables_planner.get_plan_bookings(plan_id)
        for b in bookings:
            self.delete(b["id"])


def bookings_max_units(bookings):
    if not len(bookings):
        return 0
    # We need to use portions library to get bookings intersections max units
    portions = P.IntervalDict()
    for interval in bookings:
        portions[P.closed(interval["start"], interval["end"])] = interval

    join_plan_op = lambda x, y: {
        "units": x["units"] + y["units"],
        "id": x["id"] + "/" + y["id"],
    }

    output = P.IntervalDict()
    for interval in bookings:
        i = P.closed(interval["start"], interval["end"])
        d = P.IntervalDict({i: {"units": interval["units"], "id": interval["id"]}})
        output = output.combine(d, how=join_plan_op)

    # We could maybe just get the max from value["units"]??
    items = []
    for interval, value in output.items():
        for atomic in interval:
            items.append((atomic, value))

    # get max units for all items:
    return max([item[1]["units"] for item in items])
