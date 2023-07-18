from api._common.domain import Domain
from rethinkdb import RethinkDB

from api import app

from .._common.api_exceptions import Error

r = RethinkDB()
import time
import traceback

from .bookings.api_booking import Bookings
from .flask_rethink import RDB

apib = Bookings()

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


def wait_delete_status(desktop_id, wait_seconds=0, interval_seconds=2):
    seconds = 0
    while seconds <= wait_seconds:
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
                return True
    raise Error(
        "internal_server",
        "Engine could not delete " + desktop_id + " in " + str(wait_seconds),
        traceback.format_exc(),
        description_code="generic_error",
    )


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
                traceback.format_exc(),
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
                {"status": "Starting", "accessed": int(time.time())},
                return_changes=True,
            )
            .run(db.conn)
        )
        if not len(domain.get("changes", [])):
            return "Starting"
        if domain.get("changes", [{}])[0].get("new_val", {}).get("viewer"):
            r.table("domains").get(desktop_id).replace(r.row.without("viewer")).run(
                db.conn
            )

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
                {"status": new_status, "accessed": int(time.time())}
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
        "Desktop can't be stopped from " + status,
        traceback.format_exc(),
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


def desktop_delete(desktop_id, from_started=False, wait_seconds=0):
    status = get_desktop_status(desktop_id)
    if status == "Deleting":
        return True
    if from_started:
        # TODO: Engine should implement StoppingAndDeleting
        status = desktop_stop(desktop_id, force=True, wait_seconds=60)

    if status in ["Stopped", "Failed"]:
        with app.app_context():
            apib.delete_item_bookings("desktop", desktop_id)
            r.table("domains").get(desktop_id).update(
                {"status": "Deleting", "accessed": int(time.time())}
            ).run(db.conn)
    else:
        raise Error(
            "precondition_required",
            "Unable to delete desktop " + desktop_id + " in status " + status,
            traceback.format_exc(),
            description_code="unable_to_delete_desktop_from",
        )
    if wait_seconds:
        wait_delete_status(desktop_id, wait_seconds=wait_seconds)
    return True


def desktops_delete(desktops_ids, force=False):
    for desktop_id in desktops_ids:
        with app.app_context():
            r.table("bookings").get_all(
                ["desktop", desktop_id], index="item_type-id"
            ).delete().run(db.conn)
    if force:
        with app.app_context():
            r.table("domains").get_all(r.args(desktops_ids)).update(
                {"status": "ForceDeleting"}
            ).run(db.conn)
    else:
        with app.app_context():
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Stopped"}
            ).update({"status": "Deleting", "accessed": int(time.time())}).run(db.conn)
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": "Failed"}
            ).update({"status": "Deleting", "accessed": int(time.time())}).run(db.conn)


def template_delete(template_id):
    with app.app_context():
        r.table("domains").get(template_id).update(
            {"status": "Deleting", "accessed": int(time.time())}
        ).run(db.conn)


def templates_delete(templates_ids, force=False):
    if force:
        with app.app_context():
            r.table("domains").get_all(r.args(templates_ids)).filter(
                {"kind": "template"}
            ).update({"status": "ForceDeleting", "accessed": int(time.time())}).run(
                db.conn
            )
    else:
        with app.app_context():
            r.table("domains").get_all(r.args(templates_ids), index="id").filter(
                {"kind": "template"}
            ).update({"status": "Deleting", "accessed": int(time.time())}).run(db.conn)


def desktops_non_persistent_delete(user_id, template=False):
    if template == False:
        with app.app_context():
            r.table("domains").get_all(user_id, index="user").filter(
                {"persistent": False}
            ).update({"status": "ForceDeleting"}).run(db.conn)
    else:
        with app.app_context():
            r.table("domains").get_all(user_id, index="user").filter(
                {"from_template": template, "persistent": False}
            ).update({"status": "ForceDeleting"}).run(db.conn)
