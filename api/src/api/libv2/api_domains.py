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

from xml.etree import ElementTree as ET

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from isardvdi_common.api_exceptions import Error

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


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
            with app.app_context():
                hardware["hardware"]["interfaces"][index]["name"] = (
                    r.table("interfaces")
                    .get(interface["id"])
                    .pluck("name")["name"]
                    .run(db.conn)
                )

        if "isos" in hardware["hardware"]:
            isos = hardware["hardware"]["isos"]
            hardware["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                with app.app_context():
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

    def update_domain_path(self, domain_id, old_path, new_path):
        """
        Update all instances of a specific absolute path in a domain JSON document in RethinkDB.

        :param domain_id: The ID of the domain to update.
        :param old_path: The absolute path to replace.
        :param new_path: The new absolute path.
        """
        with app.app_context():
            domain = r.table("domains").get(domain_id).run(db.conn)

        if not domain:
            raise Error("not_found", f"Domain {domain_id} not found.")

        # Recursive function to replace paths in the JSON structure
        def replace_path(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, str) and value == old_path:
                        obj[key] = new_path
                    else:
                        replace_path(value)
            elif isinstance(obj, list):
                for item in obj:
                    replace_path(item)

        # Replace paths in the JSON document
        replace_path(domain)

        # Special handling for XML strings if present
        if "xml" in domain:
            xml_content = domain["xml"]
            try:
                root = ET.fromstring(xml_content)
                for source in root.findall(".//source"):
                    if source.attrib.get("file") == old_path:
                        source.set("file", new_path)
                domain["xml"] = ET.tostring(root, encoding="unicode")
            except ET.ParseError as e:
                print("Error parsing XML:", e)

        with app.app_context():
            r.table("domains").get(domain_id).update(domain).run(db.conn)
        return domain
