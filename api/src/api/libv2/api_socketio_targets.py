#
#   Copyright © 2025 Pau Abril Iranzo
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


import json
import threading
import time
import traceback

from rethinkdb import RethinkDB
from rethinkdb.errors import ReqlDriverError

from api import app

from .. import socketio
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

threads = {}


class TargetsThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.stop = False

    def run(self):
        while True:
            try:
                with app.app_context():
                    for c in (
                        r.table("targets")
                        .changes(include_initial=False)
                        .run(db.connect())
                    ):
                        if self.stop is True:
                            break
                        if c["new_val"] is None:
                            event = "delete"
                            user = c["old_val"]["user_id"]
                            deployment = {"id": c["old_val"]["id"]}
                        elif c["old_val"] is None:
                            event = "add"
                            user = c["new_val"]["user_id"]
                            deployment = c["new_val"]
                        else:
                            event = "update"
                            user = c["new_val"]["user_id"]
                            deployment = c["new_val"]

                        socketio.emit(
                            "targets_" + event,
                            json.dumps(deployment),
                            namespace="/userspace",
                            room=user,
                        )

            except ReqlDriverError:
                print("TargetsThread: Rethink db connection lost!")
                app.logger.error("TargetsThread: Rethink db connection lost!")
                time.sleep(0.5)
            except Exception:
                print("TargetsThread internal error: restarting")
                app.logger.error("TargetsThread internal error: restarting")
                app.logger.error(traceback.format_exc())
                time.sleep(0.5)

        print("TargetsThread ENDED!!!!!!!")
        app.logger.error("TargetsThread ENDED!!!!!!!")


def start_targets_thread():
    global threads
    if "targets" not in threads:
        threads["targets"] = None
    if threads["targets"] is None:
        threads["targets"] = TargetsThread()
        threads["targets"].daemon = True
        threads["targets"].start()
        app.logger.info("TargetsThread Started")
