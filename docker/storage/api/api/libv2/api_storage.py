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

# from subprocess import check_output
import hashlib
import os
from pathlib import Path

from api import app

from .._common.api_rest import ApiRest
from ..libv2.storage.isard_qcow import IsardStorageQcow


def ff(path_id):
    # file_format = check_output(
    #     ("file", "-F", "','", path_id), text=True
    # ).strip().split(",")[1]
    # if "QCOW" in file_format:
    #     return "qcow2"
    return "qcow2"


class Storage:
    def __init__(self):
        app.logger.info("Instantiating storage")
        self.storage = {"qcow2": IsardStorageQcow()}
        self.init_api()

    def init_api(self):
        flavour = os.environ.get("FLAVOUR", False)
        if str(flavour) == "all-in-one" or not flavour:
            self.hostname = "isard-hypervisor"
        else:
            self.hostname = os.environ.get("DOMAIN")
        api_domain = os.environ.get("API_DOMAIN", False)
        if api_domain and api_domain != "isard-api":
            self.api_rest = ApiRest(
                "https://" + api_domain + "/api/v3/admin", verify_cert=False
            )
        else:
            self.api_rest = ApiRest(
                "http://isard-api:5000/api/v3/admin", verify_cert=False
            )

        self.templates_path = "/isard/templates"
        self.desktops_path = "/isard/groups"
        self.media_path = "/isard/media"

    def get_file_info(self, path_id):
        return self.storage[ff(path_id)].get_file_info(path_id)

    def update_disks(self):
        self.template_files = [
            {
                "id": hashlib.md5(str(p).encode("utf-8")).hexdigest(),
                "path": str(p),
                "hyper": self.hostname,
                "kind": "template",
                "size": p.stat().st_size,
            }
            for p in Path(self.templates_path).rglob("*")
            if p.is_file()
        ]
        self.desktop_files = [
            {
                "id": hashlib.md5(str(p).encode("utf-8")).hexdigest(),
                "path": str(p),
                "hyper": self.hostname,
                "kind": "desktop",
                "size": p.stat().st_size,
            }
            for p in Path(self.desktops_path).rglob("*")
            if p.is_file()
        ]
        self.api_rest.put(
            "/storage/physical/init/domains",
            self.template_files + self.desktop_files,
        )
        app.logger.info("- updated disks to api")
        return {
            "templates": len(self.template_files),
            "desktops": len(self.desktop_files),
        }

    def update_media(self):
        self.media_files = [
            {
                "id": hashlib.md5(str(p).encode("utf-8")).hexdigest(),
                "path": str(p),
                "hyper": self.hostname,
                "kind": "media",
                "size": p.stat().st_size,
            }
            for p in Path(self.media_path).rglob("*")
            if p.is_file()
        ]
        self.api_rest.put(
            "/storage/physical/init/media",
            self.media_files,
        )
        app.logger.info("- updated media to api")
        return {
            "media": len(self.media_files),
        }
