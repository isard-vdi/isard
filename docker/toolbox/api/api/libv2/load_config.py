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

import logging as log
import os
import time
import traceback

from api import app


class loadConfig:
    def __init__(self, app=None):
        None

    def init_app(self, app):
        try:
            app.config.setdefault("LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
            app.config.setdefault("LOG_FILE", "isard-toolbox.log")
            app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

        except:
            log.error(traceback.format_exc())
            log.error("Missing parameters!")
            print("Missing parameters!")
            return False
        print("Initial configuration loaded...")
        return True
