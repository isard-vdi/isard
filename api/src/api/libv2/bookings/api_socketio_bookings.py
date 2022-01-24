import json
import time
import traceback

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from rethinkdb.errors import ReqlDriverError

from ..flask_rethink import RDB
from ..log import log

db = RDB(app)
db.init_app(app)

import threading

from ... import socketio

threads = {}


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
                        if c["new_val"] == None:
                            event = "delete"
                            user = c["old_val"]["user_id"]
                            booking = c["old_val"]
                        elif c["old_val"] == None:
                            event = "add"
                            user = c["new_val"]["user_id"]
                            # TODO: Check the added booking is editable or not
                            c["new_val"]["editable"] = True
                            booking = c["new_val"]
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
                        log.error("SENDING: bookingitem_" + event)
                        log.error("TO: bookingsitem_" + booking["item_id"])
                        socketio.emit(
                            "bookingitem_" + event,
                            json.dumps(booking),
                            namespace="/userspace",
                            room=user,
                        )
                        # Emit event to summary room
                        socketio.emit(
                            "bookingitem_" + event,
                            json.dumps(booking),
                            namespace="/userspace",
                            room=user,
                        )
            except ReqlDriverError:
                print("BookingsThread: Rethink db connection lost!")
                log.error("BookingsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("BookingsThread internal error: restarting")
                log.error("BookingsThread internal error: restarting")
                log.error(traceback.format_exc())
                time.sleep(2)


def start_bookings_thread():
    global threads
    if "bookings" not in threads:
        threads["bookings"] = None
    if threads["bookings"] == None:
        threads["bookings"] = BookingsThread()
        threads["bookings"].daemon = True
        threads["bookings"].start()
        log.info("BookingsThread Started")
