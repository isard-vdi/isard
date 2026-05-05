#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging as log
import traceback
import uuid
from datetime import datetime, timedelta

import portion as P
import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.bookings import Bookings as BookingsHelper
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.scheduler import Scheduler as SchedulerHelper
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess
from isardvdi_common.lib.bookings.reservables_planner_compute import (
    ReservablesPlannerCompute,
)
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r

_get_cached_desktop_bookings_cache: TTLCache = TTLCache(maxsize=200, ttl=5)
_get_cached_deployment_bookings_cache: TTLCache = TTLCache(maxsize=200, ttl=5)


class BookingsProcessed(RethinkSharedConnection):

    _rdb_table = "bookings"

    @classmethod
    @cached(cache=_get_cached_desktop_bookings_cache)
    def get_cached_desktop_bookings(cls, desktop_id):
        with cls._rdb_context():
            booking = (
                r.table(cls._rdb_table)
                .get_all(["desktop", desktop_id], index="item_type-id")
                .filter(lambda b: b["end"] > r.now())
                .order_by("start")
                .run(cls._rdb_connection)
            )
        return booking

    @classmethod
    def clear_get_cached_desktop_bookings_cache(cls):
        _get_cached_desktop_bookings_cache.clear()

    @classmethod
    @cached(cache=_get_cached_deployment_bookings_cache)
    def get_cached_deployment_bookings(cls, deployment_id):
        with cls._rdb_context():
            booking = (
                r.table(cls._rdb_table)
                .get_all(["deployment", deployment_id], index="item_type-id")
                .filter(lambda b: b["end"] > r.now())
                .order_by("start")
                .run(cls._rdb_connection)
            )
        return booking

    @classmethod
    def clear_get_cached_deployment_bookings_cache(cls):
        _get_cached_deployment_bookings_cache.clear()

    @classmethod
    def get_all(cls):
        with cls._rdb_context():
            return list(
                r.table("bookings")
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
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_user_priority(cls, payload, item_type, item_id):
        reservables, units, item_name = BookingsHelper._get_reservables(
            item_type, item_id
        )
        return ReservablesPlannerCompute.payload_priority(payload, reservables)

    @classmethod
    def get_min_profile_priority(cls, item_type, item_id):
        reservables, units, item_name = BookingsHelper._get_reservables(
            item_type, item_id
        )
        return ReservablesPlannerCompute.min_profile_priority(reservables)

    @classmethod
    def get_users_priorities(cls, rule_id):
        with cls._rdb_context():
            priority = list(
                r.table("bookings_priority")
                .get_all(rule_id, index="rule_id")
                .run(cls._rdb_connection)
            )
        users = []
        kind = ""
        for p in priority:
            allowed = p["allowed"]
            for key, value in allowed.items():
                if value == False:
                    continue
                if len(value) > 0:
                    if key == "users":
                        for item in value:
                            with cls._rdb_context():
                                user = (
                                    r.table("users")
                                    .get(item)
                                    .pluck(
                                        "id", "role", "category", "username", "group"
                                    )
                                    .run(cls._rdb_connection)
                                )
                            users.append(user)
                            if len(users) == 2:
                                return ReservablesPlannerCompute.compute_user_priority(
                                    users, rule_id
                                )
                    if key == "categories":
                        kind = "category"
                    if key == "groups":
                        kind = "group"
                    if key == "roles":
                        kind = "role"
                    with cls._rdb_context():
                        users = list(
                            r.table("users")
                            .filter({kind: value[0]})
                            .sample(2)
                            .pluck("id", "role", "category", "username", "group")
                            .run(cls._rdb_connection)
                        )
                    return ReservablesPlannerCompute.compute_user_priority(
                        users, rule_id
                    )

                else:
                    with cls._rdb_context():
                        users = list(
                            r.table("users")
                            .sample(2)
                            .pluck("id", "role", "category", "username", "group")
                            .run(cls._rdb_connection)
                        )
                    return ReservablesPlannerCompute.compute_user_priority(
                        users, rule_id
                    )

    @classmethod
    def delete_users_priority(cls, priority_id):
        with cls._rdb_context():
            r.table("bookings_priority").get(priority_id).delete().run(
                cls._rdb_connection
            )

    @classmethod
    def list_priority_rules(cls):
        with cls._rdb_context():
            return list(
                r.table("bookings_priority")
                .pluck("rule_id")
                .distinct()
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_minumum_forbid_time(cls):
        return list(r.table("bookings_priority")["forbid_time"].min())

    @classmethod
    def add(
        cls,
        payload,
        start,
        end,
        item_type,  # desktop/deployment
        item_id,  # id
        title=None,
        now=False,
    ):
        # CHECK: There is still empty room for this desktop resources.

        reservables, units, item_name = BookingsHelper._get_reservables(
            item_type, item_id
        )

        # Has enough quota to do another booking?
        priorities = cls.get_user_priority(payload, item_type, item_id)
        if priorities["max_items"] <= cls.get_total_user_bookings_count(
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
        plans = ReservablesPlannerProccess.new_booking_plans(payload, booking)
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
        with cls._rdb_context():
            r.table("bookings").insert(booking).run(cls._rdb_connection)
        if now:
            if item_type == "desktop":
                with cls._rdb_context():
                    r.table("domains").get(item_id).update(
                        {"booking_id": booking["id"]}
                    ).run(cls._rdb_connection)
            else:
                raise Error(
                    "bad_request", "Can't set a booking starting now in a deployment"
                )
        SchedulerHelper.bookings_schedule(
            booking["id"], item_type, item_id, booking["start"], booking["end"]
        )
        return {
            **booking,
            **{
                "editable": BookingsHelper.is_future(booking),
                "start": start,
                "end": end,
            },
        }

    @classmethod
    def update(
        cls,
        booking_id,
        payload,
        title,
        start,
        end,
    ):
        with cls._rdb_context():
            booking = r.table("bookings").get(booking_id).run(cls._rdb_connection)
        if booking is None:
            raise Error(
                "not_found",
                "Booking not found",
                description_code="not_found",
            )
        new_start = datetime.strptime(start, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
        new_end = datetime.strptime(end, "%Y-%m-%dT%H:%M%z").astimezone(pytz.UTC)
        if not ReservablesPlannerProccess.existing_booking_update_fits(
            payload, booking, new_start, new_end
        ):
            raise Error(
                "conflict",
                "The booking update does not fit in requested date",
                description_code="booking_does_not_fit_date",
            )

        with cls._rdb_context():
            r.table("bookings").get(booking_id).update(
                {
                    "title": title,
                    "start": new_start,
                    "end": new_end,
                }
            ).run(cls._rdb_connection)

    @classmethod
    def delete(
        cls,
        booking_id,
    ):
        with cls._rdb_context():
            booking = r.table("bookings").get(booking_id).run(cls._rdb_connection)
        if booking == None:
            raise Error(
                "not_found",
                "Booking not found",
                traceback.format_stack(),
                description_code="not_found",
            )
        # If the booking is in progress, the desktop must be stopped
        if booking.get("start") <= datetime.now(pytz.utc) and booking.get(
            "end"
        ) >= datetime.now(pytz.utc):
            if booking.get("item_type") == "desktop":
                with cls._rdb_context():
                    desktop_status = (
                        r.table("domains")
                        .get(booking.get("item_id"))
                        .pluck("status")["status"]
                        .run(cls._rdb_connection)
                    )
                if desktop_status not in [
                    DesktopStatusEnum.stopped.value,
                    DesktopStatusEnum.failed.value,
                ]:
                    raise Error(
                        "precondition_required",
                        "In order to remove a booking in progress its desktop must be stopped",
                        traceback.format_stack(),
                        description_code="booking_desktop_delete_stop",
                    )
                else:
                    r.table("domains").get(booking.get("item_id")).update(
                        {"booking_id": False}
                    ).run(cls._rdb_connection)
                    SchedulerHelper.remove_desktop_timeouts(booking.get("item_id"))
            elif booking.get("item_type") == "deployment":
                with cls._rdb_context():
                    desktops = (
                        r.table("domains")
                        .get_all(booking.get("item_id"), index="tag")
                        .pluck("status", "id")
                        .run(cls._rdb_connection)
                    )
                if any(
                    d.get("status")
                    not in [
                        DesktopStatusEnum.stopped.value,
                        DesktopStatusEnum.failed.value,
                    ]
                    for d in desktops
                ):
                    raise Error(
                        "precondition_required",
                        "In order to remove a booking in progress the deployment desktops must be stopped",
                        traceback.format_stack(),
                        description_code="booking_deployment_delete_stop",
                    )
                else:
                    with cls._rdb_context():
                        r.table("domains").get_all(
                            booking.get("item_id"), index="tag"
                        ).update({"booking_id": False}).run(cls._rdb_connection)
                    for desktop in desktops:
                        SchedulerHelper.remove_desktop_timeouts(desktop.get("id"))

        with cls._rdb_context():
            r.table("bookings").get(booking_id).delete().run(cls._rdb_connection)

        SchedulerHelper.remove_scheduler_startswith_id(booking_id)

    @classmethod
    def get_item_bookings(
        cls,
        payload,
        fromDate,
        toDate,
        item_type,
        item_id,
        returnType="all",
        returnUnavailable=None,
    ):
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

        reservable_plan = ReservablesPlannerProccess.get_item_availability(
            payload, item_type, item_id, fromDate, toDate, returnUnavailable
        )
        if not returnType or returnType == "all":
            return [
                {
                    **booking,
                    **{
                        "editable": BookingsHelper.is_future(booking),
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
                        "editable": BookingsHelper.is_future(booking),
                        "event_type": "event",
                        "start": booking["start"].strftime("%Y-%m-%dT%H:%M%z"),
                        "end": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                    },
                }
                for booking in bookings
            ]
        if returnType == "availability":
            return reservable_plan

    @classmethod
    def delete_item_bookings(cls, item_type, item_id):
        with cls._rdb_context():
            if not Helpers._check(
                r.table("bookings")
                .get_all([item_type, item_id], index="item_type-id")
                .delete()
                .run(cls._rdb_connection),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Unable to delete item bookings",
                    traceback.format_stack(),
                )
        SchedulerHelper.bookings_remove_scheduled_jobs(item_id)

    @classmethod
    def get_user_bookings(cls, fromDate, toDate, user_id):
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
            deployment_desktops_tags = list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .filter(lambda desktop: r.not_(desktop["tag"] == False))["tag"]
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )
        return [
            {
                **booking,
                **{
                    "editable": BookingsHelper.is_future(booking),
                    "event_type": "event",
                    "start": booking["start"].strftime("%Y-%m-%dT%H:%M%z"),
                    "end": booking["end"].strftime("%Y-%m-%dT%H:%M%z"),
                },
            }
            for booking in bookings
        ]

    @classmethod
    def get_total_user_bookings_count(cls, user_id):
        start = datetime.now(pytz.utc)
        # Count the bookings the user already has
        with cls._rdb_context():
            return (
                r.table("bookings")
                .get_all(user_id, index="user_id")
                .filter(r.row["start"] > start)
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_booking_plans(cls, booking_id):
        with cls._rdb_context():
            plan_ids = [
                plan["plan_id"]
                for plan in list(
                    r.table("bookings")
                    .get(booking_id)["plans"]
                    .run(cls._rdb_connection)
                )
            ]
        with cls._rdb_context():
            return list(
                r.db("isard")
                .table("resource_planner")
                .get_all(*plan_ids)
                .merge(
                    lambda plan: {"item": r.table("gpus").get(plan["item_id"])["name"]}
                )
                .run(cls._rdb_connection)
            )

    """
      Orchestrator provisioning
    """

    @classmethod
    def get_booking_profile_count_within_one_hour(cls):
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

        with cls._rdb_context():
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
                .run(cls._rdb_connection)
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
                    "units": cls.bookings_max_units(forecast_0_plans),
                    "date": datetime.now().astimezone().isoformat(),
                },
                "to_create": {
                    "units": cls.bookings_max_units(forecast_30_plans),
                    "date": (
                        datetime.now().astimezone() + timedelta(minutes=30)
                    ).isoformat(),
                },
                "to_destroy": {
                    "units": cls.bookings_max_units(forecast_60_plans),
                    "date": (
                        datetime.now().astimezone() + timedelta(minutes=60)
                    ).isoformat(),
                },
            }
            profiles_forecast.append(profile)
        return profiles_forecast

    def empty_planning(cls, plan_id):
        bookings = ReservablesPlannerProccess.get_plan_bookings(plan_id)
        for b in bookings:
            cls.delete(b["id"])

    @staticmethod
    def bookings_max_units(bookings):
        # Was ``@classmethod`` with a single ``bookings`` parameter, which
        # silently bound ``cls`` as ``bookings`` on every call (the three
        # call sites in ``get_booking_profile_count_within_one_hour``
        # passed a list as the only positional arg, so Python passed two
        # args to a one-arg signature → TypeError before the body ever
        # ran). The function only operates on its argument, so
        # ``@staticmethod`` is the right shape. Tracked as Bug 33 in
        # APIV4_LOAD_TESTING_BUGS_FOUND.md (root cause was misdiagnosed
        # as a response-model mismatch in the load-testing report —
        # actual cause is this decorator/signature mismatch).
        if not len(bookings):
            return 0
        # We need to use portions library to get bookings intersections max units
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

    @classmethod
    def check_all_bookings(cls, batch_size=250):
        log.info("check_all_bookings Started")

        # filter all desktops with an old booking
        with cls._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all("desktop", index="kind")
                .eq_join("booking_id", r.table("bookings"))
                .filter(lambda booking: booking["right"]["end"] < r.now())["left"]["id"]
                .run(cls._rdb_connection)
            )
        log.info(
            f"check_all_bookings Updating {len(desktops)} desktops with old bookings"
        )
        for i in range(0, len(desktops), batch_size):
            batch_ids = desktops[i : i + batch_size]
            with cls._rdb_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"booking_id": False}
                ).run(cls._rdb_connection)

        # filter all desktops with a non existing booking
        with cls._rdb_context():
            bookings = list(
                r.table("domains")
                .get_all("desktop", index="kind_valid_booking")
                .filter(lambda desktop: desktop["booking_id"] != False)
                .pluck("booking_id")["booking_id"]
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            existing_bookings = list(
                r.table("bookings")
                .get_all(r.args(bookings))["id"]
                .run(cls._rdb_connection)
            )
        nonexistent_bookings = [b for b in bookings if b not in existing_bookings]
        log.info(
            f"check_all_bookings Updating {len(nonexistent_bookings)} desktops with nonexistent bookings"
        )

        for i in range(0, len(nonexistent_bookings), batch_size):
            batch_ids = nonexistent_bookings[i : i + batch_size]
            with cls._rdb_context():
                r.table("domains").get_all(
                    r.args(batch_ids), index="booking_id"
                ).update({"booking_id": False}).run(cls._rdb_connection)

        # update desktops with current booking
        with cls._rdb_context():
            current_bookings = list(
                r.table("bookings")
                .get_all("desktop", index="item_type")
                .filter(
                    lambda booking: booking["start"] < r.now()
                    and booking["end"] > r.now()
                )
                .run(cls._rdb_connection)
            )
        for booking in current_bookings:
            with cls._rdb_context():
                r.table("domains").get(booking["item_id"]).update(
                    {"booking_id": booking["id"]}
                ).run(cls._rdb_connection)

        # update deployment desktops with current booking
        with cls._rdb_context():
            current_bookings = list(
                r.table("bookings")
                .get_all("deployment", index="item_type")
                .filter(
                    lambda booking: booking["start"] < r.now()
                    and booking["end"] > r.now()
                )
                .run(cls._rdb_connection)
            )
        for booking in current_bookings:
            with cls._rdb_context():
                r.table("domains").get_all(booking["item_id"], index="tag").update(
                    {"booking_id": booking["id"]}
                ).run(cls._rdb_connection)

        log.info("check_all_bookings Finished")
