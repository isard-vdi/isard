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

from engine.services.db import (
    get_dict_from_item_in_table,
    get_table_field,
    insert_table_dict,
    update_table_dict,
    update_table_field,
)
from rethinkdb import r


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


def create_storage(disk, user, force_parent=False, perms=["r", "w"]):
    directory_path = disk.pop("path_selected")
    relative_path = PurePath(disk.pop("file")).relative_to(directory_path)
    storage_id = str(relative_path).removesuffix(relative_path.suffix)
    if "size" in disk.keys():
        disk.pop("size")
    if force_parent == False:
        parent = disk.pop("parent")
    else:
        parent = force_parent

    insert_table_dict(
        "storage",
        {
            "id": storage_id,
            "type": relative_path.suffix[1:],
            "directory_path": directory_path,
            "parent": parent,
            "user_id": user,
            "status": "non_existing",
            "perms": perms,
            "status_logs": [{"time": int(time.time()), "status": "created"}],
        },
    )
    disk["storage_id"] = storage_id
    return storage_id


def insert_storage(disk, perms=["r", "w"]):
    storage_id = disk.get("storage_id")
    if storage_id:
        storage = get_dict_from_item_in_table("storage", storage_id)
        if not storage:
            return False
        disk.update(
            {
                "file": _get_filename(storage),
                "parent": storage.get("parent"),
                "path_selected": storage.get("directory_path"),
                "perms": perms,
            }
        )


def update_storage_status(storage_id, status):
    if storage_id:
        data = {
            "status": status,
            "status_logs": r.row["status_logs"].append(
                {"time": int(time.time()), "status": status}
            ),
        }
        update_table_dict("storage", storage_id, data)


def update_storage_deleted_domain(storage_id, domain=None):
    if storage_id:
        update_table_field("storage", storage_id, "last_domain_attached", domain)


def update_domain_createdict_qemu_img_info(
    create_dict, disk_index, qemu_img_info, force_storage_id=False
):
    if force_storage_id is False:
        storage_id = (
            dict(enumerate(create_dict.get("hardware", {}).get("disks", [])))
            .get(disk_index, {})
            .get("storage_id")
        )
    else:
        storage_id = force_storage_id
    update_storage_qemu_info(storage_id, qemu_img_info)


def update_storage_qemu_info(storage_id, qemu_img_info, hierarchy=True):
    if storage_id is None:
        print("storage_id is None")
        return False
    d_storage = get_dict_from_item_in_table("storage", storage_id)
    if d_storage:
        filename = _get_filename(d_storage)
        if type(qemu_img_info) is list and len(qemu_img_info) > 0:
            disk_info = qemu_img_info[0]
        elif type(qemu_img_info) is dict:
            disk_info = qemu_img_info
        else:
            return False

        if disk_info.get("filename") == filename:
            storage_dict = {}
            storage_dict["qemu-img-info"] = disk_info
            if not hierarchy:
                return True
            if "backing-filename" not in disk_info.keys():
                storage_dict["parent"] = None
            else:
                parent_path = disk_info["backing-filename"]
                try:
                    uuid_parent = parent_path[: parent_path.rfind(".")].split("/")[-1]
                    # if id doesn't exist get_table_field is None
                    parent_id = get_table_field("storage", uuid_parent, "id")
                except Exception as e:
                    parent_id = None

                if parent_id is None:
                    storage_dict["status"] = "orphan"

                storage_dict["parent"] = parent_id
            update_table_dict("storage", storage_id, storage_dict)
    return True
