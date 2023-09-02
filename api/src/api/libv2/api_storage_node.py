#
#   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from cachetools import TTLCache, cached

from .._common.api_rest import ApiRest
from .._common.storage_node import StorageNode


@cached(TTLCache(maxsize=1, ttl=5))
def storage_node_list():
    for storage_node in StorageNode.get_all():
        if not storage_node.id:
            storage_node.status = "error"
            continue
        try:
            ApiRest(base_url=storage_node.id).get(timeout=1)
        except:
            storage_node.status = "error"
            continue
        storage_node.status = "online"

    with app.app_context():
        return list(r.table("storage_node").run(db.conn))
