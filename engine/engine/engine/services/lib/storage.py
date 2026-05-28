#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2022 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import time
from pathlib import PurePath

from rethinkdb import r

from engine.services.db import (
    get_dict_from_item_in_table,
    insert_table_dict,
    update_table_dict,
)


def _get_filename(storage):
    return str(
        PurePath(storage.get("directory_path"))
        .joinpath(storage.get("id"))
        .with_suffix(f".{storage.get('type')}")
    )


def get_storage_id_filename(storage_id):
    storage = get_dict_from_item_in_table("storage", storage_id)
    if not storage:
        return None
    return _get_filename(storage)


def update_storage_status(storage_id, status):
    if storage_id:
        data = {
            "status": status,
            "status_logs": r.row["status_logs"].append(
                {"time": int(time.time()), "status": status}
            ),
        }
        update_table_dict("storage", storage_id, data)
