#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback
from datetime import datetime, timedelta

import pytz
from rethinkdb import RethinkDB

from api import app

from ..api_exceptions import Error

r = RethinkDB()
import logging as log
import random
from pprint import pformat, pprint

from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import uuid

from ..helpers import _check, _get_reservables, _random_password
from .api_reservables import Reservables
from .api_reservables_planner import ReservablesPlanner
from .api_reservables_planner_compute import payload_priority
from .api_reservables_scheduler import ResourceScheduler


def is_future(event):
    return True if event["start"] > datetime.now(pytz.utc) else False


class Bookings:
    def __init__(self):
        self.reservables = Reservables()
        self.reservables_planner = ReservablesPlanner()
        self.resources_scheduler = ResourceScheduler()

    def get_user_priority(self, payload, item_type, item_id):
        reservables, units, item_name = _get_reservables(item_type, item_id)
        return payload_priority(payload, reservables)

    def list_priority_rules(self):
        return list(
            r.table("bookings_priority").pluck("rule_id").distinct().run(db.conn)
        )

    def add(
        self,
        payload,
        start,
        end,
        item_type,  # desktop/deployment
        item_id,  # id
        title=None,
    ):

        # CHECK: There is still empty room for this desktop resources.

        reservables, units, item_name = _get_reservables(item_type, item_id)

        # Has enough quota to do another booking?
        priorities = self.get_user_priority(payload, item_type, item_id)
        if priorities["max_items"] < self.get_total_user_bookings_count(
            payload["user_id"]
        ):
            raise Error(
                "precondition_required",
                "The user " + payload["user_id"] + " has reached max_items bookings.",
            )

        booking = {
            "id": str(uuid.uuid4()),
            "item_id": item_id,
            "item_type": item_type,
            "units": units,
            "reservables": reservables,
            "start": datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC),
            "end": datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
            - timedelta(0, 1),
            "title": title if title else item_name,
            "user_id": payload["user_id"],
        }

        # Overlap this plan with existing ones and check which ones have room from the new booking
        plans = self.reservables_planner.new_booking_plans(payload, booking)
        if not len(plans):
            raise Error("conflict", "The booking does not fit in requested date")

        # We could do a random or anything because the booking fits in one or multiple plans
        # Now we get the first available

        priorities = priorities["priority"]
        new_planning = []
        for k, v in plans.items():
            new_planning.append(
                {
                    "plan_id": v["id"],
                    "item_id": v["item_id"],
                    "subitem_id": v["subitem_id"],
                    "priority": priorities[v["subitem_id"]],
                }
            )

        booking["plans"] = new_planning
        with app.app_context():
            if not _check(r.table("bookings").insert(booking).run(db.conn), "inserted"):
                raise Error("internal_server", "Unable to insert booking in database.")

        self.resources_scheduler.schedule_booking(
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
            raise Error("conflict", "The booking update does not fit in requested date")

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
            raise Error("not_found", "Booking not found", traceback.format_stack())
        if not _check(
            r.table("bookings").get(booking_id).delete().run(db.conn), "deleted"
        ):
            raise Error(
                "internal_server", "Unable to delete booking", traceback.format_stack()
            )

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
                    r.row["start"].during(
                        datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
                        datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
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

    def get_user_bookings(self, fromDate, toDate, user_id):
        with app.app_context():
            bookings = list(
                r.table("bookings")
                .get_all(user_id, index="user_id")
                .filter(
                    r.row["start"].during(
                        datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
                        datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
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

    def get_subitem_reservables_bookings(
        self, reservables, fromDate, toDate, increment_units=0
    ):
        bookings = []

        for k, v in reservables.items():
            query = r.table("bookings")
            query = query.get_all(v, index="reservables_" + k)
            if fromDate and toDate:
                query = query.filter(
                    r.row["start"].during(
                        datetime.strptime(fromDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
                        datetime.strptime(toDate, "%Y-%m-%dT%H:%M%z").astimezone(
                            pytz.UTC
                        ),
                    )
                )
            with app.app_context():
                bookings += list(query.run(db.conn))

        return bookings
        # Add new item units so we can substract it from maximum units allowed
        if increment_units:
            for booking in bookings:
                booking["units"] += increment_units
        return bookings

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