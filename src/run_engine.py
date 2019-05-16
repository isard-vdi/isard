from gevent.pywsgi import WSGIServer

import logging

from flask import Flask
from logging.handlers import RotatingFileHandler


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

    app.m = ManagerHypervisors()
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
