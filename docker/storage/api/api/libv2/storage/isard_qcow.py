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

import contextlib
import json
import traceback
from subprocess import check_output

import guestfs
import pyqcow

from ..._common.api_exceptions import Error


class QcowFileLockedError(Exception):
    def __init__(self, file_path, message=False):
        if not message:
            message = "The " + file_path + " is locked."
        super().__init__(message)


@contextlib.contextmanager
def Qcow(file_path):
    qcow_file = pyqcow.file()
    try:
        qcow_file.open(file_path)
    except:
        raise Error("not_found", "File not found", traceback.format_exc())
    if qcow_file.is_locked():
        raise Error("precondition_required", "File is locked", traceback.format_exc())
    yield qcow_file
    qcow_file.close()


@contextlib.contextmanager
def Guestfs(file_path, readonly=1):
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(file_path, readonly=readonly)
    g.launch()
    yield g
    g.umount_all()


class IsardStorageQcow:
    def get_file_info(self, file_path):
        return json.loads(
            check_output(
                ("qemu-img", "info", "--output", "json", file_path), text=True
            ).strip()
        )

    def get_file_size(self, file_path):
        with Qcow(file_path) as q:
            return q.get_media_size()

    def get_file_chain(self, file_path):
        backing = [file_path]
        bc = file_path
        while bc:
            with Qcow(bc) as q:
                bc = q.get_backing_filename()
            if bc:
                backing.append(bc)
        return backing

    def get_file_disks(self, file_path):
        with Guestfs(file_path) as g:
            try:
                return {
                    "devices": g.list_devices(),
                    "partitions": g.list_partitions(),
                    "filesystems": g.list_filesystems(),
                }
            except:
                return {
                    "devices": [],
                    "partitions": [],
                    "filesystems": [],
                }
