from isardvdi_common.api_exceptions import Error
from isardvdi_common.domain import Domain
from rethinkdb import RethinkDB

from api import app

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
        with app.app_context():
            try:
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


def get_desktop_status(desktop_id):
    with app.app_context():
        try:
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
                description_code="not_found",
            )
    return status


def desktop_start(desktop_id, wait_seconds=0, paused=False):
    status = get_desktop_status(desktop_id)
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
    with app.app_context():
        domain = (
            r.table("domains")
            .get(desktop_id)
            .update(
                {"status": "Starting", "viewer": {}, "accessed": int(time.time())},
                return_changes=True,
            )
            .run(db.conn)
        )
        if not len(domain.get("changes", [])):
            return "Starting"

    return wait_status(desktop_id, "Starting", wait_seconds=wait_seconds)


def desktops_start(desktops_ids, wait_seconds=0, paused=False):
    with app.app_context():
        desktops = list(
            r.table("domains")
            .get_all(r.args(desktops_ids), index="id")
            .pluck("id", "status")
            .run(db.conn)
        )
        desktops_ok = [
            desktop["id"]
            for desktop in desktops
            if desktop["status"] in ["Stopped", "Failed"]
        ]
        with app.app_context():
            new_status = "Starting" if not paused else "StartingPaused"
            r.table("domains").get_all(r.args(desktops_ok)).update(
                {"status": new_status, "viewer": {}, "accessed": int(time.time())}
            ).run(db.conn)


def desktop_stop(desktop_id, force=False, wait_seconds=0):
    status = get_desktop_status(desktop_id)
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


def desktops_stop(desktops_ids, force=False, wait_seconds=30):
    if force:
        with app.app_context():
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Shutting-down"}
            ).update({"status": "Stopping", "accessed": int(time.time())}).run(db.conn)
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Started"}
            ).update({"status": "Stopping", "accessed": int(time.time())}).run(db.conn)
    else:
        with app.app_context():
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Shutting-down"}
            ).update({"status": "Stopping", "accessed": int(time.time())}).run(db.conn)
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Started"}
            ).update({"status": "Shutting-down", "accessed": int(time.time())}).run(
                db.conn
            )


def desktops_stop_all():
    with app.app_context():
        r.table("domains").get_all("Shutting-down", index="status").update(
            {"status": "Stopping", "accessed": int(time.time())}
        ).run(db.conn)
        r.table("domains").get_all("Started", index="status").update(
            {"status": "Stopping", "accessed": int(time.time())}
        ).run(db.conn)


def desktop_reset(desktop_id):
    status = get_desktop_status(desktop_id)
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
    tag = r.table("domains").get(desktop_id)["tag"].default(False).run(db.conn)
    rcb = RecycleBinDesktop(user_id=agent_id)
    rcb.add(desktop_id)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if permanent or tag or max_time == "0":
        rcb.delete_storage(agent_id)


def desktops_delete(agent_id, desktops_ids, permanent=False):
    rcb = RecycleBinBulk(user_id=agent_id)
    rcb.add(desktops_ids)

    max_time = get_recicle_delete_time(agent_id)
    # Checks if recycle bin time is set to be immediately deleted and perform a permanent delete
    if max_time == "0" or permanent:
        rcb.delete_storage(agent_id)


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
