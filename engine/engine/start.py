from engine.services.lib.debug import check_if_debugging

check_if_debugging()

import inspect
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler
from subprocess import check_call, check_output

from flask import Flask

## Moved populate & upgrade from webapp
from initdb.populate import Populate
from initdb.upgrade import Upgrade
from pid import PidFile, PidFileAlreadyLockedError, PidFileAlreadyRunningError

check_output(("/isard/generate_certs.sh"), text=True).strip()

try:
    p = Populate()
except Exception as e:
    print(traceback.format_exc())
    print("Error populating...")
    exit(1)

try:
    u = Upgrade()
except Exception as e:
    print(traceback.format_exc())
    print("Error Upgrading...")
    exit(1)
## End

from engine.services.lib.functions import check_tables_populated

check_tables_populated()

from engine.models.engine import Engine
from engine.services import db


def run(app):
    http_server = WSGIServer(("0.0.0.0", 5000), app)
    http_server.serve_forever()


# if app.debug:
#     from werkzeug.debug import DebuggedApplication
#     app.wsgi_app = DebuggedApplication( app.wsgi_app, True )

if __name__ == "__main__":
    p = PidFile("engine")
    try:
        p.create()
    except PidFileAlreadyLockedError:
        import time

        err_pid = PidFile(str(int(time.time())))
        err_pid.create()
        while True:
            time.sleep(1)

    app = Flask(__name__)

    app.m = Engine(with_status_threads=False)
    app.db = db

    # remove default logging for get/post messages
    werk = logging.getLogger("werkzeug")
    werk.setLevel(logging.ERROR)

    # add log handler
    handler = RotatingFileHandler("api.log", maxBytes=10000, backupCount=1)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)

    # register blueprints
    from engine.api import api as api_blueprint

    app.register_blueprint(api_blueprint, url_prefix="")  # url_prefix /api?

    ## DEBUG mode hungs flask endpoint
    # if os.environ.get("LOG_LEVEL") == "DEBUG":
    #     app.run(debug=True, host="0.0.0.0")
    # else:
    app.run(host="0.0.0.0", port=5000)
