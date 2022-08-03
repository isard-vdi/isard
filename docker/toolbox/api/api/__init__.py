#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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
import shutil

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

# Max upload size
app.config["MAX_CONTENT_LENGTH"] = 1 * 1000 * 1000  # 1 MB

print("Starting toolbox api...")

from api.libv2.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

from api.libv2.load_validator_schemas import load_validators

app.validators = load_validators()


import logging as log

"""'
Import all views
"""
# from .views import XmlView
from .views import StorageView
