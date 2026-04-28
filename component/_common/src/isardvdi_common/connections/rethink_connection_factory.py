#
#   Copyright © 2025 Pau Abril Iranzo
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


import importlib
import importlib.util

if (
    importlib.util.find_spec("api")
    and importlib.util.find_spec("api").origin == "/api/api/__init__.py"
):
    """APIv3"""

    from abc import ABC

    from api import app
    from api.libv2.flask_rethink import RDB

    class RethinkSharedConnection(ABC):
        """
        Manage RethinkDB connection via APIv3.

        Open _rdb_context and use _rdb_connection to use a shared connection.
        """

        _rdb_context = app.app_context

        _rdb_flask = RDB(app)

        @classmethod
        @property
        def _rdb_connection(cls):
            return cls._rdb_flask.conn

else:
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )
