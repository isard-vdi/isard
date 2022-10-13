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

from api import app


class StructuredMessage(object):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        if isinstance(self.message, str):
            return "%s" % (self.message)

        message = "%s - %s" % (
            self.message["msg"],
            self.message["description"],
        )
        if LOG_LEVEL in ["INFO", "WARNING"]:
            return message
        if LOG_LEVEL == "ERROR":
            return "%s - %s - %s" % (
                message,
                self.message["function_call"],
                self.message["function"],
            )
        if LOG_LEVEL == "DEBUG":
            return "%s - %s - %s\r\n%s\r\n%s" % (
                message,
                self.message["function"],
                self.message["function_call"],
                self.message["debug"],
                self.message["request"],
                self.message["data"],
            )


app.sm = StructuredMessage

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
log.basicConfig(
    level=LOG_LEVEL_NUM, format="%(asctime)s - %(levelname)-8s - %(message)s"
)
