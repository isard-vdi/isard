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
from importlib.machinery import SourceFileLoader
from logging.config import dictConfig

from flask import Flask
from flask_cors import CORS

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "format": "%(asctime)s.%(msecs)03d, %(levelname)s, %(message)s",
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
            }
        },
        "root": {"handlers": ["stdout"], "level": os.getenv("LOG_LEVEL", "INFO")},
    }
)

app = Flask(__name__, static_url_path="")
CORS(app)
app.url_map.strict_slashes = False

# Max upload size
app.config["MAX_CONTENT_LENGTH"] = 1 * 1000 * 1000  # 1 MB

print("Starting storage api...")

from api.libv2.load_config import setup_app
from isardvdi_common.api_rest import ApiRest

ApiRest().wait_for()

if not setup_app(app):
    app.logger.error("Unable to initialize app config. Exitting.")
    exit(0)

from api.libv2.load_validator_schemas import load_validators

app.validators = load_validators()

"""'
Import all views
"""
from .views import StorageView, check
