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

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

app.secret_key = os.environ["WEBAPP_SESSION_SECRET"]

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


@app.route("/isard-admin/fancytree/<path:path>")
def send_fancytree(path):
    return send_from_directory(
        os.path.join(app.root_path, "node_modules/jquery.fancytree"), path
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
