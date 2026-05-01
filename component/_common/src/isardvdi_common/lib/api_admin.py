import traceback

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.helpers.helpers import Helpers
from rethinkdb import r


class ApiAdmin(RethinkSharedConnection):

    @staticmethod
    def parse_media_data_merge():
        """_From api/libv2/api_admin.py parse_media_data_merge()_"""
        return lambda media: {
            "domains": r.table("domains")
            .get_all(media["id"], index="media_ids")
            .count(),
            "category_name": r.table("categories").get(media["category"])["name"],
            "group_name": r.table("groups").get(media["group"])["name"],
        }

    @staticmethod
    def parse_hypervisor_data_merge():
        """_From api/libv2/api_admin.py parse_hypervisor_data_merge()_"""
        return lambda hyper: {
            "gpus": r.table("vgpus").filter({"hyp_id": hyper["id"]}).count(),
            "desktops_started": r.table("domains")
            .get_all(hyper["id"], index="hyp_started")
            .count(),
        }

    @staticmethod
    def parse_deployment_data_merge():
        """_From api/libv2/api_admin.py parse_deployment_data_merge()_"""
        return lambda deploy: {
            "desktop_name": r.table("domains")
            .get_all(deploy["id"], index="tag")["name"][0]
            .default(False),
            "category_name": r.table("users")
            .get(deploy["user"])
            .merge(
                lambda user: {
                    "category_name": r.table("categories").get(user["category"])["name"]
                }
            )["category_name"]
            .default(False),
            "category": r.table("users")
            .get(deploy["user"])
            .merge(lambda user: {"category": user["category"]})["category"]
            .default(False),
            "group_name": r.table("users")
            .get(deploy["user"])
            .merge(
                lambda user: {
                    "group_name": r.table("groups").get(user["group"])["name"]
                }
            )["group_name"]
            .default(False),
            "user_name": r.table("users").get(deploy["user"])["name"].default(False),
            "co_owners_user_names": r.expr(deploy["co_owners"]).map(
                lambda co_owner: r.table("users").get(co_owner)["name"].default(False)
            ),
            "how_many_desktops": r.table("domains")
            .get_all(deploy["id"], index="tag")
            .count()
            .default(False),
            "how_many_desktops_started": r.table("domains")
            .get_all([deploy["id"], "Started"], index="tag_status")
            .count()
            .default(False),
            "last_access": r.table("domains")
            .get_all(deploy["id"], index="tag")
            .max("accessed")["accessed"]
            .default(False),
        }

    @classmethod
    def system_tables(cls):
        """_Replaces app.system_tables_"""
        # TODO(move-api_admin-to-common): Add a cache for this, it should never change
        with cls._rdb_context():
            return r.table_list().run(cls._rdb_connection)

    @classmethod
    def _validate_table(cls, table):
        """_From api/libv2/validators.py \_validate_table()_"""
        from isardvdi_common.helpers.error_factory import Error

        if table not in cls.system_tables():
            raise Error(
                "not_found",
                "Table " + table + " does not exist.",
                traceback.format_exc(),
            )

    @classmethod
    def get_table_item(cls, table: str, item_id: str) -> dict | None:
        """Fetch a full row from ``table`` by id.

        Returns the row dict, or ``None`` if missing. Used by callers
        that need the whole row (e.g. for resource-unassignment fallback
        merging) rather than just specific fields.
        """
        cls._validate_table(table)
        with cls._rdb_context():
            return r.table(table).get(item_id).run(cls._rdb_connection)

    @classmethod
    def insert_table_item(cls, table: str, data: dict) -> None:
        """Insert a row into ``table``.

        Raises ``conflict`` if ``data["id"]`` already exists, or
        ``internal_server`` if the insert returns ``inserted == 0``.
        Caller is responsible for validating ``data["id"]`` is present
        and for any sanitization.
        """
        from isardvdi_common.helpers.error_factory import Error

        cls._validate_table(table)
        with cls._rdb_context():
            existing = r.table(table).get(data["id"]).run(cls._rdb_connection)
            if existing is not None:
                raise Error(
                    "conflict",
                    "Id " + data["id"] + " already exists in table " + table,
                )
            result = r.table(table).insert(data).run(cls._rdb_connection)
            if not result.get("inserted"):
                raise Error(
                    "internal_server",
                    "Insert into " + table + " returned inserted=0",
                    traceback.format_exc(),
                )

    @classmethod
    def update_table_item(cls, table: str, data: dict) -> None:
        """Update a row in ``table`` by ``data["id"]``.

        No-op if the id doesn't exist (rethinkdb's ``get(id).update(...)``
        returns silently). Caller is responsible for validating ``id`` is
        present and for any sanitization.
        """
        cls._validate_table(table)
        with cls._rdb_context():
            r.table(table).get(data["id"]).update(data).run(cls._rdb_connection)

    @classmethod
    def delete_table_item(cls, table: str, item_id: str) -> None:
        """Delete a row from ``table`` by id.

        Raises ``not_found`` if the row doesn't exist, or
        ``internal_server`` if the delete returns ``deleted == 0``.
        Caller is responsible for any pre-delete cleanup (e.g.
        unassigning the resource from desktops/deployments).
        """
        from isardvdi_common.helpers.error_factory import Error

        cls._validate_table(table)
        with cls._rdb_context():
            item = r.table(table).get(item_id).run(cls._rdb_connection)
            if not item:
                raise Error(
                    "not_found",
                    "Item " + str(item_id) + " not found",
                    description_code="not_found",
                )
            result = r.table(table).get(item_id).delete().run(cls._rdb_connection)
            if not result.get("deleted"):
                raise Error(
                    "internal_server",
                    "Delete of " + str(item_id) + " returned deleted=0",
                    traceback.format_exc(),
                    description_code="generic_error",
                )

    @classmethod
    def admin_table_list(
        cls,
        table,
        order_by=None,
        pluck=None,
        without=None,
        id=None,
        index=None,
        merge=None,
    ):
        """_From api/libv2/api_admin.py admin_table_list()_

        Fetches a list of items from a table in the database. To be used by admin users.

        Parses the returned data to include additional information
        """
        # Check if table exists

        cls._validate_table(table)

        query = r.table(table)

        ## Apply secondary index or primary key, if any is provided

        if id and not index:
            query = query.get(id)
        elif id and index:
            query = query.get_all(id, index=index)

        ## Add merge data

        if table == "users":
            query = query.without(
                "password",
                "password_history",
                "api_key",
                "photo",
                {"vpn": {"wireguard": "keys"}},
            )

        if table == "media":
            query = query.merge(cls.parse_media_data_merge())

        if table == "hypervisors":
            query = query.merge(cls.parse_hypervisor_data_merge())

        if table == "deployments":
            query = query.merge(cls.parse_deployment_data_merge()).default(False)

        if table == "bookings_priority":
            query = query.merge(
                lambda priority: {
                    "role_names": r.table("roles")
                    .get_all(
                        r.args(
                            r.branch(
                                (priority["allowed"]["roles"] != False),
                                priority["allowed"]["roles"],
                                [],
                            )
                        )
                    )["name"]
                    .coerce_to("array"),
                    "category_names": r.table("categories")
                    .get_all(
                        r.args(
                            r.branch(
                                (priority["allowed"]["categories"] != False),
                                priority["allowed"]["categories"],
                                [],
                            )
                        )
                    )["name"]
                    .coerce_to("array"),
                    "group_names": r.table("groups")
                    .get_all(
                        r.args(
                            r.branch(
                                (priority["allowed"]["groups"] != False),
                                priority["allowed"]["groups"],
                                [],
                            )
                        )
                    )["name"]
                    .coerce_to("array"),
                    "user_names": r.table("users")
                    .get_all(
                        r.args(
                            r.branch(
                                (priority["allowed"]["users"] != False),
                                priority["allowed"]["users"],
                                [],
                            )
                        )
                    )["name"]
                    .coerce_to("array"),
                }
            )

        # Apply pluck, order_by or without

        if pluck:
            query = query.pluck(pluck)

        if order_by:
            query = query.order_by(order_by)

        if without:
            query = query.without(without)

        # Return the result

        if id and not index:
            with cls._rdb_context():
                return query.run(cls._rdb_connection)
        else:
            with cls._rdb_context():
                return list(query.run(cls._rdb_connection))

    @staticmethod
    def check_category_allowed_table(table):
        """_From api/libv2/api_admin.py check_category_allowed_table()_"""
        from isardvdi_common.helpers.error_factory import Error

        allowed_tables = [
            "users",
            "groups",
            "deployments",
            "media",
            "domains",
            "hypervisors",
            "virt_install",
            "categories",
        ]

        if table not in allowed_tables:
            raise Error(
                "forbidden",
                "Table not allowed to be listed by manager",
                traceback.format_exc(),
            )

    @staticmethod
    def get_category_limited_tables():
        """_From api/libv2/api_admin.py get_category_limited_tables()_"""
        return ["users", "groups", "deployments", "media", "domains"]

    @classmethod
    def manager_table_list(
        cls,
        table,
        category,
        order_by=None,
        pluck=None,
        without=None,
        id=None,
        index=None,
        merge=None,
    ):
        """_From api/libv2/api_admin.py manager_table_list()_

        Fetches a list of items from a table in the database. To be used by manager users.

        Filters the items by the category of the manager.

        Is limited by the table the manager is allowed to access.

        Parses the returned data to include additional information
        """

        # Define allowed tables for manager and category limited tables

        cls.check_category_allowed_table(table)
        CATEGORY_LIMITED_TABLES = cls.get_category_limited_tables()
        query = r.table(table)

        ## Apply secondary index or primary key, if any is provided

        if table == "categories":
            query = query.get(category)
        elif id and not index:
            query = query.get(id)
        elif id and index:
            query = query.get_all(id, index=index)

        ## Check category limited tables

        if not id and not index and table in CATEGORY_LIMITED_TABLES:
            if table == "groups":
                query = query.get_all(category, index="parent_category")
            elif (
                table != "deployments"
            ):  ## deployment table does not have category index
                query = query.get_all(category, index="category")

        elif not id and index and table in CATEGORY_LIMITED_TABLES:
            if table == "groups":
                query = query.filter({"parent_category": category})
            elif (
                table != "deployments"
            ):  ## deployments do not have category field in the database
                query = query.filter({"category": category})

        ## Add merge data

        if table == "users":
            query = query.without(
                "password",
                "password_history",
                "api_key",
                "photo",
                {"vpn": {"wireguard": "keys"}},
            )

        if table == "media":
            query = query.merge(cls.parse_media_data_merge())

        if table == "hypervisors":
            query = query.merge(cls.parse_hypervisor_data_merge())

        if table == "deployments":
            query = (
                query.merge(cls.parse_deployment_data_merge())
                .filter({"category": category})
                .default(False)
            )

        # Apply pluck, order_by or without

        if pluck:
            query = query.pluck(pluck)

        if order_by:
            query = query.order_by(order_by)

        if without:
            query = query.without(without)

        # Return the result

        if id and not index:
            from isardvdi_common.helpers.error_factory import Error

            with cls._rdb_context():
                item = query.run(cls._rdb_connection)
            if table in CATEGORY_LIMITED_TABLES:
                item_category = item.get("category") or item.get("parent_category")
                if item_category != category:
                    raise Error(
                        "forbidden",
                        "Not enough access rights to access this item",
                        traceback.format_exc(),
                    )

            return item
        else:
            with cls._rdb_context():
                return list(query.run(cls._rdb_connection))

    @classmethod
    def DesktopViewerData(cls, desktop_id):
        """_From api/libv2/api_admin.py ApiAdmin.DesktopViewerData()_

        Returns ``None`` if the desktop doesn't exist so the caller can
        translate that into a typed 404 instead of a generic 500. Wrapping
        with ``.default(None)`` before ``.pluck()`` keeps the query
        single-roundtrip.
        """
        with cls._rdb_context():
            desktop = (
                r.table("domains")
                .get(desktop_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if desktop is None:
            return None
        return {
            "guest_properties": desktop.get("guest_properties"),
            "create_dict": {
                "hardware": {
                    "interfaces": [
                        i["id"] if isinstance(i, dict) else i
                        for i in (
                            desktop.get("create_dict", {})
                            .get("hardware", {})
                            .get("interfaces", [])
                        )
                    ]
                },
                **{
                    k: v
                    for k, v in (desktop.get("create_dict") or {}).items()
                    if k != "hardware"
                },
            },
            "viewer": {"guest_ip": (desktop.get("viewer") or {}).get("guest_ip")},
        }

    @classmethod
    def DeploymentViewerData(cls, deployment_id):
        """_From api/libv2/api_admin.py ApiAdmin.DeploymentViewerData()_

        Returns ``None`` for missing deployments (see DesktopViewerData).
        """
        with cls._rdb_context():
            deployment = (
                r.table("deployments")
                .get(deployment_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if deployment is None:
            return None
        return {"create_dict": deployment.get("create_dict")}

    @classmethod
    def DesktopDetailsData(cls, desktop_id):
        """_From api/libv2/api_admin.py ApiAdmin.DesktopDetailsData()_

        Returns ``None`` for missing desktops (see DesktopViewerData).
        """
        with cls._rdb_context():
            desktop = (
                r.table("domains")
                .get(desktop_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if desktop is None:
            return None
        return {
            "detail": desktop.get("detail"),
            "description": desktop.get("description"),
        }

    @classmethod
    def ListDesktops(cls, categories=None, bastion=True):
        """_From api/libv2/api_admin.py ApiAdmin.ListDesktops()_"""
        query = r.table("categories")
        if categories:
            query = query.get_all(r.args(categories))
        query = query.eq_join("id", r.table("groups"), index="parent_category")
        query = query.map(
            lambda doc: {
                "group_id": doc["right"]["id"],
                "group_name": doc["right"]["name"],
                "category_id": doc["left"]["id"],
                "category_name": doc["left"]["name"],
            }
        )
        query = query.eq_join("group_id", r.table("domains"), index="group").filter(
            {"right": {"kind": "desktop"}}
        )
        query = query.merge(
            lambda doc: {
                "right": r.table("users")
                .get(doc["right"]["user"])
                .pluck("role", "name")
                .merge(lambda user: {"user_name": user["name"], "role": user["role"]})
                .without("name")
            }
        )

        query = query.pluck(
            {
                "right": [
                    "id",
                    {
                        "create_dict": {
                            "reservables": True,
                            "hardware": {"vcpus": True, "memory": True},
                        }
                    },
                    {"image": {"url": True}},
                    "kind",
                    "server",
                    "hyp_started",
                    "name",
                    "status",
                    "user_name",
                    "accessed",
                    "forced_hyp",
                    "favourite_hyp",
                    "booking_id",
                    "role",
                    "persistent",
                    "current_action",
                    "server_autostart",
                ],
                "left": ["group_name", "category_name"],
            }
        ).zip()

        if bastion:
            query = query.merge(
                lambda doc: {
                    "bastion": r.branch(
                        r.table("targets")
                        .get_all(doc["id"], index="desktop_id")
                        .is_empty(),
                        None,
                        r.table("targets")
                        .get_all(doc["id"], index="desktop_id")
                        .pluck("id", "domain", "http", "ssh")
                        .nth(0),
                    ),
                }
            )

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def GetTemplate(cls, template_id):
        """_From api/libv2/api_admin.py ApiAdmin.GetTemplate()_"""
        try:
            with cls._rdb_context():
                return (
                    r.table("domains")
                    .get(template_id)
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "username",
                        "category",
                        "group",
                        "enabled",
                        "derivates",
                        "accessed",
                        "detail",
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "forced_hyp": True,
                                    "favourite_hyp": True,
                                },
                                "origin": True,
                                "reservables": True,
                            }
                        },
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all(template_id, index="parents")
                            .count()
                            .add(
                                r.db("isard")
                                .table("deployments")
                                .get_all(template_id, index="template")
                                .count()
                            ),
                            "category_name": r.table("categories")
                            .get(domain["category"])["name"]
                            .default(False),
                            "group_name": r.table("groups")
                            .get(domain["group"])["name"]
                            .default(False),
                            "interfaces": domain["create_dict"]["hardware"][
                                "interfaces"
                            ].keys(),
                        }
                    )
                    .run(cls._rdb_connection)
                )
        except Exception:
            from isardvdi_common.helpers.error_factory import Error

            raise Error(
                "internal_server",
                "Internal server error ",
                traceback.format_exc(),
            )

    @classmethod
    def ListTemplates(cls, category=None):
        """_From api/libv2/api_admin.py ApiAdmin.ListTemplates()_"""
        if not category:
            query = r.table("domains").get_all("template", index="kind")
        else:
            query = r.table("domains").get_all(
                ["template", category], index="kind_category"
            )

        query = (
            query.eq_join("group", r.table("groups"))
            .map(
                lambda template: template["left"]
                .merge(
                    {
                        "group_id": template["right"]["id"],
                        "group_name": template["right"]["name"],
                        "category_id": template["right"]["parent_category"],
                    }
                )
                .without("right")
            )
            .eq_join("category_id", r.table("categories"))
            .map(
                lambda template: template["left"]
                .merge(
                    {
                        "category_name": template["right"]["name"],
                    }
                )
                .without("right")
            )
            .eq_join("user", r.table("users"))
            .map(
                lambda template: template["left"].merge(
                    {"user_name": template["right"]["name"]}
                )
            )
            .pluck(
                [
                    "id",
                    "icon",
                    "image",
                    "name",
                    "kind",
                    "description",
                    "user_name",
                    "enabled",
                    "accessed",
                    "detail",
                    {
                        "create_dict": {
                            "origin": True,
                            "reservables": True,
                        }
                    },
                    "forced_hyp",
                    "favourite_hyp",
                    "category",
                    "group_name",
                    "category_name",
                ]
            )
            .merge(
                lambda domain: {
                    "derivates": r.table("domains")
                    .get_all(domain["id"], index="parents")
                    .distinct()
                    .count()
                    .add(
                        r.table("deployments")
                        .get_all(domain["id"], index="template")
                        .count()
                    )
                }
            )
        )
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def domains_status_minimal(cls, status):
        """_From api/libv2/api_admin.py ApiAdmin.domains_status_minimal()_"""
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all(["desktop", status], index="kind_status")
                .pluck(
                    "id",
                    "name",
                    "accessed",
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_domain_storage(cls, domain_id):
        """_From api/libv2/api_admin.py ApiAdmin.get_domain_storage()_

        Returns ``[]`` for missing domains so the caller can translate
        the empty list into a typed 404 instead of crashing on a
        ``pluck on null`` ReqlNonExistenceError.
        """
        with cls._rdb_context():
            desktop = (
                r.table("domains").get(domain_id).default(None).run(cls._rdb_connection)
            )
        if desktop is None:
            return []
        desktop_disks = (
            (desktop.get("create_dict") or {}).get("hardware", {}).get("disks", [])
        )

        storage_ids = []
        for storage in desktop_disks:
            if isinstance(storage, dict) and storage.get("storage_id"):
                storage_ids.append(storage.get("storage_id"))

        with cls._rdb_context():
            return list(
                r.table("storage")
                .get_all(r.args(storage_ids))
                .merge(
                    lambda storage: {
                        "actual_size": storage["qemu-img-info"]["actual-size"].default(
                            0
                        )
                        / 1073741824,
                        "virtual_size": storage["qemu-img-info"][
                            "virtual-size"
                        ].default(0)
                        / 1073741824,
                    }
                )
                .run(cls._rdb_connection)
            )

    # This is the function to be called
    @classmethod
    def get_template_tree_list(cls, template_id, user_id):
        """_From api/libv2/api_admin.py ApiAdmin.get_template_tree_list()_

        Pre-validates that ``template_id`` exists so the downstream
        ``r.table("domains").get(template_id).merge(...).pluck(...)``
        chain doesn't ReqlNonExistenceError on a null pluck.
        """
        with cls._rdb_context():
            if (
                r.table("domains")
                .get(template_id)
                .default(None)
                .run(cls._rdb_connection)
            ) is None:
                from isardvdi_common.helpers.error_factory import Error

                raise Error("not_found", f"Template {template_id} not found")

        levels = {}
        derivated = cls.template_tree_list(template_id, user_id)
        for n in derivated:
            levels.setdefault(
                (
                    n["duplicate_parent_template"]
                    if n.get("duplicate_parent_template", False)
                    else n["parent"]
                ),
                [],
            ).append(n)
        recursion = cls.template_tree_recursion(template_id, levels)
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "role")
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            d = (
                r.table("domains")
                .get(template_id)
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "category_name",
                    "duplicate_parent_template",
                    "group",
                    "group_name",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .run(cls._rdb_connection)
            )
        root = [
            {
                "id": d["id"],
                "title": d["name"],
                "expanded": True,
                "unselectable": (
                    False
                    if user["role"] == "manager" or user["role"] == "admin"
                    else True
                ),
                "selected": True if user["id"] == d["user"] else False,
                "parent": (
                    d["parents"][-1]
                    if "parents" in d.keys() and len(d["parents"]) > 0
                    else ""
                ),
                "duplicate_parent_template": d.get("duplicate_parent_template", False),
                "user": d["username"],
                "category": d["category_name"],
                "group": d["group_name"],
                "kind": d["kind"] if d["kind"] == "desktop" else "template",
                "children": recursion,
            }
        ]
        return root

    # Call get_template_tree_list. This is a subfunction only.
    @classmethod
    def template_tree_recursion(cls, template_id, levels):
        """_From api/libv2/api_admin.py ApiAdmin.template_tree_recursion()_"""
        nodes = [dict(n) for n in levels.get(template_id, [])]
        for n in nodes:
            children = cls.template_tree_recursion(n["id"], levels)
            if children:
                n["children"] = children
        return nodes

    @classmethod
    def _derivated(cls, template_id):
        """_From api/libv2/api_admin.py ApiAdmin._derivated()_"""
        with cls._rdb_context():
            domains = list(
                r.db("isard")
                .table("domains")
                .get_all(template_id, index="parents")
                .pluck(
                    "id",
                    "duplicate_parent_template",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

        deployments = Helpers.get_template_derivated_deployments(template_id)

        return domains + deployments

    @classmethod
    def _duplicated(cls, template_id):
        """_From api/libv2/api_admin.py ApiAdmin._duplicated()_"""
        with cls._rdb_context():
            duplicated_from_original = list(
                r.table("domains")
                .get_all(template_id, index="duplicate_parent_template")
                .pluck(
                    "id",
                    "duplicate_parent_template",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .merge(
                    lambda d: {
                        "category_name": r.table("categories").get(d["category"])[
                            "name"
                        ],
                        "group_name": r.table("groups").get(d["group"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

        # Recursively get templates derived from duplicated templates
        derivated_from_duplicated = []
        for d in duplicated_from_original:
            derivated_from_duplicated += cls._derivated(d["id"])
        return duplicated_from_original + derivated_from_duplicated

    # TODO: Test when changing to apiv4
    # This has no recursion. Call get_template_tree_list
    @classmethod
    def template_tree_list(cls, template_id, user_id):
        """_From api/libv2/api_admin.py ApiAdmin.template_tree_list()_"""
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "role", "category")
                .run(cls._rdb_connection)
            )

        # Get derivated from this template (and derivated from itself)
        derivated = cls._derivated(template_id)

        # Duplicated templates should have the same parent as the original
        # Except for duplicates from root template
        duplicated = cls._duplicated(template_id)

        derivated = list(derivated) + list(duplicated)

        if user["role"] == "manager":
            derivated = [
                (
                    {
                        **d,
                        "user": "-",
                        "username": "-",
                        "category": "-",
                        "category_name": "-",
                        "group": "-",
                        "group_name": "-",
                        "unselectable": True,
                        "name": "-",
                    }
                    if d["category"] != user["category"]
                    else d
                )
                for d in derivated
            ]

        fancyd = []
        for d in derivated:
            if user["role"] == "manager" or user["role"] == "admin":
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "parent": (
                            d.get("template_id")
                            if d.get("kind") == "deployment"
                            else (
                                d["parents"][-1]
                                if d.get("parents")
                                else d["duplicate_parent_template"]
                            )
                        ),
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"],
                        "duplicate_parent_template": d.get(
                            "duplicate_parent_template", False
                        ),
                    }
                )
            else:
                ## It can only be an advanced user
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "parent": (
                            d.get("template_id")
                            if d.get("kind") == "deployment"
                            else (
                                d["parents"][-1]
                                if d.get("parents")
                                else d["duplicate_parent_template"]
                            )
                        ),
                        "user": d["username"],
                        "category": d["category_name"],
                        "group": d["group_name"],
                        "kind": d["kind"],
                        "duplicate_parent_template": d.get(
                            "duplicate_parent_template", False
                        ),
                    }
                )
        return fancyd

    @classmethod
    def TemplatesByTerm(cls, term):
        """_From api/libv2/api_admin.py ApiAdmin.TemplatesByTerm()_"""
        with cls._rdb_context():
            data = (
                r.table("domains")
                .get_all("template", index="kind")
                .filter(r.row["name"].match(term))
                .order_by("name")
                .pluck(
                    {
                        "id",
                        "name",
                        "kind",
                        "group",
                        "icon",
                        "user",
                        "description",
                        "category",
                    }
                )
                .run(cls._rdb_connection)
            )
        return data

    @classmethod
    def multiple_actions(cls, action, ids, agent_id):
        """Synchronously dispatch a bulk admin action.

        Originally fired ``gevent.spawn(process_bulk_action)`` so v3's
        Flask+gevent stack returned 200 immediately. Under apiv4
        (FastAPI on uvicorn/asyncio) the spawned greenlet sat on a
        libev Hub the asyncio worker never drives, so the work
        silently never ran (and risked a libev UAF SIGSEGV). Callers
        are now expected to schedule this method via FastAPI's
        ``BackgroundTasks`` (apiv4) or run it inline in a sync context.
        See APIV4_THREADING_INCIDENT_ANALYSIS.md §5.1.
        """
        if action == "soft_toggle":
            DesktopEvents.desktops_toggle(ids)

        if action == "toggle":
            DesktopEvents.desktops_toggle(ids, force=True)

        if action == "delete":
            DesktopEvents.desktops_delete(agent_id, ids)

        if action == "force_failed":
            DesktopEvents.desktops_force_failed(ids)

        if action == "shutting_down":
            DesktopEvents.desktops_stop(ids, force=False)

        if action == "stopping":
            DesktopEvents.desktops_stop(ids, force=True)

        if action == "starting_paused":
            DesktopEvents.desktops_start(ids, paused=True)

        if action == "remove_forced_hyper":
            DesktopEvents.remove_forced_hyper(ids)

        if action == "remove_favourite_hyper":
            DesktopEvents.remove_favourite_hyper(ids)

        if action == "activate_autostart":
            DesktopEvents.activate_autostart(ids)

        if action == "deactivate_autostart":
            DesktopEvents.deactivate_autostart(ids)

    @classmethod
    def get_domains_field(cls, field, kind, payload):
        """_From api/libv2/api_admin.py ApiAdmin.get_domains_field()_"""
        query = r.table("domains")

        if payload["role_id"] == "manager" and kind:
            query = query.get_all([kind, payload["category_id"]], index="kind_category")
        elif payload["role_id"] == "admin" and kind:
            query = query.get_all(kind, index="kind")
        elif payload["role_id"] == "manager" and not kind:
            query = query.get_all(payload["category_id"], index="category")

        if field not in ["vcpus", "memory"]:
            pluck = field
        else:
            pluck = {"create_dict": {"hardware": field}}
        query = query.pluck(pluck)

        query = (
            query["create_dict"]["hardware"] if field in ["vcpus", "memory"] else query
        )
        query = (
            query.map(lambda value: {"memory": (value["memory"] / 1048576)})
            if field == "memory"
            else query
        )

        with cls._rdb_context():
            result = query.distinct().run(cls._rdb_connection)
        return result

    @classmethod
    def set_logs_desktops_old_entries_max_time(cls, max_time):
        """_From api/libv2/api_admin.py ApiAdmin.set_logs_desktops_old_entries_max_time()_"""
        with cls._rdb_context():
            r.table("config").update(
                {"logs_desktops": {"old_entries": {"max_time": max_time}}}
            ).run(cls._rdb_connection)

    @classmethod
    def set_logs_desktops_old_entries_action(cls, action):
        """_From api/libv2/api_admin.py ApiAdmin.set_logs_desktops_old_entries_action()_"""
        if action == "none":
            with cls._rdb_context():
                r.table("config").replace(
                    r.row.without({"logs_desktops": "old_entries"})
                ).run(cls._rdb_connection)
        else:
            with cls._rdb_context():
                r.table("config").update(
                    {"logs_desktops": {"old_entries": {"action": action}}}
                ).run(cls._rdb_connection)

    @classmethod
    def get_logs_desktops_old_entries_config(cls):
        """_From api/libv2/api_admin.py ApiAdmin.get_logs_desktops_old_entries_config()_"""
        try:
            with cls._rdb_context():
                return r.table("config")[0]["logs_desktops"]["old_entries"].run(
                    cls._rdb_connection
                )
        except r.ReqlNonExistenceError:
            return {"max_time": None, "action": None}

    @classmethod
    def set_logs_users_old_entries_max_time(cls, max_time):
        """_From api/libv2/api_admin.py ApiAdmin.set_logs_users_old_entries_max_time()_"""
        with cls._rdb_context():
            r.table("config").update(
                {"logs_users": {"old_entries": {"max_time": max_time}}}
            ).run(cls._rdb_connection)

    @classmethod
    def set_logs_users_old_entries_action(cls, action):
        """_From api/libv2/api_admin.py ApiAdmin.set_logs_users_old_entries_action()_"""
        if action == "none":
            with cls._rdb_context():
                r.table("config").replace(
                    r.row.without({"logs_users": "old_entries"})
                ).run(cls._rdb_connection)
        else:
            with cls._rdb_context():
                r.table("config").update(
                    {"logs_users": {"old_entries": {"action": action}}}
                ).run(cls._rdb_connection)

    @classmethod
    def get_logs_users_old_entries_config(cls):
        """_From api/libv2/api_admin.py ApiAdmin.get_logs_users_old_entries_config()_"""
        try:
            with cls._rdb_context():
                return r.table("config")[0]["logs_users"]["old_entries"].run(
                    cls._rdb_connection
                )
        except r.ReqlNonExistenceError:
            return {"max_time": None, "action": None}

    @classmethod
    def get_older_than_old_entry_max_time(cls, table, max_time_config=None):
        """_From api/libv2/api_admin.py ApiAdmin.get_older_than_old_entry_max_time()_"""
        from isardvdi_common.helpers.error_factory import Error

        if table == "logs_desktops":
            if max_time_config is None:
                max_time_config = cls.get_logs_desktops_old_entries_config()["max_time"]
        elif table == "logs_users":
            if max_time_config is None:
                max_time_config = cls.get_logs_users_old_entries_config()["max_time"]
        else:
            raise Error(
                "forbidden",
                "Table not allowed to delete old entries",
                traceback.format_exc(),
            )

        if max_time_config is None:
            raise Error(
                "precondition_required",
                "Max time is not set",
                traceback.format_exc(),
            )

        max_time_hours = int(max_time_config)

        query = r.table(table)

        if table == "logs_desktops":
            query = query.filter(
                (
                    (r.row.has_fields("stopped_time"))
                    & (
                        r.row["stopped_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("stopping_time"))
                    & (
                        r.row["stopping_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("started_time"))
                    & (
                        r.row["started_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("starting_time"))
                    & (
                        r.row["starting_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
            )
        elif table == "logs_users":
            query = query.filter(
                (
                    (r.row.has_fields("stopped_time"))
                    & (
                        r.row["stopped_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
                | (
                    (r.row.has_fields("started_time"))
                    & (
                        r.row["started_time"]
                        < r.now().sub(r.expr(max_time_hours * 3600))
                    )
                )
            )

        query = query.pluck("id")["id"]

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))
