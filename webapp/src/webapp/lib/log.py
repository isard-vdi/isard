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

import logging as log

from webapp import app

try:
    LOG_LEVEL = app.config["LOG_LEVEL"]
except Exception as e:
    LOG_LEVEL = "INFO"

# LOG FORMATS
LOG_FORMAT = "%(asctime)s %(msecs)d - %(levelname)s - %(threadName)s: %(message)s"
LOG_DATE_FORMAT = "%Y/%m/%d %H:%M:%S"
# getLevelName returns the string "Level <x>" for an unknown name, and
# basicConfig then raises ValueError at import. Normalise and fall back.
LOG_LEVEL_NUM = log.getLevelName(str(LOG_LEVEL).strip().upper())
if not isinstance(LOG_LEVEL_NUM, int):
    print(f"LOG_LEVEL={LOG_LEVEL!r} is not a log level; falling back to INFO")
    LOG_LEVEL_NUM = log.INFO
log.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT, level=LOG_LEVEL_NUM)
