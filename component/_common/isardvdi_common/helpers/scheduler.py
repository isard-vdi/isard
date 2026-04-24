#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases, Miriam Melina Gamboa Valdez
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

import logging

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r

log = logging.getLogger(__name__)
import traceback
from datetime import datetime, timedelta

import pytz
from isardvdi_common.connections.api_rest import ApiRest
from isardvdi_common.helpers.api_notify import notify_desktop, notify_user
from isardvdi_common.helpers.desktop_nonpersistent_events import (
    DesktopNonpersistentEvents,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.quotas import Quotas
from isardvdi_common.models.config import Config

# from rethinkdb import RethinkDB

# from .api_nonpersistentdesktop_events import desktop_non_persistent_delete
# from .caches import get_config


class Scheduler(RethinkSharedConnection):

    api_rest = ApiRest("isard-scheduler")

    #     """
    #     GENERIC METHODS
    #     """

    @classmethod
    def remove_scheduler_startswith_id(cls, id):
        try:
            cls.api_rest.delete("/startswith/" + id + ".")
        except Exception:
            log.error(
                "Could not contact scheduler service at /scheduler/"
                + id
                + " method DELETE. "
                + traceback.format_exc()
            )

    #     """
    #     DESKTOPS SCHEDULING
    #     """

    @classmethod
    def remove_desktop_timeouts(cls, desktop_id):
        cls.remove_scheduler_startswith_id(desktop_id)
        with cls._rdb_context():
            r.table("domains").get(desktop_id).update(
                {"scheduled": {"shutdown": False}}
            ).run(cls._rdb_connection)

    @classmethod
    def add_desktop_timeouts(cls, payload, desktop_id, reset_existing=True):
        if reset_existing:
            cls.remove_desktop_timeouts(desktop_id)

        with cls._rdb_context():
            desktop = (
                r.table("domains")
                .get(desktop_id)
                .pluck(
                    "name",
                    "user",
                    "server_autostart",
                    {"create_dict": {"reservables": "vgpus"}},
                    "tag",
                )
                .run(cls._rdb_connection)
            )

        if desktop.get("server_autostart"):
            return

        data = {
            "kwargs": {
                "user_id": desktop["user"],
                "desktop_id": desktop_id,
                "desktop_name": desktop["name"],
                "msg": {
                    "type": "info",
                    "msg_code": "desktop-time-limit",
                },
            },
        }

        start_date = datetime.now(pytz.utc)

        if desktop.get("create_dict", {}).get("reservables", {}).get("vgpus"):
            # First find if deployment has a booking
            booking = []
            if desktop.get("tag"):
                item_id = desktop.get("tag")
                with cls._rdb_context():
                    booking = (
                        r.table("bookings")
                        .get_all(item_id, index="item_id")
                        .filter(
                            lambda plan: (plan["end"] > r.now())
                            & (
                                plan["reservables"]["vgpus"]
                                == desktop.get("create_dict", {})
                                .get("reservables", {})
                                .get("vgpus")
                            )
                        )
                        .order_by("start")
                        .run(cls._rdb_connection)
                    )
            if not len(booking):
                # If not, find if desktop has a booking
                item_id = desktop_id
                with cls._rdb_context():
                    booking = (
                        r.table("bookings")
                        .get_all(item_id, index="item_id")
                        .filter(
                            lambda plan: (plan["end"] > r.now())
                            & (
                                plan["reservables"]["vgpus"]
                                == desktop.get("create_dict", {})
                                .get("reservables", {})
                                .get("vgpus")
                            )
                        )
                        .order_by("start")
                        .run(cls._rdb_connection)
                    )
            if not len(booking):
                if payload["role_id"] in ["admin", "manager"]:
                    # They are gods, they can do whatever they want
                    return
                # There is no booking, can't be started
                # StartNow feature should have added this booking already
                raise Error(
                    "internal_server",
                    "No booking found when trying to start gpu desktop",
                )
            else:
                booking = booking[0]
            data["id"] = desktop_id + ".shutdown-15m"
            data["date"] = (booking["end"] - timedelta(minutes=15)).strftime(
                "%Y-%m-%dT%H:%M%z"
            )
            data["kwargs"]["msg"]["params"] = {
                "date": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                "minutes": 15,
                "name": desktop.get("name"),
            }
            data["kwargs"]["msg"]["type"] = "warning"
            data["kwargs"]["msg"][
                "msg_lang"
            ] = "en"  # TODO Needs to be the frontend user lang
            try:
                cls.api_rest.post("/advanced/date/desktop/desktop_notify", data)
            except Exception:
                log.error(
                    "could not contact scheduler service at /advanced/date/desktop/desktop_notify"
                )
            data["id"] = desktop_id + ".shutdown-5m"
            data["date"] = (booking["end"] - timedelta(minutes=5)).strftime(
                "%Y-%m-%dT%H:%M%z"
            )
            data["kwargs"]["msg"]["type"] = "danger"
            data["kwargs"]["msg"]["params"]["minutes"] = 5
            try:
                cls.api_rest.post("/advanced/date/desktop/desktop_notify", data)
            except Exception:
                log.error(
                    "could not contact scheduler service at /advanced/date/desktop/desktop_notify"
                )
            return

        timeouts = Quotas.get_shutdown_timeouts(payload, desktop_id)
        if not timeouts:
            return

        # Send now notification only to web
        time_remaining = timeouts["max"]
        stop_date = start_date + timedelta(minutes=time_remaining)
        data["date"] = stop_date.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        absolute_end_time = data["date"]
        data["kwargs"]["msg"]["params"] = {"date": stop_date, "minutes": time_remaining}
        if timeouts.get("notify_intervals"):
            for interval in timeouts["notify_intervals"]:
                if interval["time"] == 0:
                    notify_user(
                        desktop["user"],
                        interval["type"],
                        data["kwargs"]["msg"]["msg_code"],
                        params={
                            "date": absolute_end_time,
                            "time_remaining": time_remaining,
                            "name": desktop.get("name"),
                        },
                    )
                    notify_desktop(
                        desktop_id,
                        interval["type"],
                        data["kwargs"]["msg"]["msg_code"],
                        params={
                            "date": absolute_end_time,
                            "time_remaining": time_remaining,
                            "name": desktop.get("name"),
                        },
                    )
                else:
                    # Program in max time + NEGATIVE INTERVAL TIME minutes
                    time_remaining = timeouts["max"] + interval["time"]
                    data["id"] = desktop_id + ".shutdown-" + str(interval["time"]) + "m"
                    data["date"] = start_date + timedelta(minutes=time_remaining)
                    data["date"] = (
                        data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
                    )
                    data["kwargs"]["msg"]["params"] = {
                        "date": absolute_end_time,
                        "minutes": time_remaining,
                        "name": desktop.get("name"),
                    }
                    data["kwargs"]["msg"]["type"] = interval["type"]
                    data["kwargs"]["msg"][
                        "msg_lang"
                    ] = "en"  # TODO Needs to be the frontend user lang
                    try:
                        cls.api_rest.post("/advanced/date/desktop/desktop_notify", data)
                    except Exception:
                        log.error(
                            "could not contact scheduler service at /advanced/date/desktop/desktop_notify"
                        )

        # Stop desktop (Shutting down)
        data["id"] = desktop_id + ".shutdown"
        stop_date = stop_date + timedelta(minutes=1)
        data["date"] = stop_date.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["kwargs"] = {"desktop_id": desktop_id}
        try:
            cls.api_rest.post("/advanced/date/desktop/desktop_stop", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/desktop/desktop_stop"
            )

        # Stop desktop (Force down)
        data["id"] = desktop_id + ".shutdown-force"
        stop_date = stop_date + timedelta(minutes=1)
        data["date"] = stop_date.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["kwargs"] = {"desktop_id": desktop_id}
        try:
            cls.api_rest.post("/advanced/date/desktop/desktop_stop", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/desktop/desktop_stop"
            )

        # Update end time in domain
        with cls._rdb_context():
            r.table("domains").get(desktop_id).update(
                {"scheduled": {"shutdown": absolute_end_time}}
            ).run(cls._rdb_connection)
        return {"shutdown": absolute_end_time}

    #     """
    #     BOOKINGS SPECIFICS
    #     """

    @classmethod
    def bookings_schedule_subitem(
        cls, plan_id, item_type, item_id, subitem_id, on_date
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

        # end -15m: user message, is about to finish
        data["id"] = plan_id + ".gpu_user_advice-15"
        data["date"] = start_date - timedelta(0, 17 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["message"] = "This desktop will be stopped in 15 minutes"
        try:
            cls.api_rest.post("/advanced/date/bookings/gpu_desktops_notify", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_notify"
            )

        # end -5m: user message, immediate shutdown
        data["id"] = plan_id + ".gpu_user_advice-5"
        data["date"] = start_date - timedelta(0, 7 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["message"] = "This desktop will be stopped in 5 minutes"
        try:
            cls.api_rest.post("/advanced/date/bookings/gpu_desktops_notify", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_notify"
            )

        # end -2m: shutdown desktops
        data["id"] = plan_id + ".gpu_desktops_destroy"
        data["date"] = start_date - timedelta(0, 2 * 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            cls.api_rest.post("/advanced/date/bookings/gpu_desktops_destroy", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_desktops_destroy"
            )

        # end -1m: call engine to set item_id (gpu card) to profile data["profile"]
        data["id"] = plan_id + ".gpu_profile_set"
        data["date"] = start_date - timedelta(0, 60)
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            cls.api_rest.post("/advanced/date/bookings/gpu_profile_set", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/gpu_profile_set"
            )

    @classmethod
    def bookings_schedule(cls, booking_id, item_type, item_id, start, end):
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

        # start -1s: set in_reservable
        data["id"] = booking_id + ".in_reservable"
        data["date"] = start_date
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        try:
            cls.api_rest.post("/advanced/date/bookings/domain_reservable_set", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/domain_reservable_set"
            )

        # end -1s: set in_reservable
        data["id"] = booking_id + ".not_in_reservable"
        data["date"] = end_date
        data["date"] = data["date"].astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M%z")
        data["kwargs"]["booking_id"] = False
        try:
            cls.api_rest.post("/advanced/date/bookings/domain_reservable_set", data)
        except Exception:
            log.error(
                "could not contact scheduler service at /advanced/date/bookings/domain_reservable_set"
            )

    @classmethod
    def bookings_reschedule_item_id(cls, item_id, on_date):
        """
        Move every scheduled default-profile job for this planner item to
        `on_date`. Since the scheduler service has no "reschedule" verb we
        delete the existing jobs and let the planner re-register new ones
        through its normal add-plan code paths.

        Matches the v3 silent-no-op when no jobs exist for the item.
        """
        try:
            with cls._rdb_context():
                ids = list(
                    r.table("scheduler_jobs")
                    .pluck("kwargs", "id")
                    .filter({"kwargs": {"item_id": item_id}})["id"]
                    .run(cls._rdb_connection)
                )
            if ids:
                cls.api_rest.delete("/delete_jobs", {"jobs_ids": ids})
        except Exception:
            log.error(
                "Could not reschedule scheduler jobs for item_id "
                + item_id
                + " to "
                + str(on_date)
                + ": "
                + traceback.format_exc()
            )

    @classmethod
    def bookings_remove_scheduler_item_id(cls, item_id):
        """
        Drop every scheduler job tied to this planner item. Delegates to
        :py:meth:`bookings_remove_scheduled_jobs`, which queries
        `scheduler_jobs` and issues a bulk delete against the scheduler
        service.
        """
        cls.bookings_remove_scheduled_jobs(item_id)

    @classmethod
    def bookings_remove_scheduled_jobs(cls, item_id):
        try:
            with cls._rdb_context():
                ids = list(
                    r.table("scheduler_jobs")
                    .pluck("kwargs", "id")
                    .filter({"kwargs": {"item_id": item_id}})["id"]
                    .run(cls._rdb_connection)
                )
            cls.api_rest.delete("/delete_jobs", {"jobs_ids": ids})
        except Exception:
            log.error("could not contact scheduler service at /delete_jobs")

    @classmethod
    def add_nonpersistent_desktop_delete_timeout(cls, desktop_id):
        nonpersistent_desktops_inactivity_limit = Config.get_config()[
            "nonpersistent_desktops_inactivity_limit"
        ]
        if nonpersistent_desktops_inactivity_limit is None:
            return
        elif nonpersistent_desktops_inactivity_limit == 0:
            DesktopNonpersistentEvents.desktop_non_persistent_delete(desktop_id)
            return
        else:
            try:
                cls.api_rest.post(
                    "/advanced/date/desktop/nonpersistent_delete_timeout",
                    {
                        "id": desktop_id + ".nonpersistent_delete",
                        "date": (
                            datetime.now()
                            + timedelta(minutes=nonpersistent_desktops_inactivity_limit)
                        )
                        .astimezone(pytz.UTC)
                        .strftime("%Y-%m-%dT%H:%M%z"),
                        "kwargs": {"desktop_id": desktop_id},
                    },
                )
            except Exception:
                log.error(
                    "could not contact scheduler service at /advanced/date/nonpersistent/delete"
                )
