from engine.services.lib.debug import check_if_debugging
check_if_debugging()

from gevent.pywsgi import WSGIServer

import os, sys
import logging

from flask import Flask
from logging.handlers import RotatingFileHandler

## Moved populate & upgrade from webapp
from initdb.populate import Populate
from initdb.upgrade import Upgrade
import traceback

try:
    p=Populate()
except Exception as e:
    print(traceback.format_exc())
    print('Error populating...')
    exit(1)

try:
    u=Upgrade()
except Exception as e:
    print(traceback.format_exc())
    print('Error Upgrading...')
    exit(1)
## End

from engine.services.lib.functions import check_tables_populated
check_tables_populated()

from engine.services import db
from engine.models.manager_hypervisors import ManagerHypervisors


def run(app):
    http_server = WSGIServer(("0.0.0.0", 5555), app)
    http_server.serve_forever()


# if app.debug:
#     from werkzeug.debug import DebuggedApplication
#     app.wsgi_app = DebuggedApplication( app.wsgi_app, True )

if __name__ == "__main__":

    app = Flask(__name__)

    #app.m = ManagerHypervisors()
    app.m = ManagerHypervisors(with_status_threads=False)
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

    run(app)
