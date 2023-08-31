#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Lídia Montero Gutiérrez
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
import traceback

from api._common.domain import Domain
from rethinkdb import RethinkDB

from api import app

from ..libv2.validators import _validate_item
from .api_cards import ApiCards
from .api_desktop_events import template_delete, templates_delete

r = RethinkDB()
import logging as log

from .._common.api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


from .helpers import _check, _parse_media_info, _parse_string, get_user_data


class ApiDomains:
    def __init__(self):
        None

    def get_domain_details_hardware(self, domain_id):
        with app.app_context():
            hardware = (
                r.table("domains")
                .get(domain_id)
                .pluck("create_dict")["create_dict"]
                .merge(
                    lambda domain: {
                        "video_name": domain["hardware"]["videos"].map(
                            lambda video: r.table("videos").get(video)["name"]
                        ),
                        "boot_name": domain["hardware"]["boot_order"].map(
                            lambda boot_order: r.table("boots").get(boot_order)["name"]
                        ),
                        "reservable_name": r.branch(
                            domain["reservables"]["vgpus"].default(None),
                            domain["reservables"]["vgpus"].map(
                                lambda reservable: r.table("reservables_vgpus").get(
                                    reservable
                                )["name"]
                            ),
                            False,
                        ),
                    }
                )
                .run(db.conn)
            )

        for index, interface in enumerate(hardware["hardware"]["interfaces"]):
            hardware["hardware"]["interfaces"][index]["name"] = (
                r.table("interfaces")
                .get(interface["id"])
                .pluck("name")["name"]
                .run(db.conn)
            )

        if "isos" in hardware["hardware"]:
            with app.app_context():
                isos = hardware["hardware"]["isos"]
                hardware["hardware"]["isos"] = []
                # Loop instead of a get_all query to keep the isos array order
                for iso in isos:
                    hardware["hardware"]["isos"].append(
                        r.table("media").get(iso["id"]).pluck("id", "name").run(db.conn)
                    )
        if "floppies" in hardware["hardware"]:
            with app.app_context():
                hardware["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(db.conn)
                )
        hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576
        return hardware
