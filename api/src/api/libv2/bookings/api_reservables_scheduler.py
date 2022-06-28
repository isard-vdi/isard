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

import json
import os
import random
import traceback
import uuid
from datetime import datetime, timedelta
from pprint import pprint

import portion as P
import pytz
import requests
from jose import jwt

from ..api_exceptions import Error
from ..helpers import _check, _get_reservables, _parse_string


class ResourceScheduler:
    def __init__(self):
        self.base_url = "http://isard-scheduler:5000/scheduler"

    def schedule_subitem(self, plan_id, item_type, item_id, subitem_id, on_date):
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
            self._post("/advanced/date/gpu_desktops_notify", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/gpu_desktops_notify"
            )

        ## end -5m: user message, immediate shutdown
        data["id"] = plan_id + ".gpu_user_advice-5"
        data["date"] = start_date - timedelta(0, 7 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["message"] = "This desktop will be stopped in 5 minutes"
        try:
            self._post("/advanced/date/gpu_desktops_notify", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/gpu_desktops_notify"
            )

        ## end -2m: shutdown desktops
        data["id"] = plan_id + ".gpu_desktops_destroy"
        data["date"] = start_date - timedelta(0, 2 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            self._post("/advanced/date/gpu_desktops_destroy", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/gpu_desktops_destroy"
            )

        ## end -1m: call engine to set item_id (gpu card) to profile data["profile"]
        data["id"] = plan_id + ".gpu_profile_set"
        data["date"] = start_date - timedelta(0, 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            self._post("/advanced/date/gpu_profile_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/gpu_profile_set"
            )

    def schedule_booking(self, booking_id, item_type, item_id, start, end):
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
            self._post("/advanced/date/domain_reservable_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/domain_reservable_set"
            )

        ## end -1s: set in_reservable
        data["id"] = booking_id + ".not_in_reservable"
        data["date"] = end_date - timedelta(0, 1 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["kwargs"]["booking_id"] = False
        try:
            self._post("/advanced/date/domain_reservable_set", data)
        except:
            log.error(
                "could not contact scheduler service at /advanced/date/domain_reservable_set"
            )

    def reschedule_id(self, id, on_date):
        log.error("Reschedule id " + id + " not implemented!!!")

    def reschedule_item_id(self, item_id, on_date):
        log.error("Reschedule item id " + item_id + " not implemented!!!")

    def remove_scheduler_id(self, id):
        try:
            self._delete("/startswith/" + id, {})
        except:
            log.error(
                "Could not contact scheduler service at /" + id + " method DELETE"
            )

    def remove_scheduler_item_id(self, item_id):
        log.error("Remove scheduler id " + item_id + " not implemented!!!")

    def header_auth(self):
        token = jwt.encode(
            {
                "exp": datetime.utcnow() + timedelta(seconds=20),
                "kid": "isardvdi",
                "data": {
                    "role_id": "admin",
                    "category_id": "*",
                },
            },
            os.environ["API_ISARDVDI_SECRET"],
            algorithm="HS256",
        )
        return {"Authorization": "Bearer " + token}

    def _post(self, url, data):
        try:
            resp = requests.post(
                self.base_url + url, json=data, headers=self.header_auth()
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error("bad_request", "Bad request while contacting scheduler service")
        except:
            raise Error(
                "internal_server",
                "Could not contact scheduler service",
                traceback.format_exc(),
            )

    def _delete(self, url, data={}):
        try:
            resp = requests.delete(
                self.base_url + url, json=data, headers=self.header_auth()
            )
            if resp.status_code == 200:
                return json.loads(resp.text)
            raise Error("bad_request", "Bad request while contacting scheduler service")
        except:
            raise Error(
                "internal_server",
                "Could not contact scheduler service",
                traceback.format_exc(),
            )
