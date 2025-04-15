import json
import threading
import time
import traceback

from rethinkdb import RethinkDB
from rethinkdb.errors import ReqlDriverError

from api import app

from ... import socketio
from ..flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)


threads = {}


class PlanningsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("resource_planner")
                        .changes(include_initial=False)
                        .run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            event = "delete"
                            plan = c["old_val"]
                        elif c["old_val"] == None:
                            event = "add"
                            plan = c["new_val"]
                        else:
                            event = "update"
                            plan = c["new_val"]
                        # Format the date fields as strings
                        plan["start"] = plan["start"].strftime("%Y-%m-%dT%H:%M%z")
                        plan["end"] = plan["end"].strftime("%Y-%m-%dT%H:%M%z")
                        # Emit event to user room
                        socketio.emit(
                            "plan_" + event,
                            json.dumps(plan),
                            namespace="/userspace",
                            room=plan["user_id"],
                        )
            except ReqlDriverError:
                print("PlanningsThread: Rethink db connection lost!")
                app.logger.error("PlanningsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("PlanningsThread internal error: restarting")
                app.logger.error("PlanningsThread internal error: restarting")
                app.logger.error(traceback.format_exc())
                time.sleep(0.5)


def start_plannings_thread():
    global threads
    if "plannings" not in threads:
        threads["plannings"] = None
    if threads["plannings"] == None:
        threads["plannings"] = PlanningsThread()
        threads["plannings"].daemon = True
        threads["plannings"].start()
        app.logger.info("PlanningsThread Started")
