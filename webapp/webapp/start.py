from eventlet import monkey_patch

monkey_patch()

from flask_socketio import SocketIO
from webapp.lib import api
from webapp.lib.flask_rethink import RethinkDB

from webapp import app

db = RethinkDB(app)
db.init_app(app)

socketio = SocketIO(app)

app.isardapi = api.isard()

from webapp.lib import isardSocketio

## Main
if __name__ == "__main__":
    # Start socketio threads
    isardSocketio.start_domains_thread()
    isardSocketio.start_users_thread()
    isardSocketio.start_media_thread()
    isardSocketio.start_hypervisors_thread()
    isardSocketio.start_config_thread()
    isardSocketio.start_resources_thread()

    import logging

    logger = logging.getLogger("socketio")
    # level = logging.getLevelName('ERROR')
    logger.setLevel("ERROR")
    engineio_logger = logging.getLogger("engineio")
    engineio_logger.setLevel("ERROR")

    socketio.run(
        app, host="0.0.0.0", port=5000, debug=False
    )  # , logger=logger, engineio_logger=engineio_logger)
