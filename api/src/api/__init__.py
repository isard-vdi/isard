# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

import os

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

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

import os

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
    AdminUsersView,
    CommonView,
    DeploymentsView,
    DesktopsNonPersistentView,
    DesktopsPersistentView,
    DownloadsView,
    HypervisorsView,
    JumperViewerView,
    PublicView,
    TemplatesView,
    UsersView,
)
