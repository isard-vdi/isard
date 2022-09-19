import traceback

from rethinkdb import RethinkDB

from api import app

from .api_exceptions import Error

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import concurrent.futures

from .helpers import _check


class DS:
    def __init__(self):
        None

    def delete_desktop(self, desktop_id, status):
        if status in ["Started", "Shutting-down"]:
            transition_status = "Stopping"
            final_status = "Stopped"
            try:
                self.WaitStatus(
                    desktop_id, status, transition_status, final_status, wait_seconds=20
                )
                status = "Stopped"
            except:
                with app.app_context():
                    r.table("domains").get(desktop_id).update({"status": "Failed"}).run(
                        db.conn
                    )
                    status = "Failed"

        if status in ["Stopped", "Failed"]:
            transition_status = "Deleting"
            final_status = "Deleted"
            try:
                self.WaitStatus(desktop_id, status, transition_status, final_status)
            except:
                with app.app_context():
                    log.error(
                        "Deleting desktop "
                        + str(desktop_id)
                        + " failed (engine timeout?).We will force delete in database."
                    )
                    r.table("domains").get(desktop_id).delete().run(db.conn)
                    return

        log.error(
            "Deleting desktop "
            + str(desktop_id)
            + " failed (engine down?).We will force failed and delete again in database."
        )
        with app.app_context():
            r.table("domains").get(desktop_id).update({"status": "Failed"}).run(db.conn)
        transition_status = "Deleting"
        final_status = "Deleted"

        try:
            self.WaitStatus(desktop_id, "Failed", transition_status, final_status)
        except:
            with app.app_context():
                r.table("domains").get(desktop_id).delete().run(db.conn)

    def delete_non_persistent(self, user_id, template=False):
        ## StoppingAndDeleting all the user's desktops
        if template == False:
            with app.app_context():
                desktops_to_delete = (
                    r.table("domains")
                    .get_all(user_id, index="user")
                    .filter({"persistent": False})
                    .without("create_domain", "xml", "history_domain")
                    .run(db.conn)
                )
        else:
            with app.app_context():
                desktops_to_delete = (
                    r.table("domains")
                    .get_all(user_id, index="user")
                    .filter({"from_template": template, "persistent": False})
                    .without("create_domain", "xml", "history_domain")
                    .run(db.conn)
                )
        for desktop in desktops_to_delete:
            self.delete_desktop(desktop["id"], desktop["status"])

    def WaitStatus(
        self,
        desktop_id,
        original_status,
        transition_status,
        final_status,
        wait_seconds=10,
    ):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda p: self._wait_for_domain_status(*p),
                [
                    desktop_id,
                    original_status,
                    transition_status,
                    final_status,
                    wait_seconds,
                ],
            )
        result = future.result()

    def _wait_for_domain_status(
        self,
        desktop_id,
        original_status,
        transition_status,
        final_status,
        wait_seconds=10,
    ):
        with app.app_context():
            # Prepare changes
            if final_status == "Deleted":
                changestatus = (
                    r.table("domains")
                    .get(desktop_id)
                    .changes()
                    .filter({"new_val": None})
                    .run(db.conn)
                )
            elif final_status == "Started":
                changestatus = (
                    r.table("domains")
                    .get(desktop_id)
                    .changes()
                    .filter({"new_val": {"status": final_status}})
                    .has_fields(
                        {"new_val": {"viewer": {"tls": {"host-subject": True}}}}
                    )
                    .run(db.conn)
                )
            else:
                changestatus = (
                    r.table("domains")
                    .get(desktop_id)
                    .changes()
                    .filter({"new_val": {"status": final_status}})
                    .run(db.conn)
                )

            # Start transition
            if transition_status != "Any":
                status = (
                    r.table("domains")
                    .get(desktop_id)
                    .update({"status": transition_status})
                    .run(db.conn)
                )

                if _check(status, "replaced") == False:
                    raise Error(
                        "precondition_required",
                        "Desktop transition initial status incorrect",
                        traceback.format_exc(),
                        description_code="desktop_transition_initial_status_incorrect",
                    )

            # Get change
            try:
                with app.app_context():
                    real_final_status = (
                        r.table("domains")
                        .get(desktop_id)
                        .pluck("status")
                        .default(None)
                        .run(db.conn)
                    )
                if not real_final_status or real_final_status == final_status:
                    return
                doc = changestatus.next(wait=wait_seconds)
            except ReqlTimeoutError:
                raise Error(
                    "gateway_timeout",
                    "Unable to change desktop status.",
                    traceback.format_exc(),
                    description_code="unable_to_change_desktop_status",
                )
            if final_status != "Deleted":
                if doc["new_val"]["status"] != final_status:
                    raise Error(
                        "gateway_timeout",
                        "Unable to change desktop status.",
                        traceback.format_exc(),
                        description_code="unable_to_change_desktop_status",
                    )

    def WaitHyperStatus(
        self, hyper_id, original_status, transition_status, final_status
    ):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                lambda p: self._wait_for_hyper_status(*p),
                [hyper_id, original_status, transition_status, final_status],
            )
        result = future.result()

    def _wait_for_hyper_status(
        self, hyper_id, original_status, transition_status, final_status
    ):
        with app.app_context():
            # Prepare changes
            if final_status == "Deleted":
                changestatus = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .changes()
                    .filter({"new_val": None})
                    .run(db.conn)
                )
            elif final_status == "Started":
                changestatus = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .changes()
                    .filter({"new_val": {"status": final_status}})
                    .has_fields(
                        {"new_val": {"viewer": {"tls": {"host-subject": True}}}}
                    )
                    .run(db.conn)
                )
            else:
                changestatus = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .changes()
                    .filter({"new_val": {"status": final_status}})
                    .run(db.conn)
                )

            # Start transition
            if transition_status != "Any":
                status = (
                    r.table("hypervisors")
                    .get(hyper_id)
                    .update({"status": transition_status})
                    .run(db.conn)
                )

                if _check(status, "replaced") == False:
                    raise Error(
                        "precondition_required",
                        "Hypervisor transition initial status incorrect",
                        traceback.format_exc(),
                        description_code="hypervisor_transition_initial_status_incorrect",
                    )

            # Get change
            try:
                doc = changestatus.next(wait=5)
            except ReqlTimeoutError:
                raise Error(
                    "gateway_timeout",
                    "Unable to change hypervisor status.",
                    traceback.format_exc(),
                    description_code="unable_to_change_hypervisor_status",
                )
            if final_status != "Deleted":
                if doc["new_val"]["status"] != final_status:
                    raise Error(
                        "gateway_timeout",
                        "Unable to change hypervisor status.",
                        traceback.format_exc(),
                        description_code="unable_to_change_hypervisor_status",
                    )

    def _check(self, dict, action):
        """
        These are the actions:
        {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        """
        if dict[action]:
            return True
        if not dict["errors"]:
            return True
        return False
