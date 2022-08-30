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

from pathlib import PurePath

from engine.services.db import (
    get_dict_from_item_in_table,
    get_table_field,
    insert_table_dict,
    update_table_field,
)


def _get_filename(storage):
    return str(
        PurePath(storage.get("directory_path"))
        .joinpath(storage.get("id"))
        .with_suffix(f".{storage.get('type')}")
    )


def create_storage(disk, user, force_parent=False):
    directory_path = disk.pop("path_selected")
    relative_path = PurePath(disk.pop("file")).relative_to(directory_path)
    storage_id = str(relative_path).removesuffix(relative_path.suffix)
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
        },
    )
    disk["storage_id"] = storage_id


def insert_storage(disk):
    storage_id = disk.get("storage_id")
    if storage_id:
        storage = get_dict_from_item_in_table("storage", storage_id)
        disk.update(
            {
                "file": _get_filename(storage),
                "parent": storage.get("parent"),
                "path_selected": storage.get("directory_path"),
            }
        )


def update_storage_status(storage_id, status):
    if storage_id:
        update_table_field("storage", storage_id, "status", status)


def update_qemu_img_info(create_dict, disk_index, qemu_img_info):
    storage_id = (
        dict(enumerate(create_dict.get("hardware", {}).get("disks", [])))
        .get(disk_index, {})
        .get("storage_id")
    )
    if storage_id:
        filename = _get_filename(get_dict_from_item_in_table("storage", storage_id))
        for disk_info in qemu_img_info:
            if disk_info.get("filename") == filename:
                update_table_field("storage", storage_id, "qemu-img-info", disk_info)
                if type(qemu_img_info) is list:
                    d_qemu_img_info = qemu_img_info[0]
                elif type(qemu_img_info) is dict:
                    d_qemu_img_info = qemu_img_info
                else:
                    return False
                if "backing-filename" not in d_qemu_img_info.keys():
                    update_table_field("storage", storage_id, "parent", None)
                else:
                    parent_path = d_qemu_img_info["backing-filename"]
                    try:
                        uuid_parent = parent_path[: parent_path.rfind(".")].split("/")[
                            -1
                        ]
                        # if id doesn't exist get_table_field is None
                        parent_id = get_table_field("storage", uuid_parent, "id")

                    except Exception as e:
                        parent_id = None

                    if parent_id is None:
                        update_table_field("storage", storage_id, "status", "orphan")

                    update_table_field("storage", storage_id, "parent", parent_id)
    return True