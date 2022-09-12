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

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import os
from datetime import datetime, timedelta

import pytz
from jose import jwt

from .api_rest import ApiRest


class Scheduler:
    def __init__(self):
        self.api_rest = ApiRest("http://isard-scheduler:5000/scheduler")

    """
    GENERIC METHODS
    """

    def reschedule_id(self, id, on_date):
        log.error("Reschedule id " + id + " not implemented!!!")

    def remove_scheduler_startswith_id(self, id):
        try:
            self.api_rest.delete("/startswith/" + id)
        except:
            log.error(
                "Could not contact scheduler service at /" + id + " method DELETE"
            )

    """
    BOOKINGS SPECIFICS
    """

    def bookings_schedule_subitem(
        self, plan_id, item_type, item_id, subitem_id, on_date
    ):
        if isinstance(on_date, datetime):
            on_date = on_date.isoformat()
        data = {
            "kwargs": {
                "item_type": item_type,
                "plan_id": plan_id,
                "item_id": item_id,
                "subitem_id": subitem_id,
            },
        }

        start_date = datetime.strptime(on_date, "%Y-%m-%dT%H:%M:%S%z").astimezone(
            pytz.UTC
        )

        ## end -15m: user message, is about to finish
        data["id"] = plan_id + ".gpu_user_advice-15"
        data["date"] = start_date - timedelta(0, 17 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["message"] = "This desktop will be stopped in 15 minutes"
        try:
            self.api_rest.post("/advanced/date/bookings/gpu_desktops_notify", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_notify"
            )

        ## end -5m: user message, immediate shutdown
        data["id"] = plan_id + ".gpu_user_advice-5"
        data["date"] = start_date - timedelta(0, 7 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["message"] = "This desktop will be stopped in 5 minutes"
        try:
            self.api_rest.post("/advanced/date/bookings/gpu_desktops_notify", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_notify"
            )

        ## end -2m: shutdown desktops
        data["id"] = plan_id + ".gpu_desktops_destroy"
        data["date"] = start_date - timedelta(0, 2 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            self.api_rest.post("/advanced/date/bookings/gpu_desktops_destroy", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_destroy"
            )

        ## end -1m: call engine to set item_id (gpu card) to profile data["profile"]
        data["id"] = plan_id + ".gpu_profile_set"
        data["date"] = start_date - timedelta(0, 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            self.api_rest.post("/advanced/date/bookings/gpu_profile_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_profile_set"
            )

    def bookings_schedule(self, booking_id, item_type, item_id, start, end):
        if isinstance(start, datetime):
            start = start.isoformat()
        if isinstance(end, datetime):
            end = end.isoformat()
        data = {
            "kwargs": {
                "item_type": item_type,
                "booking_id": booking_id,
                "item_id": item_id,
            },
        }

        start_date = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S%z").astimezone(
            pytz.UTC
        )
        end_date = datetime.strptime(end, "%Y-%m-%dT%H:%M:%S%z").astimezone(pytz.UTC)

        ## start -1s: set in_reservable
        data["id"] = booking_id + ".in_reservable"
        data["date"] = start_date - timedelta(0, 1 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            self.api_rest.post("/advanced/date/bookings/domain_reservable_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/domain_reservable_set"
            )

        ## end -1s: set in_reservable
        data["id"] = booking_id + ".not_in_reservable"
        data["date"] = end_date - timedelta(0, 1 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["kwargs"]["booking_id"] = False
        try:
            self.api_rest.post("/advanced/date/bookings/domain_reservable_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/domain_reservable_set"
            )

    def bookings_reschedule_item_id(self, item_id, on_date):
        log.error("Reschedule item id " + item_id + " not implemented!!!")

    def bookings_remove_scheduler_item_id(self, item_id):
        log.error("Remove scheduler id " + item_id + " not implemented!!!")
