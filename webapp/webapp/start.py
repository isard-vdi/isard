import os

from eventlet import monkey_patch

monkey_patch()

from flask_socketio import SocketIO
from webapp.lib.flask_rethink import RethinkDB

from webapp import app

db = RethinkDB(app)
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
