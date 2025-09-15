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
import secrets

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

# Generate a random session secret key at startup (in-memory only)
app.secret_key = secrets.token_bytes(32)

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


@app.route("/isard-admin/vendors/<path:path>")
def send_vendors(path):
    return send_from_directory(os.path.join(app.root_path, "node_modules"), path)


@app.route("/isard-admin/templates/<path:path>")
def send_templates(path):
    return send_from_directory(os.path.join(app.root_path, "templates"), path)


@app.route("/isard-admin/static/<path:path>")
def send_static_js(path):
    return send_from_directory(os.path.join(app.root_path, "static"), path)


@app.errorhandler(404)
def not_found_error(error):
    return render_template("page_404.html"), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template("page_500.html"), 500


"""
Import all views
"""
from .views import AdminBackupsWebView, AdminViews
