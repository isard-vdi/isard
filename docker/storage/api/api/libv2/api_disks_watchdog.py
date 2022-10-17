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

import os
import time
from pathlib import Path
from urllib.parse import quote

import watchdog.events
import watchdog.observers

from api import app

from .._common.api_rest import ApiRest


def _get_path_kind(directory):
    if "/templates/" in directory:
        kind = "domains"
    if "/groups/" in directory:
        kind = "domains"
    if "/media/" in directory:
        kind = "media"
    return kind


class Handler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self):
        flavour = os.environ.get("FLAVOUR", False)
        if str(flavour) == "all-in-one" or not flavour:
            self.hostname = "isard-hypervisor"
        else:
            self.hostname = os.environ.get("DOMAIN")
        api_domain = os.environ.get("API_DOMAIN", False)
        if api_domain and api_domain != "isard-api":
            self.api_rest = ApiRest(
                "https://" + api_domain + "/api/v3/admin", verify_cert=True
            )
        else:
            self.api_rest = ApiRest(
                "http://isard-api:5000/api/v3/admin", verify_cert=True
            )

        self.templates_path = "/isard/templates"
        self.desktops_path = "/isard/groups"
        self.media_path = "/isard/media"

        self.update_disks()
        watchdog.events.PatternMatchingEventHandler.__init__(
            self,
            patterns=["*.qcow2", "*.iso"],
            ignore_directories=True,
            case_sensitive=False,
        )

    def update_disks(self):
        self.template_files = [
            {
                "id": str(p),
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
                "id": str(p),
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
        self.media_files = [
            {
                "id": str(hash(p.stat())),
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
        app.logger.info("- updated disks to api")

    def on_created(self, event):
        app.logger.info("- received created event - % s." % event.src_path)
        p = Path(event.src_path)
        kind = _get_path_kind(event.src_path)
        self.api_rest.put(
            "/storage/physical/" + kind,
            {
                "id": str(p),
                "path": str(p),
                "hyper": self.hostname,
                "kind": kind,
                "size": p.stat().st_size,
            },
        )

    def on_deleted(self, event):
        app.logger.info("- received delete event - % s." % event.src_path)
        p = Path(event.src_path)
        kind = _get_path_kind(event.src_path)
        self.api_rest.delete("/storage/physical/" + kind + "/{}".format(quote(str(p))))

    def on_moved(self, event):
        app.logger.info("- received moved event - % s." % event.src_path)
        # Event is moved, you can process it now


def start_disks_watchdog():
    src_path = r"/isard"
    event_handler = Handler()
    observer = watchdog.observers.Observer()
    observer.schedule(event_handler, path=src_path, recursive=True)
    observer.start()
    app.logger.info("- started disks watchdog")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
