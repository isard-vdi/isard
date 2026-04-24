#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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


class Settings:
    RETHINKDB_HOST = os.environ.get("RETHINKDB_HOST", "isard-db")
    RETHINKDB_PORT = os.environ.get("RETHINKDB_PORT", 28015)
    RETHINKDB_DB = os.environ.get("RETHINKDB_DB", "isard")
    RETHINKDB_POOL_SIZE = os.environ.get("RETHINKDB_POOL_SIZE", 10)
    RETHINKDB_CONNECTION_TIMEOUT = os.environ.get("RETHINKDB_CONNECTION_TIMEOUT", 60)
    DB_POOL_MAX_PENDING = int(os.environ.get("DB_POOL_MAX_PENDING", 0))


settings = Settings()
