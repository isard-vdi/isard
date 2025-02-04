from api.libv2.api_notify import notify_admins
from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from isardvdi_common.domain import Domain
from rethinkdb import RethinkDB

from api import app

from .caches import get_document

r = RethinkDB()
import time
import traceback

from api.libv2.recycle_bin import (
    RecycleBinBulk,
    RecycleBinCategory,
    RecycleBinDeployment,
    RecycleBinDeploymentDesktops,
    RecycleBinDesktop,
    RecycleBinGroup,
    RecycleBinTemplate,
    RecycleBinUser,
    get_recicle_delete_time,
)

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


@cached(cache=TTLCache(maxsize=20, ttl=30))
def get_qos_disks():
    with app.app_context():
        qos_disks = list(r.table("qos_disk").pluck("id", "allowed").run(db.conn))
    return qos_disks


def get_desktop_qos_disk_id(desktop):
    qos_disks = get_qos_disks()
    for qos_disk in qos_disks:
        if qos_disk["allowed"]["roles"] == []:
            return qos_disk["id"]
    for qos_disk in qos_disks:
        if (
            qos_disk["allowed"]["roles"]
            and desktop["role_id"] in qos_disk["allowed"]["roles"]
        ):
            return qos_disk["id"]
    return False


def wait_status(
    desktop_id, current_status, wait_seconds=0, interval_seconds=2, raise_exc=True
):
    if wait_seconds == 0:
        return current_status
    seconds = 0
    status = current_status
    while status == current_status and seconds <= wait_seconds:
        time.sleep(interval_seconds)
        seconds += interval_seconds
        try:
            with app.app_context():
                status = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status")["status"]
                    .run(db.conn)
                )
        except:
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


def get_desktop(desktop_id):
    try:
        # For desktop events better do not cache it's status
        with app.app_context():
            domain = (
                r.table("domains")
                .get(desktop_id)
                .pluck("status", "create_dict", "user")
                .run(db.conn)
            )
        return {
            "status": domain["status"],
            "role_id": get_document("users", domain["user"], ["role"]),
            "qos_disk_id": domain["create_dict"]["hardware"].get("qos_disk_id", False),
        }
    except:
        raise Error(
            "not_found",
            "Desktop not found",
            description_code="not_found",
        )


def desktop_start(desktop_id, wait_seconds=0, paused=False):
    domain = get_desktop(desktop_id)
    status = domain["status"]
    if status in ["Started", "Starting", "StartingPaused", "CreatingAndStarting"]:
        return True
    if status not in ["Stopped", "Failed"]:
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
    qos_disk_id = get_desktop_qos_disk_id(domain)
    with app.app_context():
        domain = (
            r.table("domains")
            .get(desktop_id)
            .update(
                {
                    "status": "Starting",
                    "viewer": {},
                    "accessed": int(time.time()),
                    "create_dict": {"hardware": {"qos_disk_id": qos_disk_id}},
                },
                return_changes=True,
            )
            .run(db.conn)
        )
    if not len(domain.get("changes", [])):
        return "Starting"

    return wait_status(desktop_id, "Starting", wait_seconds=wait_seconds)


def desktops_start(desktops_ids, paused=False, batch_size=15, wait_seconds=3):
    action = "start"
    desktops_ok = []
    try:
        new_status = "Starting" if not paused else "StartingPaused"
        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            keys = [["desktop", d_id] for d_id in batch_ids]
            with app.app_context():
                desktops_ok.extend(
                    list(
                        r.table("domains")
                        .get_all(*keys, index="kind_ids")
                        .filter(
                            (
                                (r.row["status"] == "Stopped")
                                | (r.row["status"] == "Failed")
                            )
                        )
                        .run(db.conn)
                    )
                )
            time.sleep(wait_seconds)
        for desktop in desktops_ok:
            qos_disk_id = get_desktop_qos_disk_id(desktop) if not paused else False
            with app.app_context():
                r.table("domains").get(desktop["id"]).update(
                    {
                        "status": new_status,
                        "viewer": {},
                        "accessed": int(time.time()),
                        "create_dict": {"hardware": {"qos_disk_id": qos_disk_id}},
                    }
                ).run(db.conn)
                notify_admins(
                    "desktop_action",
                    {
                        "action": action,
                        "count": len(desktops_ids),
                        "status": "completed",
                    },
                )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def desktop_stop(desktop_id, force=False, wait_seconds=0):
    domain = get_desktop(desktop_id)
    status = domain["status"]
    if status in ["Stopped", "Stopping", "Failed"]:
        return status
    if status == "Started":
        if not force:
            with app.app_context():
                r.table("domains").get(desktop_id).update(
                    {"status": "Shutting-down", "accessed": int(time.time())}
                ).run(db.conn)
            return wait_status(desktop_id, "Shutting-down", wait_seconds=wait_seconds)
        else:
            with app.app_context():
                r.table("domains").get(desktop_id).update(
                    {"status": "Stopping", "accessed": int(time.time())}
                ).run(db.conn)
            return wait_status(desktop_id, "Stopping", wait_seconds=wait_seconds)
    if status == "Shutting-down":
        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"status": "Stopping", "accessed": int(time.time())}
            ).run(db.conn)
        return wait_status(desktop_id, "Stopping", wait_seconds=wait_seconds)
    if status == "Paused":
        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"status": "Stopped", "accessed": int(time.time())}
            ).run(db.conn)
        return wait_status(desktop_id, "Stopped", wait_seconds=wait_seconds)

    raise Error(
        "precondition_required",
        f"Desktop {desktop_id} can't be stopped from {status}",
        description_code="unable_to_stop_desktop_from",
    )


def desktops_stop(
    desktops_ids, force=False, include_shutting_down=True, batch_size=20, wait_seconds=1
):
    action = "stop"
    try:
        status_updates = []

        if include_shutting_down:
            status_updates.append(("Shutting-down", "Stopping"))
        if force:
            status_updates.append(("Started", "Stopping"))
        else:
            status_updates.append(("Started", "Shutting-down"))

        with app.app_context():
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                keys = [["desktop", d_id] for d_id in batch_ids]
                for current_status, new_status in status_updates:
                    r.table("domains").get_all(*keys, index="kind_ids").filter(
                        {"status": current_status}
                    ).update({"status": new_status, "accessed": int(time.time())}).run(
                        db.conn
                    )
            time.sleep(wait_seconds)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def desktop_reset(desktop_id):
    domain = get_desktop(desktop_id)
    status = domain["status"]
    if status not in ["Started", "Shutting-down", "Suspended", "Stopping"]:
        raise Error(
            "precondition_required",
            "Desktop can't be resetted from " + status,
            traceback.format_exc(),
            description_code="unable_to_start_desktop_from",
        )
    with app.app_context():
        r.table("domains").get(desktop_id).update(
            {"status": "Resetting", "accessed": int(time.time())}
        ).run(db.conn)


def desktop_delete(desktop_id, agent_id, permanent=False):
    with app.app_context():
        tag = r.table("domains").get(desktop_id)["tag"].default(False).run(db.conn)
    rcb = RecycleBinDesktop(user_id=agent_id)
    rcb.add(desktop_id)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if permanent or tag or max_time == "0":
        rcb.delete_storage(agent_id)


def desktops_delete(agent_id, desktops_ids, permanent=False):
    action = "delete"
    try:
        rcb = RecycleBinBulk(user_id=agent_id)
        rcb.add(desktops_ids)

        max_time = get_recicle_delete_time(agent_id)
        # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
        if max_time == "0" or permanent:
            rcb.delete_storage(agent_id)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def deployment_delete(deployment_id, agent_id, permanent=False):
    rcb = RecycleBinDeployment(user_id=agent_id)
    rcb.add(deployment_id)

    max_time = get_recicle_delete_time(agent_id)
    if max_time == "0" or permanent:
        rcb.delete_storage(agent_id)


def deployment_delete_desktops(agent_id, desktops_ids, permanent=False):
    rcb = RecycleBinDeploymentDesktops(user_id=agent_id)
    rcb.add(desktops_ids)

    max_time = get_recicle_delete_time(agent_id)
    if max_time == "0" or permanent:
        rcb.delete_storage(agent_id)


def user_delete(agent_id, user_id, delete_user=True):
    rcb = RecycleBinUser(user_id=agent_id)
    rcb.add(user_id, delete_user)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if max_time == "0":
        rcb.delete_storage(agent_id)


def group_delete(agent_id, group_id):
    rcb = RecycleBinGroup(user_id=agent_id)
    rcb.add(group_id)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if max_time == "0":
        rcb.delete_storage(agent_id)


def category_delete(agent_id, category_id):
    rcb = RecycleBinCategory(user_id=agent_id)
    rcb.add(category_id)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if max_time == "0":
        rcb.delete_storage(agent_id)


def templates_delete(template_id, agent_id):
    rcb = RecycleBinTemplate(user_id=agent_id)
    rcb.add(template_id=template_id)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if max_time == "0":
        rcb.delete_storage(agent_id)


def desktops_non_persistent_delete(user_id, template):
    with app.app_context():
        r.table("domains").get_all(user_id, index="user").filter(
            {"from_template": template, "persistent": False}
        ).update({"status": "ForceDeleting"}).run(db.conn)


def desktop_non_persistent_delete(desktop_id):
    with app.app_context():
        r.table("domains").get(desktop_id).update({"status": "ForceDeleting"}).run(
            db.conn
        )


def desktop_updating(desktop_id):
    with app.app_context():
        r.table("domains").get(desktop_id).update({"status": "Updating"}).run(db.conn)


def desktops_force_failed(desktops_ids, batch_size=100):
    action = "force_failed"
    try:
        with app.app_context():
            for i in range(0, len(desktops_ids), batch_size):
                batch_ids = desktops_ids[i : i + batch_size]
                keys = [["desktop", d_id] for d_id in batch_ids]
                if (
                    r.table("domains")
                    .get_all(*keys, index="kind_ids")
                    .filter(
                        lambda item: r.expr(
                            ["Stopped", "Started", "Downloading", "Shutting-down"]
                        ).contains(item["status"])
                    )
                    .count()
                    .run(db.conn)
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
                ).run(db.conn)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def desktops_toggle(desktops_ids, force=False, batch_size=100):
    action = "toggle"
    desktops_to_start = []
    desktops_to_stop = []

    try:
        # Classification by status
        for desktop_id in desktops_ids:
            with app.app_context():
                current_status = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("status")
                    .run(db.conn)["status"]
                )
            if current_status in ["Stopped", "Failed"]:
                desktops_to_start.append(desktop_id)
            elif current_status in ["Started"]:
                desktops_to_stop.append(desktop_id)

        desktops_stop(desktops_to_stop, force=force, include_shutting_down=False)
        desktops_start(desktops_to_start)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def remove_forced_hyper(desktops_ids, batch_size=100):
    action = "remove_forced_hyper"
    try:
        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"forced_hyp": False}
                ).run(db.conn)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def remove_favourite_hyper(desktops_ids, batch_size=100):
    action = "remove_favourite_hyper"
    try:
        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"favourite_hyp": False}
                ).run(db.conn)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def activate_autostart(desktops_ids, batch_size=100):
    action = "activate_autostart"
    try:
        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).filter(
                    {"server": True}
                ).update({"server_autostart": True}).run(db.conn)
        notify_admins(
            "desktop_action",
            {"action": action, "count": len(desktops_ids), "status": "completed"},
        )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )


def deactivate_autostart(desktops_ids, batch_size=100):
    action = "deactivate_autostart"
    try:
        for i in range(0, len(desktops_ids), batch_size):
            batch_ids = desktops_ids[i : i + batch_size]
            with app.app_context():
                r.table("domains").get_all(r.args(batch_ids)).update(
                    {"server_autostart": False}
                ).run(db.conn)
            notify_admins(
                "desktop_action",
                {"action": action, "count": len(desktops_ids), "status": "completed"},
            )
    except Error as e:
        app.logger.error(e)
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
        app.logger.error(traceback.format_exc())
        notify_admins(
            "desktop_action",
            {
                "action": action,
                "count": len(desktops_ids),
                "msg": "Something went wrong",
                "status": "failed",
            },
        )
