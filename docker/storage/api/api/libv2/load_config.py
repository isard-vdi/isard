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
import time
import traceback

from isardvdi_common.api_rest import ApiRest

from api import app


def wait_for_api(app):
    api_rest = ApiRest("isard-api")
    app.logger.info("Check connection to api")
    api_conection = False
    while not api_conection:
        try:
            api_rest.get("")
            api_conection = True
        except:
            app.logger.debug(traceback.format_exc())
            time.sleep(1)


def setup_app(app):
    try:
        app.config.setdefault("LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
        app.config.setdefault("LOG_FILE", "isard-storage.log")
        app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

    except:
        app.logger.error(traceback.format_exc())
        app.logger.error("Missing parameters!")
        return False
    app.logger.info("Initial configuration loaded...")
    return True
