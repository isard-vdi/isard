import json
import threading
import time
import traceback

from api.libv2.deployments.api_deployments import get
from rethinkdb import RethinkDB
from rethinkdb.errors import ReqlDriverError

from api import app

from ... import socketio
from ..flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)


threads = {}
from api.libv2.helpers import _parse_desktop


class BookingsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("bookings").changes(include_initial=False).run(db.conn)
                    ):
                        if self.stop == True:
                            break
                        if c["new_val"] == None:
                            event = "delete"
                            user = c["old_val"]["user_id"]
                            booking = c["old_val"]
                        else:
                            if c["old_val"] == None:
                                event = "add"
                            else:
                                event = "update"
                            user = c["new_val"]["user_id"]
                            # TODO: Check the added booking is editable or not
                            c["new_val"]["editable"] = True
                            booking = c["new_val"]
                        booking["event_type"] = "event"
                        # Format the date fields as strings
                        booking["start"] = booking["start"].strftime("%Y-%m-%dT%H:%M%z")
                        booking["end"] = booking["end"].strftime("%Y-%m-%dT%H:%M%z")
                        # Emit event to user room
                        socketio.emit(
                            "booking_" + event,
                            json.dumps(booking),
                            namespace="/userspace",
                            room=user,
                        )
                        # Emit event to item room
                        app.logger.error("SENDING: bookingitem_" + event)
                        app.logger.error("TO: " + user)
                        socketio.emit(
                            "bookingitem_" + event,
                            json.dumps(booking),
                            namespace="/userspace",
                            room=user,
                        )
                        if booking.get("item_type") == "deployment":
                            deployment = get(booking["item_id"], True)
                            socketio.emit(
                                "deployment_update",
                                json.dumps(deployment),
                                namespace="/userspace",
                                room=user,
                            )
                            for desktop in deployment["desktops"]:
                                socketio.emit(
                                    "desktop_update",
                                    json.dumps(desktop),
                                    namespace="/userspace",
                                    room=desktop["user"],
                                )
                        elif booking.get("item_type") == "desktop":
                            socketio.emit(
                                "desktop_update",
                                json.dumps(
                                    _parse_desktop(
                                        r.table("domains")
                                        .get(booking.get("item_id"))
                                        .run(db.conn)
                                    )
                                ),
                                namespace="/userspace",
                                room=booking.get("user_id"),
                            )
            except ReqlDriverError:
                print("BookingsThread: Rethink db connection lost!")
                app.logger.error("BookingsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("BookingsThread internal error: restarting")
                app.logger.error("BookingsThread internal error: restarting")
                app.logger.error(traceback.format_exc())
                time.sleep(2)


def start_bookings_thread():
    global threads
    if "bookings" not in threads:
        threads["bookings"] = None
    if threads["bookings"] == None:
        threads["bookings"] = BookingsThread()
        threads["bookings"].daemon = True
        threads["bookings"].start()
        app.logger.info("BookingsThread Started")
