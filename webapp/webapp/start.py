#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

import os

from eventlet import monkey_patch

monkey_patch()

from flask_socketio import SocketIO
from rethinkdb import RethinkDB
from webapp.lib.flask_rethink import RDB

from webapp import app

r = RethinkDB()
db = RDB(app)
db.init_app(app)

socketio = SocketIO(app)


## Main
if __name__ == "__main__":
    import logging

    logger = logging.getLogger("socketio")
    logger.setLevel("ERROR")
    engineio_logger = logging.getLogger("engineio")
    engineio_logger.setLevel("ERROR")

    debug = os.environ.get("USAGE", "production") == "devel"

    socketio.run(
        app, host="0.0.0.0", port=5000, debug=debug
    )  # , logger=logger, engineio_logger=engineio_logger)
