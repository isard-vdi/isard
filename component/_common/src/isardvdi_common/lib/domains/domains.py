from xml.etree import ElementTree as ET

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.xml_compression import compress_xml, decompress_xml
from rethinkdb import r

from ...helpers.alloweds import Alloweds
from ..bookings.reservables import Reservables
from ..deployments.deployments import DeploymentsProcessed


class DomainsProcessed(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def get_user_id_by_desktop_id(cls, desktop_ids: list[str]) -> dict[str, str]:
        """Map ``{desktop_id: user_id}`` for a batch of desktops.

        Used by admin notify-queue endpoints to fan out per-user
        notifications without N+1 queries. Desktops not present in the
        DB are simply absent from the result map (the caller can decide
        to skip or log).
        """
        with cls._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(r.args(desktop_ids), index="id")
                .pluck("id", "user")
                .run(cls._rdb_connection)
            )
        return {d["id"]: d["user"] for d in domains}

    @classmethod
    def get_by_ids(cls, domain_ids: list[str]) -> list[dict]:
        """Fetch a batch of domains by id with ``user_name``,
        ``category_name`` and ``group_name`` merged in.

        Missing referenced rows surface as ``[deleted]`` rather than
        crashing the merge. Used by the admin "fast-path" details list.
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(r.args(domain_ids))
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "status",
                    "user",
                    "category",
                    "group",
                    "accessed",
                    "create_dict",
                    "tag",
                    "persistent",
                )
                .merge(
                    lambda d: {
                        "user_name": r.table("users")
                        .get(d["user"])
                        .default({"name": "[deleted]"})["name"],
                        "category_name": r.table("categories")
                        .get(d["category"])
                        .default({"name": "[deleted]"})["name"],
                        "group_name": r.table("groups")
                        .get(d["group"])
                        .default({"name": "[deleted]"})["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def find_disks_by_kind_status(
        cls, kind: str, status: str, category_id: str | None = None
    ) -> list[dict]:
        """List ``create_dict.hardware.disks`` for every domain of
        ``kind`` in ``status``, scoped to ``category_id`` when given.

        Returns ``[{create_dict: {hardware: {disks: [...]}}}, ...]`` —
        the caller flattens to extract storage ids. Two indexes:
        ``kind_status_category`` for managers, ``kind_status`` for
        admins.
        """
        if category_id is not None:
            index_key = "kind_status_category"
            index_value = [kind, status, category_id]
        else:
            index_key = "kind_status"
            index_value = [kind, status]
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(index_value, index=index_key)
                .pluck({"create_dict": {"hardware": {"disks": True}}})
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_xml(cls, domain_id: str) -> str | None:
        """Return the ``xml`` field of a domain row, or raise when missing.

        Returns ``None`` when the row exists but has no ``xml``.
        Raises a typed ``not_found`` ``Error`` when the row is absent.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            domain = (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )
        if domain is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        return decompress_xml(domain.get("xml"))

    @classmethod
    def update_xml(cls, domain_id: str, data: dict) -> str | None:
        """Apply ``data`` to a domain row and return its (new) ``xml``.

        Caller is responsible for the payload shape; this helper sets
        ``status="Updating"`` and ``id=domain_id`` per the v3 contract,
        then returns the freshly-stored xml. Raises ``not_found`` when
        the row is absent.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            existing = (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )
        if existing is None:
            raise Error("not_found", f"Domain {domain_id} not found")
        data["status"] = "Updating"
        data["id"] = domain_id
        if "xml" in data:
            data["xml"] = compress_xml(data["xml"])
        with cls._rdb_context():
            r.table("domains").get(domain_id).update(data).run(cls._rdb_connection)
            result = (
                r.table("domains").get(domain_id).pluck("xml").run(cls._rdb_connection)
            )
        return decompress_xml(result.get("xml"))

    @classmethod
    def get_xml_and_protected(cls, domain_id: str) -> dict:
        """Return ``{xml, protected}`` for the XML-sections editor.

        ``protected`` is ``create_dict.xml_protected_sections`` (defaults
        to ``[]`` when unset). Raises ``not_found`` when the row is
        absent.
        """
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            domain = (
                r.table("domains")
                .get(domain_id)
                .pluck("xml", "create_dict")
                .default(None)
                .run(cls._rdb_connection)
            )
        if domain is None:
            raise Error("not_found", "Domain not found")
        return {
            "xml": decompress_xml(domain.get("xml")),
            "protected": domain.get("create_dict", {}).get(
                "xml_protected_sections", []
            ),
        }

    @classmethod
    def list_by_kind_user(
        cls, kind: str, user_id: str, fields: list[str]
    ) -> list[dict]:
        """List rows of ``kind`` owned by ``user_id`` with ``fields``
        plucked.

        ``kind`` is the secondary index key (``"template"``,
        ``"desktop"``, etc.) and is paired with ``user_id`` via the
        ``kind_user`` compound index.
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all([kind, user_id], index="kind_user")
                .pluck(*fields)
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_webapp_desktops_for_user(cls, user_id: str) -> list[dict]:
        """Return the legacy webapp's desktop list for ``user_id``.

        Strips fields the webapp never renders (``xml``,
        ``history_domain``, ``allowed``) and orders by ``name`` so the
        UI doesn't have to. Caller filters out hidden tags.
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .order_by("name")
                .without("xml", "history_domain", "allowed")
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_webapp_templates_for_user(cls, user_id: str) -> list[dict]:
        """Return the legacy webapp's template list for ``user_id``.

        Strips fields the webapp never renders (``viewer``, ``xml``,
        ``history_domain``).
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(["template", user_id], index="kind_user")
                .without("viewer", "xml", "history_domain")
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_status_and_scheduled(cls, domain_id: str) -> dict | None:
        """Return ``{status, scheduled}`` for ``domain_id`` (or ``None``).

        Read by the desktop-timeout extension path; only those two
        fields are needed to validate the precondition before
        re-arming the scheduler.
        """
        with cls._rdb_context():
            return (
                r.table("domains")
                .get(domain_id)
                .pluck("status", "scheduled")
                .run(cls._rdb_connection)
            )

    @classmethod
    def list_templates_for_admin(
        cls, fields: list[str], category_id: str | None = None
    ) -> list[dict]:
        """List every template visible to admin/manager.

        ``category_id`` scopes managers to their own category; admins
        pass ``None`` to see every template across categories.
        """
        with cls._rdb_context():
            query = r.table("domains").get_all("template", index="kind")
            if category_id is not None:
                query = query.filter({"category": category_id})
            return list(query.pluck(*fields).run(cls._rdb_connection))

    @classmethod
    def get_for_search(cls, domain_id: str) -> dict | None:
        """Read the full row used by the admin search panel.

        Returns ``None`` when the row is absent — the caller raises
        ``not_found`` so it can craft a route-specific error message.
        ``.default(None)`` BEFORE pluck — otherwise pluck on null
        crashes with ReqlNonExistenceError before the if-check ever
        runs.
        """
        with cls._rdb_context():
            return (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )

    @classmethod
    def get_media_domains(cls, media_ids):
        """From api/libv2/api_storage.py get_media_domains()"""
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(media_ids, index="media_ids")
                .eq_join("user", r.table("users"))
                .pluck(
                    {
                        "left": {
                            "name": True,
                            "kind": True,
                            "id": True,
                            "user": True,
                        },
                        "right": {
                            "id": True,
                            "group": True,
                            "category": True,
                            "role": True,
                            "name": True,
                            "username": True,
                        },
                    }
                )
                .map(
                    lambda doc: {
                        "id": doc["left"]["id"],
                        "name": doc["left"]["name"],
                        "kind": doc["left"]["kind"],
                        "user": doc["left"]["user"],
                        "user_data": {
                            "role_id": doc["right"]["role"],
                            "category_id": doc["right"]["category"],
                            "group_id": doc["right"]["group"],
                            "user_id": doc["right"]["id"],
                            "user_name": doc["right"]["name"],
                            "username": doc["right"]["username"],
                        },
                    }
                )
                .merge(
                    lambda doc: {
                        "category_name": r.table("categories").get(
                            doc["user_data"]["category_id"]
                        )["name"],
                        "group_name": r.table("groups").get(
                            doc["user_data"]["group_id"]
                        )["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_desktops_with_resource(cls, table, item):
        """From api/libv2/api_desktops_persistent.py get_desktops_with_resource()"""
        if table == "media":
            return cls.get_media_domains(item["id"])
        elif table == "reservables_vgpus":
            return Reservables().check_desktops_with_profile("gpus", item["id"])
        elif table in ["interfaces", "boots", "videos"]:
            with cls._rdb_context():
                return list(
                    r.table("domains")
                    .get_all(
                        item["id"], index="boot_order" if table == "boots" else table
                    )
                    .eq_join("user", r.table("users"))
                    .pluck(
                        {
                            "left": {"id": True},
                            "right": {
                                "id": True,
                                "group": True,
                                "category": True,
                                "role": True,
                            },
                        }
                    )
                    .map(
                        lambda doc: {
                            "id": doc["left"]["id"],
                            "user_data": {
                                "role_id": doc["right"]["role"],
                                "category_id": doc["right"]["category"],
                                "group_id": doc["right"]["group"],
                                "user_id": doc["right"]["id"],
                            },
                        }
                    )
                    .run(cls._rdb_connection)
                )

    @classmethod
    def unassign_resource_from_desktops_and_deployments(cls, table, item):
        """From api/libv2/api_desktops_persistent.py unassign_resource_from_desktops_and_deployments()"""
        if table == "qos_disk":
            with cls._rdb_context():
                r.table("domains").get_all(item["id"], index="qos_disk_id").update(
                    {"create_dict": {"hardware": {"qos_disk_id": False}}}
                ).run(cls._rdb_connection)
            return []

        domains = cls.get_desktops_with_resource(table, item)
        not_allowed_desktops = []
        deployments = DeploymentsProcessed.get_deployments_with_resource(table, item)
        not_allowed_deployments = []

        if item.get("allowed"):
            for domain in domains:
                isAllowed = Alloweds.is_allowed(domain.pop("user_data"), item, table)
                if not isAllowed:
                    not_allowed_desktops.append(domain["id"])
            for deployment in deployments:
                isAllowed = Alloweds.is_allowed(
                    deployment.pop("user_data"), item, table
                )
                if not isAllowed:
                    not_allowed_deployments.append(deployment["id"])
        else:
            not_allowed_desktops = [domain.get("id") for domain in domains]
            not_allowed_deployments = [deployment["id"] for deployment in deployments]

        if table == "media":
            with cls._rdb_context():
                r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "isos": r.row["create_dict"]["hardware"]["isos"].filter(
                                    lambda media: media["id"].ne(item["id"])
                                )
                            }
                        }
                    }
                ).run(cls._rdb_connection)

            deployments_batch_size = 100
            for i in range(0, len(not_allowed_deployments), deployments_batch_size):
                batch_deployments = not_allowed_deployments[
                    i : i + deployments_batch_size
                ]
                with cls._rdb_context():
                    r.table("deployments").get_all(r.args(batch_deployments)).update(
                        lambda deployment: {
                            "create_dict": deployment["create_dict"].map(
                                lambda create_item: create_item.merge(
                                    {
                                        "hardware": create_item["hardware"].merge(
                                            {
                                                "isos": create_item["hardware"][
                                                    "isos"
                                                ].filter(
                                                    lambda media: media["id"].ne(
                                                        item["id"]
                                                    )
                                                )
                                            }
                                        )
                                    }
                                )
                            )
                        }
                    ).run(cls._rdb_connection)

        elif table == "reservables_vgpus":
            Reservables().deassign_desktops_with_gpu(
                "gpus", item["id"], desktops=not_allowed_desktops
            )
            Reservables().deassign_deployments_with_gpu(
                "gpus", item["id"], deployments=not_allowed_deployments
            )
        elif table == "interfaces":
            if item["id"] == "wireguard":
                with cls._rdb_context():
                    r.table("domains").get_all(r.args(not_allowed_desktops)).replace(
                        r.row.without(
                            {
                                "guest_properties": {
                                    "viewers": {
                                        "browser_rdp": True,
                                        "file_rdpgw": True,
                                        "file_rdpvpn": True,
                                    }
                                },
                            }
                        )
                    ).run(cls._rdb_connection)
                with cls._rdb_context():
                    r.table("deployments").get_all(
                        r.args(not_allowed_deployments)
                    ).replace(
                        r.row.without(
                            {
                                "create_dict": {
                                    "guest_properties": {
                                        "viewers": {
                                            "browser_rdp": True,
                                            "file_rdpgw": True,
                                            "file_rdpvpn": True,
                                        }
                                    },
                                }
                            }
                        )
                    ).run(
                        cls._rdb_connection
                    )
            with cls._rdb_context():
                r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "interfaces": r.row["create_dict"]["hardware"][
                                    "interfaces"
                                ].filter(
                                    lambda interface: interface["id"].ne(item["id"])
                                )
                            }
                        }
                    }
                ).run(cls._rdb_connection)
            deployments_batch_size = 100
            for i in range(0, len(not_allowed_deployments), deployments_batch_size):
                batch_deployments = not_allowed_deployments[
                    i : i + deployments_batch_size
                ]
                with cls._rdb_context():
                    r.table("deployments").get_all(r.args(batch_deployments)).update(
                        lambda deployment: {
                            "create_dict": deployment["create_dict"].map(
                                lambda create_item: create_item.merge(
                                    {
                                        "hardware": create_item["hardware"].merge(
                                            {
                                                "interfaces": create_item["hardware"][
                                                    "interfaces"
                                                ].difference([item["id"]])
                                            }
                                        )
                                    }
                                )
                            )
                        }
                    ).run(cls._rdb_connection)

        elif table in ["boots", "videos"]:
            fields = {
                "boots": "boot_order",
                "videos": "videos",
            }
            with cls._rdb_context():
                r.table("domains").get_all(r.args(not_allowed_desktops)).update(
                    {
                        "create_dict": {
                            "hardware": {
                                fields[table]: r.row["create_dict"]["hardware"][
                                    fields[table]
                                ].difference([item["id"]])
                            }
                        }
                    }
                ).run(cls._rdb_connection)
            deployments_batch_size = 100
            for i in range(0, len(not_allowed_deployments), deployments_batch_size):
                batch_deployments = not_allowed_deployments[
                    i : i + deployments_batch_size
                ]
                with cls._rdb_context():
                    r.table("deployments").get_all(r.args(batch_deployments)).update(
                        lambda deployment: {
                            "create_dict": deployment["create_dict"].map(
                                lambda create_item: create_item.merge(
                                    {
                                        "hardware": create_item["hardware"].merge(
                                            {
                                                fields[table]: create_item["hardware"][
                                                    fields[table]
                                                ].difference([item["id"]])
                                            }
                                        )
                                    }
                                )
                            )
                        }
                    ).run(cls._rdb_connection)

        return not_allowed_desktops

    @classmethod
    def domain_template_tree(cls, domain_id):
        """From api/libv2/api_desktops_persistent.py domain_template_tree()"""
        try:
            with cls._rdb_context():
                parents_ids = (
                    r.table("domains")
                    .get(domain_id)["parents"]
                    .default([])
                    .run(cls._rdb_connection)
                )
        except Exception:
            return []
        if not parents_ids:
            return []

        with cls._rdb_context():
            parents = list(
                r.table("domains")
                .get_all(r.args(parents_ids))
                .merge(
                    lambda domain: {
                        "category_name": r.table("categories").get(domain["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(domain["group"])["name"],
                        "parents_count": r.expr(domain["parents"]).default([]).count(),
                    }
                )
                .order_by(r.asc("parents_count"))
                .pluck(
                    "id",
                    "name",
                    "user",
                    "username",
                    "category_name",
                    "group_name",
                    "parents_count",
                )
                .run(cls._rdb_connection)
            )

        return parents

    @classmethod
    def get_domain_details_hardware(cls, domain_id):
        """From api/libv2/api_domains.py ApiDomains.get_domain_details_hardware()"""
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

        for index, interface in enumerate(hardware["hardware"]["interfaces"]):
            with cls._rdb_context():
                hardware["hardware"]["interfaces"][index]["name"] = (
                    r.table("interfaces")
                    .get(interface["id"])
                    .pluck("name")["name"]
                    .run(cls._rdb_connection)
                )

        if "isos" in hardware["hardware"]:
            isos = hardware["hardware"]["isos"]
            hardware["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                with cls._rdb_context():
                    hardware["hardware"]["isos"].append(
                        r.table("media")
                        .get(iso["id"])
                        .pluck("id", "name")
                        .run(cls._rdb_connection)
                    )
        if "floppies" in hardware["hardware"]:
            with cls._rdb_context():
                hardware["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(cls._rdb_connection)
                )
        hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576
        return hardware

    @classmethod
    def update_domain_path(self, domain_id, old_path, new_path):
        """_From api/libv2/api_domains.py ApiDomains.update_domain_path()_

        Update all instances of a specific absolute path in a domain JSON document in RethinkDB.

        :param domain_id: The ID of the domain to update.
        :param old_path: The absolute path to replace.
        :param new_path: The new absolute path.
        """
        with self._rdb_context():
            domain = r.table("domains").get(domain_id).run(self._rdb_connection)

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

        with self._rdb_context():
            r.table("domains").get(domain_id).update(domain).run(self._rdb_connection)
        return domain

    @classmethod
    def get_domain_hardware(cls, domain_id):
        """_From api/libv2/api_desktops_common.py ApiDesktopsCommon.get_domain_hardware()_"""

        hardware_db = Caches.get_document("domains", domain_id, ["create_dict"])
        hardware = {"hardware": hardware_db["hardware"]}

        if hardware_db.get("reservables"):
            hardware["reservables"] = hardware_db["reservables"]

        if "isos" in hardware["hardware"]:
            isos = hardware["hardware"]["isos"]
            hardware["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                hardware["hardware"]["isos"].append(
                    Caches.get_document("media", iso["id"], ["id", "name"])
                )

        if "floppies" in hardware["hardware"]:
            with cls._rdb_context():
                hardware["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(cls._rdb_connection)
                )

        hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576

        return hardware
