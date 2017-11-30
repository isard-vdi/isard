import logging

from flask import Flask
from logging.handlers import RotatingFileHandler




from engine.models.manager_hypervisors import ManagerHypervisors
from engine.services import db
from engine.services.lib.functions import check_tables_populated

app = Flask(__name__)
check_tables_populated()
app.m = ManagerHypervisors()
app.db = db

#remove default logging for get/post messages
werk = logging.getLogger('werkzeug')
werk.setLevel(logging.ERROR)

#add log handler
handler = RotatingFileHandler('api.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# register blueprints
from engine.api import api as api_blueprint

app.register_blueprint(api_blueprint, url_prefix='')  # url_prefix /api?
