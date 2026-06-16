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
from isardvdi_common.lib.bookings.reservables import attach_vgpu_hypervisor_groups
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

    @classmethod
    def _assert_manager_owns_card(cls, payload, item_id):
        """A manager may only act on a GPU card delegated to their category.

        Admins pass. A manager passes only when the card's ``gpus.category``
        equals the manager's category; an unassigned/global card (``None``) is
        forbidden for a manager. Admin-author plannings on global cards stay
        admin-only.
        """
        if payload["role_id"] == "admin":
            return
        category = cls.reservables.get_item_category("gpus", item_id)
        if category != payload["category_id"]:
            raise Error(
                "forbidden",
                "GPU card is not delegated to your category",
                description_code="insufficient_permissions",
            )

    @classmethod
    def _assert_manager_owns_plan(cls, payload, plan_id):
        """:meth:`_assert_manager_owns_card` resolved from an existing plan id.

        Collapses a cross-category ``forbidden`` into ``not_found`` so a manager
        cannot enumerate plans on cards outside their category by id.
        """
        if payload["role_id"] == "admin":
            return
        with cls._rdb_context():
            plan = r.table("resource_planner").get(plan_id).run(cls._rdb_connection)
        if not plan:
            raise Error("not_found", "Plan not found", description_code="not_found")
        try:
            cls._assert_manager_owns_card(payload, plan["item_id"])
        except Error as e:
            if getattr(e, "status_code", None) == 403:
                raise Error("not_found", "Plan not found", description_code="not_found")
            raise

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
    def list_all_item_plans(cls, payload=None):
        with cls._rdb_context():
            plans = list(
                r.table("resource_planner")
                .merge(
                    lambda plan: {
                        "item": r.table("gpus")
                        .get(plan["item_id"])
                        .default({"name": "[DELETED]"})["name"],
                        "category": r.table("gpus")
                        .get(plan["item_id"])["category"]
                        .default(None),
                    }
                )
                .run(cls._rdb_connection)
            )
        # A manager only sees plannings on cards delegated to their category;
        # global (category=None) cards stay admin-only.
        if payload and payload.get("role_id") == "manager":
            plans = [p for p in plans if p.get("category") == payload["category_id"]]
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

        # A backwards window (end before start) is meaningless — it yields no
        # availability — so reject it rather than silently storing a dead plan.
        if end < start:
            raise Error(
                "bad_request",
                "End date must be after start date.",
                description_code="invalid_end_date",
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
            for change in result["changes"]:
                old = change["old_val"]
                SchedulerHelper.remove_scheduler_startswith_id(old["id"])
                # Reset the referencing desktop/deployment booking_id so no
                # domain is left pointing at a now-deleted booking (mirrors
                # Bookings.delete). delete_plan is the bulk path: the caller has
                # already deassigned the GPU profile and an unrealizable profile
                # has no running session, so no in-progress guard is needed here.
                if old.get("item_type") == "desktop" and old.get("item_id"):
                    with cls._rdb_context():
                        r.table("domains").get(old["item_id"]).update(
                            {"booking_id": False}
                        ).run(cls._rdb_connection)
                elif old.get("item_type") == "deployment" and old.get("item_id"):
                    with cls._rdb_context():
                        r.table("domains").get_all(old["item_id"], index="tag").update(
                            {"booking_id": False}
                        ).run(cls._rdb_connection)

    @classmethod
    def delete_card_subitem_plans(cls, item_id, subitem_id):
        """Non-last-card disable: drop ONLY this card's availability for this
        profile and surgically detach it from any booking, without touching the
        plans/bookings on the cards that still realize the profile.

        A non-last disable leaves the model-level reservable alive (other cards
        still enable it), so the broad ``deassign_*`` sweep must NOT run -- the
        desktops keep their GPU assignment. But this card's ``resource_planner``
        rows are now phantom capacity: availability is summed by the
        ``subitem_id`` index across all cards, so an orphaned plan on a card that
        no longer realizes the profile would over-count capacity. We therefore
        delete those rows (by the ``item-subitem`` index -- ALL of them,
        regardless of time window) and remove their plan_ids from every booking
        that referenced them. A desktop booking holds a single card's plan, so it
        empties and is deleted (its ``booking_id`` reset, scheduler jobs removed,
        mirroring :meth:`delete_plan`); a multi-card deployment booking keeps the
        entries pointing at the surviving cards and lives on."""
        with cls._rdb_context():
            plan_ids = list(
                r.table("resource_planner")
                .get_all([item_id, subitem_id], index="item-subitem")["id"]
                .run(cls._rdb_connection)
            )
        if not plan_ids:
            return 0, 0
        with cls._rdb_context():
            r.table("resource_planner").get_all(
                r.args(plan_ids), index="id"
            ).delete().run(cls._rdb_connection)
        for plan_id in plan_ids:
            SchedulerHelper.remove_scheduler_startswith_id(plan_id)

        plan_id_set = set(plan_ids)
        with cls._rdb_context():
            affected = list(
                r.table("bookings")
                .filter(
                    lambda b: b["plans"].contains(
                        lambda p: r.expr(plan_ids).contains(p["plan_id"])
                    )
                )
                .run(cls._rdb_connection)
            )
        bookings_deleted = 0
        for booking in affected:
            remaining = [p for p in booking["plans"] if p["plan_id"] not in plan_id_set]
            if remaining:
                with cls._rdb_context():
                    r.table("bookings").get(booking["id"]).update(
                        {"plans": remaining}
                    ).run(cls._rdb_connection)
                continue
            with cls._rdb_context():
                r.table("bookings").get(booking["id"]).delete().run(cls._rdb_connection)
            bookings_deleted += 1
            SchedulerHelper.remove_scheduler_startswith_id(booking["id"])
            if booking.get("item_type") == "desktop" and booking.get("item_id"):
                with cls._rdb_context():
                    r.table("domains").get(booking["item_id"]).update(
                        {"booking_id": False}
                    ).run(cls._rdb_connection)
            elif booking.get("item_type") == "deployment" and booking.get("item_id"):
                with cls._rdb_context():
                    r.table("domains").get_all(booking["item_id"], index="tag").update(
                        {"booking_id": False}
                    ).run(cls._rdb_connection)
        return len(plan_ids), bookings_deleted

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
        plans = ReservablesPlannerCompute.get_subitems_planning(
            [subitem_id], item_id=item_id, now=True
        )
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
    def check_subitem_running_desktops(cls, subitem_id):
        """Refuse to strip a profile a RUNNING desktop is still using. The
        booking guard above only covers in-progress bookings; an admin-started
        desktop has none, so without this an admin disable would delete the
        reservable out from under a live domain. Forces a stop first."""
        with cls._rdb_context():
            running = list(
                r.table("domains")
                .get_all(subitem_id, index="vgpus")
                .filter(lambda d: r.expr(["Started", "Starting"]).contains(d["status"]))
                .pluck("id")
                .run(cls._rdb_connection)
            )
        if running:
            raise Error(
                "bad_request",
                description="There's a running desktop using this GPU profile; "
                "stop it before disabling",
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
                # Span the whole timeline (epoch .. far future). list_subitem_plans
                # defaults end to start when end is omitted, which collapses the
                # window to a single instant and matches NO plan -- so this listing
                # must pass BOTH bounds, otherwise the cascade's delete_plan loop
                # and the UI warning would silently see zero plans/bookings.
                start=datetime.fromtimestamp(0, pytz.timezone("UTC")).strftime(
                    "%Y-%m-%dT%H:%M%z"
                ),
                end=datetime(9999, 12, 31, tzinfo=pytz.utc).strftime(
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
            # Unassign from desktops via the broad index sweep (desktops=None).
            # The explicit data["desktops"] list is built from an inner eq_join
            # to users, so it DROPS domains whose owning user was deleted; the
            # None branch uses get_all(subitem_id, index="vgpus") and resets
            # EVERY domain still holding the reference. Idempotent.
            cls.reservables.deassign_desktops_with_gpu(item_type, subitem_id, None)
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
        else:
            # Non-last disable: the profile survives on other cards. Don't
            # deassign desktops/deployments (they keep their GPU), but THIS
            # card's availability is now phantom -- drop only this card's plans
            # and surgically detach them from bookings (multi-card bookings
            # survive). This also fires from the whole-card delete loop
            # (delete_item), so a shared profile's plans never outlive their card.
            plans_deleted, bookings_deleted = cls.delete_card_subitem_plans(
                item_id, subitem_id
            )
            if plans_deleted or bookings_deleted:
                log.info(
                    "Disabled %s on card %s (profile still on other cards): "
                    "removed %s phantom plan(s), %s booking(s)",
                    subitem_id,
                    item_id,
                    plans_deleted,
                    bookings_deleted,
                )

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
        # Keep only the subitems (profiles) that obtained at least one plan.
        non_empty = {k: v for k, v in plans.items() if v}
        requested = [s for sublist in subitems.values() for s in (sublist or [])]
        if len(non_empty) != len(requested):
            # At least one requested profile cannot fit in the window: the whole
            # multi-profile booking is unsatisfiable.
            return {}
        # Each profile must land on a distinct physical card (item_id). Plannings
        # already enforce one profile per card per window, so distinct profiles are
        # structurally on distinct cards; this set() check is a cheap final guard.
        chosen_item_ids = [p["item_id"] for v in non_empty.values() for p in v]
        if len(set(chosen_item_ids)) != len(chosen_item_ids):
            return {}
        return non_empty

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
                cls.reservables.get_default_subitem(
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

        # Tag each available profile with the hypervisor groups that can host it
        # so the start-now UI can keep a multi-profile selection co-locatable on a
        # single host (admins/managers also get the real hypervisor names).
        attach_vgpu_hypervisor_groups(
            available, show_names=payload.get("role_id") in ("admin", "manager")
        )
        return available
