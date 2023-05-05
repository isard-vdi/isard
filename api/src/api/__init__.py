# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import os
import shutil

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app.STOCK_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/stock")
if not os.path.exists(app.STOCK_CARDS):
    os.makedirs(app.STOCK_CARDS, exist_ok=True)
app.USERS_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/user")
if not os.path.exists(app.USERS_CARDS):
    os.makedirs(app.USERS_CARDS, exist_ok=True)

# Copy only new stock images
stock_folder = os.path.join(APP_ROOT, "static/stock_assets")
for filename in os.listdir(stock_folder):
    if os.path.isfile(os.path.join(app.STOCK_CARDS, filename)):
        if (
            os.stat(os.path.join(stock_folder, filename)).st_mtime
            - os.stat(os.path.join(app.STOCK_CARDS, filename)).st_mtime
            > 1
        ):
            print("Updating stock photo: " + filename)
            shutil.copy2(
                os.path.join(stock_folder, filename),
                os.path.join(app.STOCK_CARDS, filename),
            )
    else:
        print("Adding new stock photo: " + filename)
        shutil.copy(
            os.path.join(stock_folder, filename),
            os.path.join(app.STOCK_CARDS, filename),
        )

# Max upload size
app.config["MAX_CONTENT_LENGTH"] = 1 * 1000 * 1000  # 1 MB

# '''
# App secret key for encrypting cookies
# You can generate one with:
#     import os
#     os.urandom(24)
# And paste it here.
# '''
# app.secret_key = "Change this key!//\xf7\x83\xbe\x17\xfa\xa3zT\n\\]m\xa6\x8bF\xdd\r\xf7\x9e\x1d\x1f\x14'"

# Stores data for external apps poolling in ram
app.ram = {"secrets": {}}

from api.libv2.helpers import InternalUsers

app.internal_users = InternalUsers()

print("Starting isard api...")

from api.libv2.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

from api.libv2.load_validator_schemas import load_validators

app.validators = load_validators()

debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

from flask_socketio import SocketIO

# from flask_cors import CORS
# CORS(app)
# app.config["CORS_HEADERS"] = "application/json"
socketio = SocketIO(
    app,
    path="/api/v3/socket.io/",
    cors_allowed_origins="*",
    logger=debug,
    engineio_logger=debug,
)

import logging as log

"""'
Import all views
"""
# from .views import XmlView
from .views import (
    AdminDomainsView,
    AdminDownloadsView,
    AdminResourcesView,
    AdminStoragePhysicalView,
    AdminStorageView,
    AdminTablesView,
    AdminUsersView,
    AllowedsView,
    CardsView,
    CommonView,
    DesktopsNonPersistentView,
    DesktopsPersistentView,
    HypervisorsView,
    JumperViewerView,
    MediaViews,
    NotifyView,
    PublicView,
    Stats,
    StorageView,
    TemplatesView,
    UsersView,
    VpnViews,
    maintenance,
    storage_node,
    task,
)
from .views.bookings import BookingView, ReservablesView
from .views.deployments import DeploymentsView
