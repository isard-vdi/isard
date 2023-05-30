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

app.secret_key = os.environ["WEBAPP_SESSION_SECRET"]

from webapp.lib.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

from .lib.log import *

print("Starting isard webapp...")


"""
Debug should be removed on production!
"""
# ~ app.debug = True
if app.debug:
    log.warning("Debug mode: {}".format(app.debug))
else:
    log.info("Debug mode: {}".format(app.debug))

"""
Authentication types
"""
from .auth import authentication

app.localuser = authentication.LocalUsers()


"""
Serve static files
"""


@app.route("/isard-admin/socketio/<path:path>")
def send_socketio(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/socket.io/client-dist"), path
    )


@app.route("/isard-admin/build/<path:path>")
def send_build(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/gentelella/build"), path
    )


@app.route("/isard-admin/vendors/<path:path>")
def send_vendors(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/gentelella/vendors"), path
    )


@app.route("/isard-admin/templates/<path:path>")
def send_templates(path):
    return send_from_directory(os.path.join(app.root_path, "templates"), path)


@app.route("/isard-admin/bower_components/<path:path>")
def send_bower(path):
    return send_from_directory(os.path.join(app.root_path, "bower_components"), path)


@app.route("/isard-admin/font-linux/<path:path>")
def send_font_linux(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/font-linux/assets"), path
    )


@app.route("/isard-admin/isard_dist/<path:path>")
def send_isardist(path):
    return send_from_directory(os.path.join(app.root_path, "isard_dist"), path)


@app.route("/isard-admin/static/<path:path>")
def send_static_js(path):
    return send_from_directory(os.path.join(app.root_path, "static"), path)


@app.route("/isard-admin/mathjs/<path:path>")
def send_mathjs(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/mathjs/lib/browser"), path
    )


@app.route("/isard-admin/echarts/<path:path>")
def send_echarts(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/echarts"), path
    )


@app.errorhandler(404)
def not_found_error(error):
    return render_template("page_404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("page_500.html"), 500


"""
Import all views
"""
from .views import AdminViews
