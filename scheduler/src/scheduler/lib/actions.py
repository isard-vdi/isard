#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

import string
import time

from rethinkdb import RethinkDB

from scheduler import app

r = RethinkDB()
import os
import pickle
import tarfile
import traceback

from .flask_rethink import RDB
from .log import log

db = RDB(app)
db.init_app(app)

from datetime import datetime, timedelta

BATCH_SIZE = 50000

from isardvdi_apiv4_client.api.role_admin import (
    admin_delete_old_tasks_auto,
    admin_logs_desktops_delete,
    admin_logs_users_delete,
    admin_notify_desktop,
    admin_notify_user_desktop,
    admin_usage_consolidate,
    convert_storage,
    delete_cutoff_time_surpassed,
)
from isardvdi_apiv4_client.api.role_admin import (
    delete_expired_user_notifications_data as delete_expired_notifications,
)
from isardvdi_apiv4_client.api.role_admin import (
    delete_old_entries,
    move_storage_by_path,
    recycle_bin_add_unused_items,
    retry_all_failed_tasks,
    rsync_storage_to_path,
)
from isardvdi_apiv4_client.api.role_advanced import (
    increase_storage_size,
    stop_all_desktops_in_deployment,
)
from isardvdi_apiv4_client.api.role_user import delete_desktop, stop_desktop
from isardvdi_apiv4_client.models import (
    NotifyDesktopRequest,
    NotifyDesktopRequestParams,
    NotifyUserDesktopRequest,
    NotifyUserDesktopRequestParams,
    StorageConvertRequest,
    StorageMoveByPathRequest,
    StorageRsyncToPathRequest,
)
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status

from .api_client import ApiClient
from .exceptions import Error

engine_client = ApiClient("engine")
scheduler_client = ApiClient("scheduler")


class _SafeFormatter(string.Formatter):
    """Formatter that only allows simple key substitution, rejecting
    attribute access ({key.attr}) and item access ({key[0]}) to prevent
    Server-Side Template Injection via str.format()."""

    def get_field(self, field_name, args, kwargs):
        if not field_name.isidentifier():
            raise ValueError(f"Invalid format field: {field_name!r}")
        return super().get_field(field_name, args, kwargs)


_safe_formatter = _SafeFormatter()


def safe_format(template, **kwargs):
    return _safe_formatter.format(template, **kwargs)


def format_lang(message_code, lang, kwargs):
    msg = (
        app.langs.get(lang, app.langs.get("en", {}))
        .get("messages", {})
        .get(message_code)
    )
    if not msg:
        log.error("Unknown lang " + str(lang) + " or msg code " + str(message_code))
        return "Desktop notification message with unknown code."
    try:
        return safe_format(msg, **kwargs)
    except:
        log.error(traceback.format_exc())


class Actions:
    def consolidate_consumptions_kwargs():
        return []

    def consolidate_consumptions():
        with build_client("isard-scheduler") as client:
            resp = admin_usage_consolidate.sync_detailed(client=client)
            raise_for_status(resp)

    def desktop_notify(**kwargs):
        # Send to frontend
        with build_client("isard-scheduler") as client:
            resp = admin_notify_user_desktop.sync_detailed(
                client=client,
                body=NotifyUserDesktopRequest(
                    user_id=kwargs["user_id"],
                    type_=kwargs["msg"]["type"],
                    msg_code=kwargs["msg"]["msg_code"],
                    params=NotifyUserDesktopRequestParams.from_dict(
                        kwargs["msg"]["params"]
                    ),
                ),
            )
            raise_for_status(resp)

            resp = admin_notify_desktop.sync_detailed(
                client=client,
                body=NotifyDesktopRequest(
                    desktop_id=kwargs["desktop_id"],
                    type_=kwargs["msg"]["type"],
                    msg_code=kwargs["msg"]["msg_code"],
                    params=NotifyDesktopRequestParams.from_dict(
                        kwargs["msg"]["params"]
                    ),
                ),
            )
            raise_for_status(resp)

        # Send to QMP
        engine_client.post(
            "/engine/qmp/notify/" + kwargs["desktop_id"],
            {
                "desktop_id": kwargs["desktop_id"],
                "message": kwargs["msg"]["type"]
                + ": "
                + format_lang(
                    kwargs["msg"]["msg_code"],
                    kwargs["msg"].get("msg_lang", "en"),
                    kwargs["msg"]["params"],
                ),
            },
        )

    def desktop_stop(**kwargs):
        try:
            with build_client("isard-scheduler") as client:
                resp = stop_desktop.sync_detailed(
                    client=client, desktop_id=kwargs["desktop_id"]
                )
                raise_for_status(resp)
        except:
            log.error(
                "Exception when stopping desktop "
                + kwargs["desktop_id"]
                + ": "
                + traceback.format_exc()
            )

    def stop_domains():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").update(
                {"status": "Stopping"}
            ).run(db.conn)

    def stop_domains_without_viewer_kwargs():
        return []

    def stop_domains_without_viewer():
        with app.app_context():
            r.table("domains").get_all("Started", index="status").filter(
                {"viewer": {"client_since": False}}
            ).update({"status": "Stopping"}).run(db.conn)

    def stop_shutting_down_desktops_kwargs():
        return []

    def stop_shutting_down_desktops():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Shutting-down", index="status")
                .pluck("id", "accessed")
                .run(db.conn)
            )
        t = int(time.time())

        ids_list = [d["id"] for d in domains if d["accessed"] + 1.9 * 60 < t]
        for i in range(0, len(ids_list), BATCH_SIZE):
            batch_ids = ids_list[i : i + BATCH_SIZE]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"status": "Stopping", "accessed": int(time.time())}
                ).run(db.conn)

    def check_ephimeral_status_kwargs():
        return []

    def check_ephimeral_status():
        with app.app_context():
            domains = (
                r.table("domains")
                .get_all("Started", index="status")
                .has_fields("ephimeral")
                .pluck("id", "ephimeral", "history_domain")
                .run(db.conn)
            )
        t = int(time.time())
        ids_list = [
            d["id"]
            for d in domains
            if d["history_domain"][0]["when"] + int(d["ephimeral"]["minutes"]) * 60 < t
        ]
        for i in range(0, len(ids_list), BATCH_SIZE):
            batch_ids = ids_list[i : i + BATCH_SIZE]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"status": d["ephimeral"]["action"]}
                ).run(db.conn)

    def domain_qmp_notification_kwargs(**kwargs):
        return [
            {
                "id": "domain_id",
                "name": "Domain ID",
                "placeholder": "Domain to be notified",
                "element": "select2",
                "ajax": {
                    "type": "POST",
                    "url": "/admin/allowed/term/domains",
                    "url_id": None,
                    "data": {"pluck": ["id", "name"]},
                    "ids": "id",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "Message to be sent",
                "element": "textarea",
            },
        ]

    def domain_qmp_notification(**kwargs):
        engine_client.put(
            "/engine/qmp/" + kwargs["domain_id"],
            {"action": "message", "kwargs": {"message": kwargs["message"]}},
        )

    def deployment_qmp_notification_kwargs(**kwargs):
        return [
            {
                "id": "deployment_id",
                "name": "Deployment ID",
                "placeholder": "Deployment desktops to be notified",
                "element": "select2",
                "ajax": {
                    "type": "POST",
                    "url": "/admin/allowed/term/deployments",
                    "url_id": None,
                    "data": {"pluck": ["id", "name"]},
                    "ids": "id",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "Message to be sent",
                "element": "textarea",
            },
        ]

    def deployment_qmp_notification(**kwargs):
        with app.app_context():
            deployment = (
                r.table("deployments").get(kwargs["deployment_id"]).run(db.conn)
            )
        if not deployment:
            log.error("Deployment id " + kwargs["deployment_id"] + " not found")
            raise Error(
                "not_found", "Deployment id " + kwargs["deployment_id"] + " not found"
            )
        with app.app_context():
            domains_ids = (
                r.table("domains")
                .get_all(kwargs["deployment_id"], index="tag")["id"]
                .coerce_to("array")
                .run(db.conn)
            )
        for domain_id in domains_ids:
            engine_client.put(
                "/engine/qmp/" + domain_id,
                {"action": "message", "kwargs": {"message": kwargs["message"]}},
            )

    ### GPUS SPECIFICS
    def gpu_desktops_notify_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU phy id",
                "placeholder": "gpu physical_device",
                "element": "input",
                "ajax": {
                    "type": "GET",
                    "url": "/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "physical_device",
                    "values": "name",
                },
            },
            {
                "id": "message",
                "name": "Message",
                "placeholder": "message to send to domains using this gpu",
                "element": "textarea",
            },
        ]

    def gpu_desktops_notify(**kwargs):
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            raise Error(
                "bad_request",
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!",
                traceback.format_exc(),
            )

        domains_ids = engine_client.get(
            "/engine/profile/gpu/started_domains/" + gpu_device
        )
        log.debug("-> We got " + str(domains_ids) + " domains id to be notified...")
        for domain_id in domains_ids:
            engine_client.put(
                "/engine/qmp/" + domain_id,
                {"action": "message", "message": kwargs["message"]},
            )

    def gpu_desktops_destroy_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU name",
                "placeholder": "gpu physical_device to destroy domains using it",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "id",
                    "values": "name",
                },
            },
        ]

    def gpu_desktops_destroy(**kwargs):
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            raise Error(
                "bad_request",
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!",
                traceback.format_exc(),
            )

        domains_ids = engine_client.get(
            "/engine/profile/gpu/started_domains/" + gpu_device
        )
        log.debug("-> We got " + str(domains_ids) + " domains id to be destroyed...")

        for domain_id in domains_ids:
            try:
                with build_client("isard-scheduler") as client:
                    resp = stop_desktop.sync_detailed(
                        client=client, desktop_id=domain_id
                    )
                    raise_for_status(resp)
                    log.debug(
                        "-> Stopping domain " + domain_id + ": " + str(resp.parsed)
                    )
            except:
                log.error(
                    "Exception when stopping domain "
                    + domain_id
                    + ": "
                    + traceback.format_exc()
                )

    def gpu_profile_set_kwargs(**kwargs):
        return [
            {
                "id": "item_id",
                "name": "GPU phy ID",
                "placeholder": "GPU physical id to set profile",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/admin/reservables/gpus",
                    "url_id": None,
                    "data": {},
                    "ids": "physical_device",
                    "values": "name",
                },
            },
            {
                "id": "subitem_id",
                "name": "GPU profile ID",
                "placeholder": "GPU profile to be set",
                "element": "select",
                "ajax": {
                    "type": "GET",
                    "url": "/admin/reservables/enabled/gpus",
                    "url_id": "item_id",
                    "data": {},
                    "ids": "id",
                    "values": "name",
                },
            },
        ]

    def gpu_profile_set(**kwargs):
        # Will set profile_id on selected card.
        with app.app_context():
            gpu_device = (
                r.table("gpus")
                .get(kwargs["item_id"])
                .pluck("physical_device")
                .run(db.conn)["physical_device"]
            )
        if not gpu_device:
            log.error(
                "The gpu "
                + kwargs["item_id"]
                + " has no associated physical_device right now!"
            )
            return

        answer = engine_client.get("/engine/profile/gpu/" + gpu_device)
        if (
            answer.get("vgpu_profile")
            and answer["vgpu_profile"] == kwargs["subitem_id"].split("-")[-1]
        ):
            raise Error(
                "bad_request",
                "-> The actual profile at vgpu is the same we want to put: "
                + str(kwargs["subitem_id"])
                + ", so doing nothing.",
            )

        answer = engine_client.put(
            "/engine/profile/gpu/" + gpu_device,
            {"profile_id": kwargs["subitem_id"]},
        )
        log.debug(
            "-> Profile "
            + kwargs["subitem_id"]
            + " set to gpu "
            + gpu_device
            + ": "
            + str(answer)
        )

    def domain_reservable_set_kwargs(**kwargs):
        return []

    def domain_reservable_set(**kwargs):
        if kwargs["item_type"] == "deployment":
            with app.app_context():
                r.table("domains").get_all(kwargs["item_id"], index="tag").update(
                    {"booking_id": kwargs["booking_id"]}
                ).run(db.conn)
            if not kwargs["booking_id"]:
                try:
                    with build_client("isard-scheduler") as client:
                        resp = stop_all_desktops_in_deployment.sync_detailed(
                            client=client, deployment_id=kwargs["item_id"]
                        )
                        raise_for_status(resp)
                        log.debug(
                            "-> Stopping deployment "
                            + kwargs["item_id"]
                            + " desktops: "
                            + str(resp.parsed)
                        )
                except:
                    log.error(
                        "Exception when stopping deployment "
                        + kwargs["item_id"]
                        + " desktops: "
                        + traceback.format_exc()
                    )

        if kwargs["item_type"] == "desktop":
            with app.app_context():
                r.table("domains").get(kwargs["item_id"]).update(
                    {"booking_id": kwargs["booking_id"]}
                ).run(db.conn)
            if not kwargs["booking_id"]:
                try:
                    with build_client("isard-scheduler") as client:
                        resp = stop_desktop.sync_detailed(
                            client=client, desktop_id=kwargs["item_id"]
                        )
                        raise_for_status(resp)
                        log.debug(
                            "-> Stopping desktop "
                            + kwargs["item_id"]
                            + ": "
                            + str(resp.parsed)
                        )
                except:
                    log.error(
                        "Exception when stopping desktop "
                        + kwargs["item_id"]
                        + ": "
                        + traceback.format_exc()
                    )

    def recycle_bin_cutoff_time_system_delete():
        with build_client("isard-scheduler") as client:
            resp = delete_cutoff_time_surpassed.sync_detailed(client=client)
            raise_for_status(resp)

    def send_unused_items_to_recycle_bin(**kwargs):
        try:
            with build_client("isard-scheduler") as client:
                resp = recycle_bin_add_unused_items.sync_detailed(client=client)
                raise_for_status(resp)
        except:
            log.error(
                "Exception when sending to recycle bin unused items: "
                + traceback.format_exc()
            )

    def delete_expired_notifications_data(**kwargs):
        try:
            with build_client("isard-scheduler") as client:
                resp = delete_expired_notifications.sync_detailed(client=client)
                raise_for_status(resp)
        except:
            log.error(
                "Exception when deleting expired notifications: "
                + traceback.format_exc()
            )

    # def recycle_bin_old_entries_action_archive(**kwargs):
    #     return []

    # def recycle_bin_old_entries_action_archive(**kwargs):
    #     api_client.put("/recycle_bin/old_entries/archive")

    def recycle_bin_old_entries_action_delete_kwargs(**kwargs):
        return []

    def recycle_bin_old_entries_action_delete(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = delete_old_entries.sync_detailed(client=client)
            raise_for_status(resp)

    def wait_desktops_to_do_storage_action_kwargs(**kwargs):
        return []

    def wait_desktops_to_do_storage_action(**kwargs):
        response = None
        try:
            with build_client("isard-scheduler") as client:
                if kwargs["action"] == "move":
                    if kwargs.get("rsync"):
                        resp = rsync_storage_to_path.sync_detailed(
                            client=client,
                            storage_id=kwargs["storage_id"],
                            body=StorageRsyncToPathRequest(
                                destination_path=kwargs["destination_path"],
                                priority=kwargs["priority"],
                            ),
                        )
                    else:
                        resp = move_storage_by_path.sync_detailed(
                            client=client,
                            storage_id=kwargs["storage_id"],
                            body=StorageMoveByPathRequest(
                                dest_path=kwargs["destination_path"],
                                priority=kwargs["priority"],
                            ),
                        )
                elif kwargs["action"] == "virt_win_reg":
                    # ---------------------------------------------------------
                    # Deliberate escape hatch.
                    #
                    # The apiv4 endpoint PUT /item/storage/{id}/virt-win-reg/
                    # priority/{priority} declares StorageVirtWinRegRequest
                    # (with a required `registry_patch` field) as its body.
                    # The scheduler path has never carried a patch payload —
                    # it only schedules the priority change — so the typed
                    # method virt_win_reg_storage.sync_detailed() cannot be
                    # called without fabricating a payload the server will
                    # later have to reject or misinterpret.
                    #
                    # Do not migrate to the typed client without first
                    # splitting the endpoint (or making the body optional
                    # with a documented semantics for the no-body case).
                    # ---------------------------------------------------------
                    resp = client.get_httpx_client().request(
                        "put",
                        f"/api/v4/item/storage/{kwargs['storage_id']}/virt-win-reg/priority/{kwargs['priority']}",
                    )
                elif kwargs["action"] == "convert":
                    resp = convert_storage.sync_detailed(
                        client=client,
                        storage_id=kwargs["storage_id"],
                        body=StorageConvertRequest(
                            new_storage_type=kwargs["new_storage_type"],
                            new_storage_status=kwargs.get(
                                "new_storage_status", "downloadable"
                            ),
                            compress=bool(kwargs.get("compress")),
                            priority=kwargs["priority"],
                        ),
                    )
                elif kwargs["action"] == "increase":
                    resp = increase_storage_size.sync_detailed(
                        client=client,
                        storage_id=kwargs["storage_id"],
                        priority=kwargs["priority"],
                        increment=kwargs["increment"],
                    )
                else:
                    return
                raise_for_status(resp)
                response = resp.parsed if hasattr(resp, "parsed") else True
            if response:
                scheduler_client.delete(f"/{kwargs['storage_id']}.stg_action")
        except ApiV4Error as e:
            if e.description_code == "desktops_not_stopped":
                pass
            elif (
                e.description_code in ["storage_not_ready", "storage_not_found"]
                or e.status_code == 400
            ):  ## storage is deleted or kwargs are not valid
                scheduler_client.delete(f"/{kwargs['storage_id']}.stg_action")

    def logs_desktops_old_entries_action_delete_kwargs(**kwargs):
        return []

    def logs_desktops_old_entries_action_delete(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = admin_logs_desktops_delete.sync_detailed(client=client)
            raise_for_status(resp)

    def logs_users_old_entries_action_delete_kwargs(**kwargs):
        return []

    def logs_users_old_entries_action_delete(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = admin_logs_users_delete.sync_detailed(client=client)
            raise_for_status(resp)

    def nonpersistent_delete_timeout(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = delete_desktop.sync_detailed(
                client=client, desktop_id=kwargs["desktop_id"], permanent=True
            )
            raise_for_status(resp)

    def queues_old_tasks_action_delete_kwargs(**kwargs):
        return []

    def queues_old_tasks_action_delete(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = admin_delete_old_tasks_auto.sync_detailed(client=client)
            raise_for_status(resp)

    def retry_failed_tasks_kwargs(**kwargs):
        return []

    def retry_failed_tasks(**kwargs):
        with build_client("isard-scheduler") as client:
            resp = retry_all_failed_tasks.sync_detailed(client=client)
            raise_for_status(resp)
