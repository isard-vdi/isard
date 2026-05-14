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

import logging
import time
import traceback

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.api_notify import notify_admins
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.recycle_bin import Helpers as RecycleBinHelpers
from isardvdi_common.helpers.recycle_bin import (
    RecycleBinBulk,
    RecycleBinCategory,
    RecycleBinDeployment,
    RecycleBinDeploymentDesktops,
    RecycleBinDesktop,
    RecycleBinGroup,
    RecycleBinTemplate,
    RecycleBinUser,
)
from isardvdi_common.models.domain import Domain
from isardvdi_common.schemas.domains import DesktopStatusEnum

log = logging.getLogger(__name__)
from rethinkdb import r

_get_qos_disks_cache: TTLCache = TTLCache(maxsize=20, ttl=30)


class DesktopEvents(RethinkCustomBase):

    @classmethod
    @cached(cache=_get_qos_disks_cache)
    def get_qos_disks(cls):
        with cls._rdb_context():
            qos_disks = list(
                r.table("qos_disk").pluck("id", "allowed").run(cls._rdb_connection)
            )
        return qos_disks

    @classmethod
    def clear_get_qos_disks_cache(cls):
        _get_qos_disks_cache.clear()

    @classmethod
    def get_desktop_qos_disk_id(cls, desktop):
        qos_disks = cls.get_qos_disks()
        for qos_disk in qos_disks:
            if qos_disk["allowed"]["roles"] == []:
                return qos_disk["id"]
        for qos_disk in qos_disks:
            if (
                qos_disk["allowed"]["roles"]
                and desktop["role"] in qos_disk["allowed"]["roles"]
            ):
                return qos_disk["id"]
        return False

    @classmethod
    def wait_status(
        cls,
        desktop_id,
        current_status,
        wait_seconds=0,
        interval_seconds=2,
        raise_exc=True,
    ):
        if wait_seconds == 0:
            return current_status
        seconds = 0
        status = current_status
        while status == current_status and seconds <= wait_seconds:
            time.sleep(interval_seconds)
            seconds += interval_seconds
            try:
                with cls._rdb_context():
                    status = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")["status"]
                        .run(cls._rdb_connection)
                    )
            except Exception:
                raise Error(
                    "not_found",
                    "Desktop not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
        if status == current_status:
            if raise_exc:
                raise Error(
                    "internal_server",
                    "Engine could not change "
                    + desktop_id
                    + " status from "
                    + current_status
                    + " in "
                    + str(wait_seconds),
                    traceback.format_exc(),
                    description_code="generic_error",
                )
            else:
                return False
        return status

    @classmethod
    def get_desktop(cls, desktop_id):
        try:
            # For desktop events better do not cache it's status
            with cls._rdb_context():
                domain = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status", "create_dict", "user")
                    .run(cls._rdb_connection)
                )
            return {
                "status": domain["status"],
                "role": Caches.get_document("users", domain["user"], ["role"]),
                "qos_disk_id": domain["create_dict"]["hardware"].get(
                    "qos_disk_id", False
                ),
            }
        except Exception:
            raise Error(
                "not_found",
                "Desktop not found",
                description_code="not_found",
            )

    @classmethod
    def desktop_start(cls, desktop_id, wait_seconds=0, paused=False):
        domain = cls.get_desktop(desktop_id)
        status = domain["status"]

        # Early return - already in starting or started state
        if status in [
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.starting.value,
            DesktopStatusEnum.starting_paused.value,
            DesktopStatusEnum.creating_and_starting.value,
        ]:
            return status

        # Only allow starting from Stopped or Failed
        if status not in [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.failed.value,
        ]:
            raise Error(
                "precondition_required",
                "Desktop can't be started from " + status,
                traceback.format_exc(),
                description_code="unable_to_start_desktop_from",
            )

        if not Domain(desktop_id).storage_ready:
            raise Error(
                error="precondition_required",
                description="Desktop storages aren't ready",
                description_code="desktop_storage_not_ready",
            )
        qos_disk_id = cls.get_desktop_qos_disk_id(domain)
        target_status = "StartingPaused" if paused else "Starting"

        with cls._rdb_context():
            result = (
                r.table("domains")
                .get(desktop_id)
                .update(
                    lambda row: r.branch(
                        row["status"].match("Stopped|Failed"),
                        {
                            "status": target_status,
                            "viewer": {},
                            "accessed": int(time.time()),
                            "create_dict": {"hardware": {"qos_disk_id": qos_disk_id}},
                        },
                        {},
                    ),
                    return_changes=True,
                )
                .run(cls._rdb_connection)
            )

        if not result.get("changes"):
            # Another request already changed status - return current status
            with cls._rdb_context():
                current_status = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status")["status"]
                    .run(cls._rdb_connection)
                )
            return current_status

        return cls.wait_status(desktop_id, target_status, wait_seconds=wait_seconds)

    @classmethod
    def desktops_start(cls, desktops_ids, paused=False, batch_size=15, wait_seconds=3):
        action = "start"
        desktops_ok = []
        try:
            new_status = (
                DesktopStatusEnum.starting.value
                if not paused
                else DesktopStatusEnum.starting_paused.value
            )
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                keys = [["desktop", d_id] for d_id in batch_ids]
                with cls._rdb_context():
                    desktops_ok.extend(
                        list(
                            r.table("domains")
                            .get_all(*keys, index="kind_ids")
                            .filter(
                                (
                                    (r.row["status"] == DesktopStatusEnum.stopped.value)
                                    | (
                                        r.row["status"]
                                        == DesktopStatusEnum.failed.value
                                    )
                                )
                            )
                            .run(cls._rdb_connection)
                        )
                    )
                time.sleep(wait_seconds)
            for desktop in desktops_ok:
                qos_disk_id = (
                    cls.get_desktop_qos_disk_id(
                        {
                            "status": desktop["status"],
                            "role": Caches.get_document(
                                "users", desktop["user"], ["role"]
                            ),
                            "qos_disk_id": desktop["create_dict"]["hardware"].get(
                                "qos_disk_id", False
                            ),
                        }
                    )
                    if not paused
                    else False
                )
                with cls._rdb_context():
                    r.table("domains").get(desktop["id"]).update(
                        {
                            "status": new_status,
                            "viewer": {},
                            "accessed": int(time.time()),
                            "create_dict": {"hardware": {"qos_disk_id": qos_disk_id}},
                        }
                    ).run(cls._rdb_connection)
                    notify_admins(
                        "desktop_action",
                        {
                            "action": action,
                            "count": len(desktops_ids),
                            "status": "completed",
                        },
                    )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )

        except Exception:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def desktop_stop(cls, desktop_id, force=False, wait_seconds=0):
        with cls._rdb_context():
            status = (
                r.table("domains")
                .get(desktop_id)
                .pluck("status")["status"]
                .run(cls._rdb_connection)
            )

        # Early return - already in final state
        if status in [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.stopping.value,
            DesktopStatusEnum.failed.value,
        ]:
            return status

        # Transition 1: Started → Shutting-down (graceful) OR Started → Stopping (force)
        if status == DesktopStatusEnum.started.value:
            target_status = (
                DesktopStatusEnum.stopping.value
                if force
                else DesktopStatusEnum.shutting_down.value
            )

            with cls._rdb_context():
                result = (
                    r.table("domains")
                    .get(desktop_id)
                    .update(
                        lambda row: r.branch(
                            row["status"].match(DesktopStatusEnum.started.value),
                            {
                                "status": target_status,
                                "accessed": int(time.time()),
                            },
                            {},
                        ),
                        return_changes=True,
                    )
                    .run(cls._rdb_connection)
                )

            if not result.get("changes"):
                # Another request already changed status - return current status
                with cls._rdb_context():
                    current = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")
                        .run(cls._rdb_connection)
                    )
                return current["status"]

            return cls.wait_status(desktop_id, target_status, wait_seconds=wait_seconds)

        # Transition 2: Shutting-down → Stopping (force escalation)
        if status == DesktopStatusEnum.shutting_down.value:
            with cls._rdb_context():
                result = (
                    r.table("domains")
                    .get(desktop_id)
                    .update(
                        lambda row: r.branch(
                            row["status"].match(DesktopStatusEnum.shutting_down.value),
                            {
                                "status": DesktopStatusEnum.stopping.value,
                                "accessed": int(time.time()),
                            },
                            {},
                        ),
                        return_changes=True,
                    )
                    .run(cls._rdb_connection)
                )

            if not result.get("changes"):
                # Already transitioned (likely to Stopping or Stopped)
                with cls._rdb_context():
                    current = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")
                        .run(cls._rdb_connection)
                    )
                return current["status"]

            return cls.wait_status(
                desktop_id, DesktopStatusEnum.stopping.value, wait_seconds=wait_seconds
            )

        # Transition 3: Paused → Stopped
        if status == DesktopStatusEnum.paused.value:
            with cls._rdb_context():
                result = (
                    r.table("domains")
                    .get(desktop_id)
                    .update(
                        lambda row: r.branch(
                            row["status"].match(DesktopStatusEnum.paused.value),
                            {
                                "status": DesktopStatusEnum.stopped.value,
                                "accessed": int(time.time()),
                            },
                            {},
                        ),
                        return_changes=True,
                    )
                    .run(cls._rdb_connection)
                )

            if not result.get("changes"):
                # Already transitioned
                with cls._rdb_context():
                    current = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")
                        .run(cls._rdb_connection)
                    )
                return current["status"]

            return cls.wait_status(
                desktop_id, DesktopStatusEnum.stopped.value, wait_seconds=wait_seconds
            )

        raise Error(
            "precondition_required",
            f"Desktop {desktop_id} can't be stopped from {status}",
            description_code="unable_to_stop_desktop_from",
        )

    @classmethod
    def desktops_stop(
        cls,
        desktops_ids,
        force=False,
        include_shutting_down=True,
        batch_size=20,
        wait_seconds=1,
        update_accessed=True,
    ):
        action = "stop"
        try:
            status_updates = []

            if include_shutting_down:
                status_updates.append(
                    (
                        DesktopStatusEnum.shutting_down.value,
                        DesktopStatusEnum.stopping.value,
                    )
                )
            if force:
                status_updates.append(
                    (DesktopStatusEnum.started.value, DesktopStatusEnum.stopping.value)
                )
            else:
                status_updates.append(
                    (
                        DesktopStatusEnum.started.value,
                        DesktopStatusEnum.shutting_down.value,
                    )
                )

            update_data = {}
            if update_accessed:
                update_data["accessed"] = int(time.time())

            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                keys = [["desktop", d_id] for d_id in batch_ids]
                for current_status, new_status in status_updates:
                    update_data["status"] = new_status
                    with cls._rdb_context():
                        r.table("domains").get_all(*keys, index="kind_ids").filter(
                            {"status": current_status}
                        ).update(update_data).run(cls._rdb_connection)
                time.sleep(wait_seconds)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def desktop_reset(cls, desktop_id):
        with cls._rdb_context():
            domain = (
                r.table("domains")
                .get(desktop_id)
                .pluck("status")
                .run(cls._rdb_connection)
            )

        status = domain["status"]

        # Only allow reset from these states
        if status not in [
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.shutting_down.value,
            DesktopStatusEnum.suspended.value,
            DesktopStatusEnum.stopping.value,
        ]:
            raise Error(
                "precondition_required",
                "Desktop can't be resetted from " + status,
                traceback.format_exc(),
                description_code="unable_to_start_desktop_from",
            )

        # Atomic update - only if still in one of the allowed states
        with cls._rdb_context():
            result = (
                r.table("domains")
                .get(desktop_id)
                .update(
                    lambda row: r.branch(
                        row["status"].match("Started|Shutting-down|Suspended|Stopping"),
                        {
                            "status": DesktopStatusEnum.resetting.value,
                            "accessed": int(time.time()),
                        },
                        {},
                    ),
                    return_changes=True,
                )
                .run(cls._rdb_connection)
            )

        if not result.get("changes"):
            # Status changed by another action - return current status
            with cls._rdb_context():
                current = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status")
                    .run(cls._rdb_connection)
                )
            return current["status"]

        return DesktopStatusEnum.resetting.value

    @classmethod
    def desktop_delete(cls, desktop_id, agent_id, permanent=False):
        with cls._rdb_context():
            tag = (
                r.table("domains")
                .get(desktop_id)["tag"]
                .default(False)
                .run(cls._rdb_connection)
            )
        rcb = RecycleBinDesktop(user_id=agent_id)
        rcb.add(desktop_id)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if permanent or tag or max_time == 0:
            tasks = rcb.delete_storage(agent_id)
            return tasks

    @classmethod
    def desktops_delete(cls, agent_id, desktops_ids, permanent=False, batch_size=200):
        action = "delete"
        try:
            rcb_instances = []

            # Process desktops in batches of maximum 100
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                rcb = RecycleBinBulk(user_id=agent_id)
                rcb.add(batch_ids)
                rcb_instances.append(rcb)

            max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
            # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
            if max_time == 0 or permanent:
                for rcb in rcb_instances:
                    rcb.delete_storage(agent_id)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def deployment_delete(cls, deployment_id, agent_id, permanent=False):
        rcb = RecycleBinDeployment(user_id=agent_id)
        rcb.add(deployment_id)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        if max_time == 0 or permanent:
            tasks = rcb.delete_storage(agent_id)
            return tasks

    @classmethod
    def deployment_delete_desktops(
        cls, agent_id, desktops_ids, permanent=False, owner_id=None, name=None
    ):
        rcb = RecycleBinDeploymentDesktops(user_id=agent_id)
        rcb.add(desktops_ids, owner_id=owner_id, name=name)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(
            owner_id or agent_id
        )
        if max_time == 0 or permanent:
            rcb.delete_storage(agent_id)

    @classmethod
    def user_delete(cls, agent_id, user_id, delete_user=True):
        rcb = RecycleBinUser(user_id=agent_id)
        rcb.add(user_id, delete_user)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if max_time == 0:
            rcb.delete_storage(agent_id)

    @classmethod
    def group_delete(cls, agent_id, group_id):
        rcb = RecycleBinGroup(user_id=agent_id)
        rcb.add(group_id)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if max_time == 0:
            rcb.delete_storage(agent_id)

    @classmethod
    def category_delete(cls, agent_id, category_id):
        rcb = RecycleBinCategory(user_id=agent_id)
        rcb.add(category_id)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if max_time == 0:
            rcb.delete_storage(agent_id)

    @classmethod
    def templates_delete(cls, template_id, agent_id):
        rcb = RecycleBinTemplate(user_id=agent_id)
        rcb.add(template_id=template_id)

        max_time = RecycleBinHelpers.get_user_recycle_bin_cutoff_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if max_time == 0:
            task = rcb.delete_storage(agent_id)
            return task

    @classmethod
    def desktop_retry_failed(cls, desktop_id):
        """_From api/libv2/api_desktop_events.py desktop_updating()_

        Atomically transition a ``Failed`` desktop back to
        ``StartingPaused`` so the engine can re-validate hardware on a
        hypervisor and (on success) move it to ``Stopped``. Used by the
        webapp admin "retry" row action and the v3 ``GET
        /desktop/updating/{id}`` shim. Returns the new status (or
        ``"not_changed"`` if the row was not in ``Failed`` state).

        Atomicity matters: a naive read-then-write would race with the
        engine's own status updates. The conditional update inside
        ``r.branch`` is the only safe way to flip Failed → StartingPaused
        without clobbering an in-flight transition started by another
        process.
        """
        with cls._rdb_context():
            result = (
                r.table("domains")
                .get(desktop_id)
                .update(
                    lambda row: r.branch(
                        row["status"].eq(DesktopStatusEnum.failed.value),
                        {"status": "StartingPaused"},
                        {},
                    )
                )
                .run(cls._rdb_connection)
            )
        return "StartingPaused" if result.get("replaced") else "not_changed"

    @classmethod
    def desktop_updating(cls, desktop_id):
        with cls._rdb_context():
            domain = (
                r.table("domains")
                .get(desktop_id)
                .pluck("status")
                .run(cls._rdb_connection)
            )

        status = domain["status"]

        # Early return if already updating
        if status == DesktopStatusEnum.updating.value:
            return status

        # Only allow updating from Stopped or Failed status
        if status not in [
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.failed.value,
        ]:
            raise Error(
                "precondition_required",
                f"Desktop can't be updated from {status} status. Desktop must be stopped first.",
                traceback.format_exc(),
                description_code="unable_to_update_desktop_from",
            )

        # Atomic update - only if still Stopped
        with cls._rdb_context():
            result = (
                r.table("domains")
                .get(desktop_id)
                .update(
                    lambda row: r.branch(
                        row["status"].match("Stopped|Failed"),
                        {"status": DesktopStatusEnum.updating.value},
                        {},
                    ),
                    return_changes=True,
                )
                .run(cls._rdb_connection)
            )

        if not result.get("changes"):
            # Status changed by another action - return current status
            with cls._rdb_context():
                current = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status")
                    .run(cls._rdb_connection)
                )
            return current["status"]

        return DesktopStatusEnum.updating.value

    @classmethod
    def desktops_force_failed(cls, desktops_ids, batch_size=100):
        action = "force_failed"
        try:
            with cls._rdb_context():
                for i in range(0, len(desktops_ids), batch_size):
                    batch_ids = desktops_ids[i : i + batch_size]
                    keys = [["desktop", d_id] for d_id in batch_ids]
                    if (
                        r.table("domains")
                        .get_all(*keys, index="kind_ids")
                        .filter(
                            lambda item: r.expr(
                                [
                                    DesktopStatusEnum.stopped.value,
                                    DesktopStatusEnum.started.value,
                                    DesktopStatusEnum.downloading.value,
                                    DesktopStatusEnum.shutting_down.value,
                                ]
                            ).contains(item["status"])
                        )
                        .count()
                        .run(cls._rdb_connection)
                        > 0
                    ):
                        raise Error(
                            "bad_request",
                            "Cannot change to Failed status desktops from Stopped, Started, Downloading or Shutting-down status",
                        )
                    r.table("domains").get_all(*keys, index="kind_ids").update(
                        {
                            "status": "Failed",
                            "hyp_started": False,
                            "accessed": int(time.time()),
                        }
                    ).run(cls._rdb_connection)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def desktops_toggle(cls, desktops_ids, force=False, batch_size=100):
        action = "toggle"
        desktops_to_start = []
        desktops_to_stop = []

        try:
            # Classification by status
            for desktop_id in desktops_ids:
                with cls._rdb_context():
                    current_status = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")
                        .run(cls._rdb_connection)["status"]
                    )
                if current_status in ["Stopped", "Failed"]:
                    desktops_to_start.append(desktop_id)
                elif current_status in ["Started"]:
                    desktops_to_stop.append(desktop_id)

            cls.desktops_stop(
                desktops_to_stop, force=force, include_shutting_down=False
            )
            cls.desktops_start(desktops_to_start)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def remove_forced_hyper(cls, desktops_ids, batch_size=100):
        action = "remove_forced_hyper"
        try:
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                with cls._rdb_context():
                    r.table("domains").get_all(r.args(batch_ids)).update(
                        {"forced_hyp": False}
                    ).run(cls._rdb_connection)
                notify_admins(
                    "desktop_action",
                    {
                        "action": action,
                        "count": len(desktops_ids),
                        "status": "completed",
                    },
                )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def remove_favourite_hyper(cls, desktops_ids, batch_size=100):
        action = "remove_favourite_hyper"
        try:
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                with cls._rdb_context():
                    r.table("domains").get_all(r.args(batch_ids)).update(
                        {"favourite_hyp": False}
                    ).run(cls._rdb_connection)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def activate_autostart(cls, desktops_ids, batch_size=100):
        action = "activate_autostart"
        try:
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                with cls._rdb_context():
                    r.table("domains").get_all(r.args(batch_ids)).filter(
                        {"server": True}
                    ).update({"server_autostart": True}).run(cls._rdb_connection)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    @classmethod
    def deactivate_autostart(cls, desktops_ids, batch_size=100):
        action = "deactivate_autostart"
        try:
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                with cls._rdb_context():
                    r.table("domains").get_all(r.args(batch_ids)).update(
                        {"server_autostart": False}
                    ).run(cls._rdb_connection)
                notify_admins(
                    "desktop_action",
                    {
                        "action": action,
                        "count": len(desktops_ids),
                        "status": "completed",
                    },
                )
        except Error as e:
            log.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                error_message = e.args[1]
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )
        except Exception as e:
            log.error(traceback.format_exc())
            notify_admins(
                "desktop_action",
                {
                    "action": action,
                    "count": len(desktops_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )
