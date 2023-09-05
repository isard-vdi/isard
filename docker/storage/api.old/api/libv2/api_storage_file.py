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

import csv
import io
import pathlib
import traceback
from pathlib import Path

from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.storage.isard_qcow import IsardStorageQcow


class StorageFile:
    def __init__(self, file_uuid):
        path = list(Path("/isard").rglob(file_uuid))
        import logging as log

        log.info(file_uuid)
        log.info(path)
        if not len(path):
            raise Error("not_found", "File not found", traceback.format_exc())
        self.file_path = str(path[0])
        # self.format = "qcow" if self.file_path.endswith(".qcow2") else "unknown"
        # self.format = "iso" if self.file_path.endswith(".iso") else "unknown"
        self.storage = IsardStorageQcow()
        # self.storage = IsardStorageIso() if self.format == "iso"
        # Init populate storage thread

    def size(self):
        return self.storage.get_file_size(self.file_path)

    def chain(self):
        return self.storage.get_file_chain(self.file_path)

    def disks(self):
        return self.storage.get_file_disks(self.file_path)
