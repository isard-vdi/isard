import logging
import os
import random
import re
import string
import time
import traceback
import uuid
from datetime import datetime, timedelta
from threading import Semaphore

import pytz
from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.caches import Caches
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r

from .quotas import Quotas

log = logging.getLogger(__name__)


mac_gen_semaphore = Semaphore()


class Helpers(RethinkSharedConnection):

    @staticmethod
    def gen_random_mac():
        mac = [
            0x52,
            0x54,
            0x00,
            random.randint(0x00, 0x7F),
            random.randint(0x00, 0xFF),
            random.randint(0x00, 0xFF),
        ]
        return ":".join(map(lambda x: "%02x" % x, mac))

    @classmethod
    def gen_new_mac(cls):
        mac_gen_semaphore.acquire()
        try:
            new_mac = cls.gen_random_mac()
            # while app.macs_in_use.count(new_mac) > 0:
            #     new_mac = gen_random_mac()
            # app.macs_in_use.append(new_mac)
            return new_mac
        finally:
            mac_gen_semaphore.release()

    @classmethod
    def gen_random_password(cls, length=12):
        """Generates a random password with the given length."""
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))

    @classmethod
    def check_duplicates(
        cls,
        item_table,
        item_names,
        user,
        item_id=None,
        ignore_deleted=False,
        raise_error=True,
    ):
        query = (
            r.table(item_table)
            .get_all(r.args(item_names), index="name")
            .filter(lambda item: (item["id"] != item_id))
        )
        if user:
            query = query.filter({"user": user})
        if ignore_deleted:
            query = query.filter(lambda item: item["status"] != "deleted")
        with cls._rdb_context():
            items = list(query.run(cls._rdb_connection))
        if items and raise_error:
            raise Error(
                "conflict",
                'Items with these names: "'
                + ", ".join([item["name"] for item in items])
                + '" already exist in '
                + item_table,
                traceback.format_exc(),
                description_code="duplicated_name",
            )
        return items

    @classmethod
    def check_duplicate(
        cls,
        item_table,
        item_name,
        category=False,
        user=False,
        item_id=None,
        ignore_deleted=False,
    ):
        query = (
            r.table(item_table)
            .get_all(item_name, index="name")
            .filter(lambda item: (item["id"] != item_id))
        )

        # Check duplicate in the same category
        if category:
            if item_table == "groups":
                query = query.filter({"parent_category": category})
            else:
                query = query.filter({"category": category})

        # Check duplicate in the same user
        elif user:
            query = query.filter({"user": user})

        # Do not check deleted items
        if ignore_deleted:
            query = query.filter(lambda item: item["status"] != "deleted")

        with cls._rdb_context():
            items = list(query.run(cls._rdb_connection))

        if items:
            raise Error(
                "conflict",
                f"Item with this name: {item_name} already exists in {item_table}",
                traceback.format_exc(),
                description_code="duplicated_name",
            )

    @classmethod
    def check_duplicate_domains(
        cls,
        kind,
        domain_names,
        user,
        item_id=None,
        ignore_deleted=False,
        raise_error=True,
    ):
        query = (
            r.table("domains")
            .get_all([r.args(domain_names), user], index="name_user")
            .filter(lambda item: (item["id"] != item_id) and item["kind"] == kind)
        )
        if user:
            query = query.filter({"user": user})
        if ignore_deleted:
            query = query.filter(
                lambda item: item["status"] != DesktopStatusEnum.deleted.value
            )
        with cls._rdb_context():
            items = list(query.run(cls._rdb_connection))
        if items and raise_error:
            raise Error(
                "conflict",
                'Items with these names: "'
                + ", ".join([item["name"] for item in items])
                + '" already exist in domains',
                traceback.format_exc(),
                description_code="duplicated_name",
            )
        return items

    @classmethod
    def update_duplicated_names(cls, item_table, items_data, user, kind=None):
        """
        Appends "(migrated)" to the duplicated names in the item_names list

        :param item_table: The table where the items are stored
        :type item_table: str
        :param items_data: The items to update
        :type items_data: list
        :param user: The user id
        :type user: str
        :param kind: The kind of the item, either desktop or template
        :type kind: str

        """
        try:
            item_names = [item["name"] for item in items_data]
            if item_table == "domains":
                duplicated_items = cls.check_duplicate_domains(
                    kind, item_names, user, raise_error=False
                )
            else:
                duplicated_items = cls.check_duplicates(
                    item_table, item_names, user, raise_error=False
                )
            duplicated_names = [item["name"] for item in duplicated_items]
            items_to_update = [
                item["id"] for item in items_data if item["name"] in duplicated_names
            ]

            if items_to_update:
                with cls._rdb_context():
                    r.table(item_table).get_all(r.args(items_to_update)).update(
                        {"name": r.row["name"] + " (migrated)"}
                    ).run(cls._rdb_connection)
        except Exception as e:
            log.error(f"Error updating duplicated names: {e}")

    @classmethod
    def get_new_user_data(cls, user_id):
        with cls._rdb_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("username", "category", "group", "role", "id", "provider")
                .run(cls._rdb_connection)
            )
        new_user = {
            "username": user["username"],
            "category": user["category"],
            "group": user["group"],
            "user": user_id,
        }

        payload = {
            "role_id": user["role"],
            "category_id": user["category"],
            "user_id": user["id"],
            "group_id": user["group"],
            "provider": user["provider"],
        }

        return {"new_user": new_user, "payload": payload}

    @staticmethod
    def itemExists(item_table, item_id):
        item = Caches.get_document(item_table, item_id)
        if item is None:
            raise Error(
                "not_found",
                item_table + " not found id: " + item_id,
                traceback.format_exc(),
            )
        return True

    @staticmethod
    def _check(dict, action):
        """
        These are the actions:
        {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        """
        if dict[action] or dict["unchanged"]:
            return True
        if not dict["errors"]:
            return True
        return False

    @classmethod
    def desktops_stop(cls, desktops_ids, wait_seconds=30):
        with cls._rdb_context():
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": DesktopStatusEnum.shutting_down.value}
            ).update(
                {
                    "status": DesktopStatusEnum.stopping.value,
                    "accessed": int(time.time()),
                }
            ).run(
                cls._rdb_connection
            )
            r.table("domains").get_all(r.args(desktops_ids), index="id").filter(
                {"status": DesktopStatusEnum.started.value}
            ).update(
                {
                    "status": DesktopStatusEnum.stopping.value,
                    "accessed": int(time.time()),
                }
            ).run(
                cls._rdb_connection
            )
        return cls.wait_status(
            desktops_ids,
            current_status=DesktopStatusEnum.stopping.value,
            wait_seconds=wait_seconds,
        )

    @classmethod
    def wait_status(
        cls,
        desktops_ids,
        current_status,
        wait_seconds=0,
        interval_seconds=2,
        raise_exc=False,
    ):
        with cls._rdb_context():
            desktops_status = list(
                r.table("domains")
                .get_all(r.args(desktops_ids))
                .pluck("status")["status"]
                .run(cls._rdb_connection)
            )
        if wait_seconds == 0:
            return desktops_status
        seconds = 0
        while current_status in desktops_status and seconds <= wait_seconds:
            time.sleep(interval_seconds)
            seconds += interval_seconds
            with cls._rdb_context():
                try:
                    desktops_status = list(
                        r.table("domains")
                        .get_all(r.args(desktops_ids))
                        .pluck("status")["status"]
                        .run(cls._rdb_connection)
                    )
                except Exception:
                    raise Error(
                        "not_found",
                        "Desktop not found",
                        traceback.format_exc(),
                        description_code="not_found",
                    )
        if current_status in desktops_status:
            if raise_exc:
                raise Error(
                    "internal_server",
                    "Engine could not change "
                    + desktops_ids
                    + " status from "
                    + current_status
                    + " in "
                    + str(wait_seconds),
                    traceback.format_exc(),
                    description_code="generic_error",
                )
            else:
                return False
        return desktops_status

    # This has no recursion. Call get_template_tree_list
    @classmethod
    def template_tree_list(cls, template_id):
        # Get derivated from this template (and derivated from itself)
        derivated = cls._derivated(template_id)

        # Duplicated templates should have the same parent as the original
        # Except for duplicates from root template
        duplicated = cls._duplicated(template_id)

        derivated = list(derivated) + list(duplicated)

        domains = []
        for d in derivated:
            domains.append(
                {
                    "id": d["id"],
                    "parent": (
                        d["parents"][-1]
                        if d.get("parents")
                        else d["duplicate_parent_template"]
                    ),
                    "duplicate_parent_template": d.get(
                        "duplicate_parent_template", False
                    ),
                    "name": d["name"],
                    "kind": d["kind"],
                    "user": d["user"],
                    "category": d["category"],
                    "group": d["group"],
                    "username": d["username"],
                    "user_name": d["user_name"],
                    "persistent": d.get("persistent"),
                }
            )
        return domains

    # This is the function to be called
    @classmethod
    def get_template_with_all_derivatives(cls, template_id, user_id=None):
        """
        Get all derivatives of a template. The template itself is _included_ in the list.
        """
        # Pre-validate existence so the pluck/merge chain below doesn't
        # ReqlNonExistenceError on a missing template (e.g. webapp click
        # on a stale row that's already been deleted by another admin).
        with cls._rdb_context():
            existing = (
                r.table("domains")
                .get(template_id)
                .default(None)
                .run(cls._rdb_connection)
            )
        if existing is None:
            raise Error(
                "not_found",
                f"Template {template_id} not found",
                description_code="template_not_found",
            )
        levels = {}
        derivated = cls.template_tree_list(template_id)
        with cls._rdb_context():
            template = (
                r.table("domains")
                .get(template_id)
                .pluck("user", "name", "category", "group", "duplicate_parent_template")
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )
        for n in derivated:
            levels.setdefault(
                (
                    n["duplicate_parent_template"]
                    if n.get("duplicate_parent_template", False)
                    else n["parent"]
                ),
                [],
            ).append(n)
        all_domains_id = [
            {
                "id": template_id,
                "name": template["name"],
                "kind": "template",
                "user": template["user"],
                "category": template["category"],
                "group": template["group"],
                "username": template["username"],
                "user_name": template["user_name"],
                "duplicate_parent_template": template.get("duplicate_parent_template"),
            }
        ]
        if user_id:
            with cls._rdb_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "category", "role")
                    .run(cls._rdb_connection)
                )
        for key, value in levels.items():
            for t in value:
                if not user_id or (
                    (user["role"] == "admin")
                    or (user["role"] == "manager" and t["category"] == user["category"])
                    or (user["role"] == "advanced" and t["user"] == user["id"])
                ):
                    all_domains_id.append(
                        {
                            "id": t["id"],
                            "name": t["name"],
                            "kind": t["kind"],
                            "user": t["user"],
                            "category": t["category"],
                            "group": t["group"],
                            "username": t["username"],
                            "user_name": t["user_name"],
                            "duplicate_parent_template": t.get(
                                "duplicate_parent_template"
                            ),
                            "persistent": t.get("persistent"),
                        }
                    )
                else:
                    raise Error(
                        "forbidden",
                        "This template has derivatives not owned by your category",
                        traceback.format_exc(),
                    )
        return all_domains_id

    # TODO: Test when changing to apiv4
    @classmethod
    def get_template_derivated_deployments(cls, template_id):
        """
        Get all deployments derivated from a template.
        """
        derivated_templates = cls._derivated_templates(template_id) + cls._duplicated(
            template_id
        )
        derivated_template_ids = [t["id"] for t in derivated_templates]
        with cls._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(r.args(derivated_template_ids), index="template")
                .pluck("id", "name", "user", "group")
                .merge(
                    lambda d: {
                        "user_data": r.table("users")
                        .get(d["user"])
                        .pluck("username", "name", "category", "group")
                    }
                )
                .merge(
                    lambda d: {
                        "username": d["user_data"]["username"],
                        "user_name": d["user_data"]["name"],
                        "category": d["user_data"]["category"],
                        "category_name": r.table("categories").get(
                            d["user_data"]["category"]
                        )["name"],
                        "group_name": r.table("groups").get(d["user_data"]["group"])[
                            "name"
                        ],
                        "kind": "deployment",
                        "template_id": template_id,  # Return the origin template for the dependency tree
                    }
                )
                .without("user_data")
                .run(cls._rdb_connection)
            )
        return deployments

    # TODO: Test when changing to apiv4
    @classmethod
    # Retrieves only derivated templates.
    def _derivated_templates(cls, template_id):
        """
        Retrieves only derivated templates from a given template.

        :param template_id: The ID of the template to get derivatives from
        :type template_id: str
        :return: A list of template dictionaries including the original template
        :rtype: list
        """
        with cls._rdb_context():
            # Get all templates derived from the given template
            derivated = list(
                r.table("domains")
                .get_all(template_id, index="parents")
                .filter({"kind": "template"})
                .pluck(
                    "id",
                    "name",
                    "parents",
                    "duplicate_parent_template",
                    "user",
                    "group",
                    "category",
                    "kind",
                )
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

            # Get the original template. Raise typed not_found if the
            # template row is gone — otherwise the pluck below raises
            # ReqlNonExistenceError on null, which routes surface as 500.
            raw = r.table("domains").get(template_id).run(cls._rdb_connection)
            if raw is None:
                raise Error(
                    "not_found",
                    f"Template {template_id} not found",
                    description_code="template_not_found",
                )
            original = (
                r.table("domains")
                .get(template_id)
                .pluck(
                    "id",
                    "name",
                    "parents",
                    "duplicate_parent_template",
                    "user",
                    "group",
                    "category",
                    "kind",
                )
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

            # Combine results, with original template first
            return [original] + derivated if original else derivated

    @classmethod
    def _derivated(cls, template_id):
        """
        Retrieves all the derivated domains from a template, including desktops.

        :param template_id: The ID of the template to get derivatives from
        :type template_id: str
        :return: A list of domain dictionaries including desktops
        :rtype: list
        """
        with cls._rdb_context():
            return list(
                r.db("isard")
                .table("domains")
                .get_all(template_id, index="parents")
                .pluck(
                    "id",
                    "name",
                    "parents",
                    "duplicate_parent_template",
                    "user",
                    "group",
                    "category",
                    "kind",
                    "persistent",
                )
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def _duplicated(cls, template_id):
        with cls._rdb_context():
            duplicated_from_original = list(
                r.table("domains")
                .get_all(template_id, index="duplicate_parent_template")
                .pluck(
                    "id",
                    "name",
                    "parents",
                    "duplicate_parent_template",
                    "user",
                    "group",
                    "category",
                    "kind",
                )
                .merge(
                    lambda d: {
                        "username": r.table("users").get(d["user"])["username"],
                        "user_name": r.table("users").get(d["user"])["name"],
                    }
                )
                .run(cls._rdb_connection)
            )

        # Recursively get templates derived from duplicated templates
        derivated_from_duplicated = []
        for d in duplicated_from_original:
            derivated_from_duplicated += cls._derivated(d["id"])
        return duplicated_from_original + derivated_from_duplicated

    @classmethod
    def unassign_item_from_resource(cls, item_id, item_type, table):
        """

        Unassigns the given user from all the items of the given table.

        :param item_id: The id of the item to unassign
        :type item_id: str
        :param item_type: The type of the item to unassign. Can be user, group or category
        :type item_type: str
        :param table: The resource table to unassign the user from
        :type table: str

        """
        items = cls.get_resources_with_item_in_allowed(item_id, item_type, table)
        for i in range(0, len(items), 200):
            batch_ids = items[i : i + 200]
            if table == "deployments":
                with cls._rdb_context():
                    r.table("deployments").get_all(
                        r.args(batch_ids), index="id"
                    ).update(
                        {
                            "create_dict": {
                                "allowed": {
                                    item_type: r.branch(
                                        r.row["create_dict"]["allowed"][item_type]
                                        .difference([item_id])
                                        .is_empty(),
                                        False,
                                        r.row["create_dict"]["allowed"][
                                            item_type
                                        ].difference([item_id]),
                                    )
                                }
                            }
                        }
                    ).run(
                        cls._rdb_connection
                    )
            else:
                with cls._rdb_context():
                    r.table(table).get_all(r.args(batch_ids), index="id").update(
                        {
                            "allowed": {
                                item_type: r.branch(
                                    r.row["allowed"][item_type]
                                    .difference([item_id])
                                    .is_empty(),
                                    False,
                                    r.row["allowed"][item_type].difference([item_id]),
                                )
                            }
                        }
                    ).run(cls._rdb_connection)

    @classmethod
    def get_resources_with_item_in_allowed(cls, item_id, item_type, table):
        """

        Retrieves all the resources in the table that the given item is in the allowed field.

        :param item_id: The id to search for
        :type item_id: str
        :param item_type: The type of the item to search for. Can be user, group or category
        :type item_type: str
        :param table: The resource table to search in
        :type table: str
        :return: A list of item ids from the given table
        :rtype: list
        """
        try:
            with cls._rdb_context():
                items = r.table(table)
                # Note: In the domains table only templates consider the allowed field
                if table == "domains":
                    items = items.get_all("template", index="kind")
                items = list(
                    items.filter(
                        lambda doc: (
                            doc["create_dict"]["allowed"][item_type].ne(False)
                            & doc["create_dict"]["allowed"][item_type].contains(item_id)
                            if table == "deployments"
                            else doc["allowed"][item_type].ne(False)
                            & doc["allowed"][item_type].contains(item_id)
                        )
                    )
                    .pluck("id")["id"]
                    .run(cls._rdb_connection)
                )
        except Exception:
            items = []
        return items

    @classmethod
    def set_current_booking(cls, desktop):
        if not desktop["create_dict"].get("reservables") or not any(
            list(desktop["create_dict"]["reservables"].values())
        ):
            return
        item_id = desktop["id"]
        item_type = "desktop"
        with cls._rdb_context():
            booking = (
                r.table("bookings")
                .get_all([item_type, item_id], index="item_type-id")
                .filter(lambda b: ((b["start"]) < r.now()) & (b["end"] > r.now()))
                .order_by("start")
                .run(cls._rdb_connection)
            )
        if not booking and desktop.get("tag"):
            with cls._rdb_context():
                booking = (
                    r.table("bookings")
                    .get_all(["deployment", desktop.get("tag")], index="item_type-id")
                    .filter(lambda b: ((b["start"]) < r.now()) & (b["end"] > r.now()))
                    .order_by("start")
                    .run(cls._rdb_connection)
                )

        if booking:
            with cls._rdb_context():
                r.table("domains").get(desktop["id"]).update(
                    {"booking_id": booking[0]["id"]}
                ).run(cls._rdb_connection)
        return

    @classmethod
    def parse_domain_insert(cls, new_data):
        if new_data.get("hardware") is None:
            new_data["hardware"] = {}
        hardware = new_data["hardware"]
        if (hardware.get("reservables") or {}).get("vgpus") == ["None"]:
            hardware["reservables"]["vgpus"] = None

        interfaces = hardware.get("interfaces") or []
        new_data["hardware"]["interfaces"] = []
        for interface in interfaces:
            new_data["hardware"]["interfaces"].append(
                {"id": interface, "mac": cls.gen_new_mac()}
            )
        return new_data

    @classmethod
    def gen_interfaces_macs(cls, interfaces):
        """
        Generates a list of interfaces with random MAC addresses.
        :param interfaces: List of interface IDs
        :return: List of dictionaries with interface ID and generated MAC address
        """
        return [{"id": interface, "mac": cls.gen_new_mac()} for interface in interfaces]

    @classmethod
    def _parse_media_info(cls, create_dict):
        medias = ["isos", "floppies", "storage"]
        for m in medias:
            if m in create_dict["hardware"]:
                create_dict["hardware"][m] = [
                    {"id": item["id"] if isinstance(item, dict) else item}
                    for item in create_dict["hardware"][m]
                ]
        return create_dict

    @classmethod
    def gen_payload_from_user(cls, user_id, invalidate_cache=False):
        user = Caches.get_document("users", user_id, invalidate=invalidate_cache)
        return {
            "provider": user["provider"],
            "user_id": user["id"],
            "name": user["name"],
            "uid": user["uid"],
            "username": user["username"],
            "photo": user.get("photo", ""),
            "role_id": user["role"],
            "role_name": Caches.get_document("roles", user["role"], ["name"]),
            "category_id": user["category"],
            "category_name": Caches.get_document(
                "categories", user["category"], ["name"]
            ),
            "group_id": user["group"],
            "group_name": Caches.get_document("groups", user["group"], ["name"]),
        }

    TIMEDELTA_REGEX = (
        r"((?P<days>-?\d+)d)?" r"((?P<hours>-?\d+)h)?" r"((?P<minutes>-?\d+)m)?"
    )
    TIMEDELTA_PATTERN = re.compile(TIMEDELTA_REGEX, re.IGNORECASE)

    @classmethod
    def parse_delta(cls, delta):
        """Parses a human readable timedelta (3d5h19m) into a datetime.timedelta.
        Delta includes:
        * Xd days
        * Xh hours
        * Xm minutes
        Values can be negative following timedelta's rules. Eg: -5h-30m
        """
        match = cls.TIMEDELTA_PATTERN.match(delta)
        if match:
            parts = {k: int(v) for k, v in match.groupdict().items() if v}
            return timedelta(**parts)

    @classmethod
    def bastion_enabled(cls):
        if os.getenv(
            "BASTION_ENABLED", "false"
        ).lower() == "true" and Caches.get_document("config", 1, ["bastion"]).get(
            "enabled"
        ):
            return True
        return False

    @classmethod
    def can_use_bastion(cls, payload):
        if not cls.bastion_enabled():
            return False

        bastion_allowed = Caches.get_document("config", 1, ["bastion"])
        if bastion_allowed is None:
            return False

        return Alloweds.is_allowed(payload, bastion_allowed, "config", True)

    @classmethod
    def can_use_bastion_individual_domains(cls, payload):
        if not cls.can_use_bastion(payload):
            return False

        bastion_allowed = Caches.get_document("config", 1, ["bastion"]).get(
            "individual_domains"
        )
        if bastion_allowed is None:
            return False

        return Alloweds.is_allowed(payload, bastion_allowed, "config", True)

    # TODO: Evaluate if this is needed. Perhaps schema validation is enough.
    @staticmethod
    def _is_frontend_desktop_status(status):
        frontend_desktop_status = [
            DesktopStatusEnum.creating.value,
            DesktopStatusEnum.creating_and_starting.value,
            DesktopStatusEnum.shutting_down.value,
            DesktopStatusEnum.stopping.value,
            DesktopStatusEnum.stopped.value,
            DesktopStatusEnum.starting.value,
            DesktopStatusEnum.started.value,
            DesktopStatusEnum.waiting_ip.value,
            DesktopStatusEnum.failed.value,
            DesktopStatusEnum.downloading.value,
            DesktopStatusEnum.download_starting.value,
            DesktopStatusEnum.updating.value,
            DesktopStatusEnum.maintenance.value,
            DesktopStatusEnum.unknown.value,
        ]
        return True if status in frontend_desktop_status else False

    @classmethod
    def is_future(cls, event):
        return True if event["start"] > datetime.now(pytz.utc) else False

    @classmethod
    @cached(TTLCache(maxsize=100, ttl=10))
    def category_name_group_name_match(cls, category_name, group_name):
        """_From api/views/decorators.py CategoryNameGroupNameMatch()"""
        with cls._rdb_context():
            category = list(
                r.table("categories")
                .get_all(category_name.strip(), index="name")
                .run(cls._rdb_connection)
            )
        if not len(category):
            raise Error(
                "bad_request",
                "Category name " + category_name + " not found",
                traceback.format_exc(),
            )

        with cls._rdb_context():
            group = list(
                r.table("groups")
                .get_all(category[0]["id"], index="parent_category")
                .filter({"name": group_name.strip()})
                .run(cls._rdb_connection)
            )

        if not len(group):
            raise Error(
                "bad_request",
                "Group name " + group_name + " not found in category " + category_name,
                traceback.format_exc(),
            )

        if group[0]["parent_category"] == category[0]["id"]:
            return {
                "category_id": category[0]["id"],
                "category": category[0]["name"],
                "group_id": group[0]["id"],
                "group": group[0]["name"],
            }

        raise Error(
            "bad_request",
            "Category name "
            + category_name
            + " does not have child group name "
            + group_name,
            traceback.format_exc(),
        )

    def owns_user_id(payload, user_id):
        if payload["role_id"] == "admin":
            return True
        if payload.get("category_id") == "*":
            return True
        if payload["role_id"] == "manager":
            user = Caches.get_document("users", user_id, ["category", "role"])
            # A manager never owns an admin, even within their own category.
            if (
                user
                and user.get("category") == payload["category_id"]
                and user.get("role") != "admin"
            ):
                return True
        raise Error(
            "forbidden",
            "Not enough access rights for this user_id: " + str(user_id),
            traceback.format_exc(),
        )

    def owns_category_id(payload, category_id):
        """_From api/views/decorators.py ownsCategoryId()"""
        if payload["role_id"] == "admin":
            return True
        if payload["role_id"] == "manager" and category_id == payload["category_id"]:
            return True
        raise Error(
            "forbidden",
            "Not enough access rights for this category_id: " + str(category_id),
            traceback.format_exc(),
        )

    def revoke_hardware_permissions(domain_data, payload):
        domain_data["create_dict"]["hardware"]["memory"] = (
            domain_data["create_dict"]["hardware"]["memory"] / 1024 / 1024
        )

        Quotas.limit_user_hardware_allowed(payload, domain_data["create_dict"])

        domain_data["create_dict"]["hardware"]["memory"] = (
            domain_data["create_dict"]["hardware"]["memory"] * 1024 * 1024
        )

    ## change owner (individual resources)

    @classmethod
    def change_owner_desktop(cls, user_id, desktop_id):
        with cls._rdb_context():
            desktop_data = (
                r.table("domains")
                .get(desktop_id)
                .pluck("name", "user")
                .run(cls._rdb_connection)
            )
        user_data = cls.get_new_user_data(user_id)
        cls.change_owner_desktops([desktop_id], user_data, desktop_data["user"])

    @classmethod
    def change_owner_template(cls, user_id, template_id):
        user_data = cls.get_new_user_data(user_id)
        cls.change_owner_templates([template_id], user_data)

    @classmethod
    def change_owner_media(cls, user_id, media_id):
        user_data = cls.get_new_user_data(user_id)
        cls.change_owner_medias([media_id], user_data)

    ## change owner (bulk resources)

    @classmethod
    def change_owner_domains(cls, domain_ids, user_data, kind):
        if not domain_ids:
            return
        # Get desktop data
        domain_data_list = []
        for i in range(0, len(domain_ids), 100):
            batch_domain_ids = domain_ids[i : i + 100]
            with cls._rdb_context():
                batch_domain_data = (
                    r.table("domains")
                    .get_all(r.args(batch_domain_ids))
                    .pluck(
                        "create_dict", "kind", "tag", "name", "id", "category", "name"
                    )
                    .run(cls._rdb_connection)
                )
            domain_data_list.extend(batch_domain_data)

        if not domain_data_list:
            return

        cls.update_duplicated_names(
            "domains",
            domain_data_list,
            user=user_data["new_user"]["user"],
            kind=kind,
        )

        ## if new owner is from another category, delete
        # permissions of groups and users of old category
        if user_data["new_user"]["category"] is not domain_data_list[0]["category"]:
            user_data["new_user"]["allowed"] = {
                "categories": False,
                "groups": False,
                "users": False,
            }

        for domain in domain_data_list:
            cls.revoke_hardware_permissions(domain, user_data["payload"])
            cls.change_storage_ownership(domain, user_data["new_user"]["user"])

        # change owner
        for i in range(0, len(domain_ids), 100):
            batch_domain_ids = domain_ids[i : i + 100]
            with cls._rdb_context():
                r.table("domains").get_all(r.args(batch_domain_ids)).filter(
                    {"persistent": False}
                ).delete().run(cls._rdb_connection)
                r.table("domains").get_all(r.args(batch_domain_ids)).update(
                    {**user_data["new_user"], "booking_id": False}
                ).run(cls._rdb_connection)

    @classmethod
    def change_owner_desktops(cls, desktop_ids, user_data, desktop_user_id):
        cls.desktops_stop(desktop_ids)
        # Deployment desktops must be ignored when checking the new user quotas
        with cls._rdb_context():
            user_desktops = list(
                r.table("domains")
                .get_all(r.args(desktop_ids))
                .pluck("id", "tag")
                .run(cls._rdb_connection)
            )
        not_deployment_desktops = list(
            filter(lambda desktop: (desktop.get("tag") in [None, False]), user_desktops)
        )
        if Quotas.get_user_migration_check_quota_config():
            Quotas.desktop_create(
                user_data["new_user"]["user"], len(not_deployment_desktops)
            )
        # delete old bookings
        with cls._rdb_context():
            r.table("bookings").get_all(desktop_user_id, index="user_id").delete().run(
                cls._rdb_connection
            )
        # remove bastion targets
        with cls._rdb_context():
            r.table("targets").get_all(
                r.args(desktop_ids), index="desktop_id"
            ).delete().run(cls._rdb_connection)

        # remove direct viewer urls
        with cls._rdb_context():
            r.table("domains").get_all(r.args(desktop_ids)).update(
                {"jumperurl": False}
            ).run(cls._rdb_connection)

        cls.change_owner_domains(desktop_ids, user_data, "desktop")

    @classmethod
    def change_owner_templates(cls, template_ids, user_data):
        if user_data["payload"]["role_id"] == "user":
            raise Error("bad_request", 'Role "user" can not own templates.')
        if Quotas.get_user_migration_check_quota_config():
            Quotas.template_create(
                user_data["new_user"]["user"],
                len(template_ids),
            )
        cls.change_owner_domains(template_ids, user_data, "template")

    @classmethod
    def change_owner_medias(cls, media_ids, user_data):
        if user_data["payload"]["role_id"] == "user":
            raise Error("bad_request", 'Role "user" can not own media.')

        if not media_ids:
            return

        # check duplicate name
        with cls._rdb_context():
            media_data = list(
                r.table("media")
                .get_all(r.args(media_ids))
                .pluck("id", "name", "category")
                .run(cls._rdb_connection)
            )
        if not media_data:
            return
        cls.update_duplicated_names(
            "media",
            media_data,
            user=user_data["new_user"]["user"],
        )

        # check media quota
        if Quotas.get_user_migration_check_quota_config():
            Quotas.media_create(user_data["new_user"]["user"], quantity=len(media_ids))

        ## if new owner is from another category, delete
        # permissions of groups and users of old category
        if user_data["new_user"]["category"] is not media_data[0]["category"]:
            user_data["new_user"]["allowed"] = {
                "categories": False,
                "groups": False,
                "users": False,
            }

        # change owner
        for i in range(0, len(media_ids), 100):
            batch_media_ids = media_ids[i : i + 100]
            with cls._rdb_context():
                r.table("media").get_all(r.args(batch_media_ids)).update(
                    user_data["new_user"]
                ).run(cls._rdb_connection)

    @classmethod
    def change_owner_deployments(cls, deployments_ids, user_data, old_user_id):
        # TODO: change allowed to false if the target user is on a different category
        with cls._rdb_context():
            deployments_data = list(
                r.table("deployments")
                .get_all(r.args(deployments_ids))
                .pluck("id", "name")
                .run(cls._rdb_connection)
            )
        cls.update_duplicated_names(
            "deployments",
            deployments_data,
            user=user_data["new_user"]["user"],
        )
        if deployments_ids:
            # check if the new owner is role user
            if user_data["payload"]["role_id"] == "user":
                raise Error("bad_request", 'Role "user" can not own deployments.')

            # check deployment create quota, ignore number of users in the deployment
            if Quotas.get_user_migration_check_quota_config():
                Quotas.deployment_create(
                    user_data["new_user"]["user"],
                    quantity=len(deployments_ids),
                    desktops_len=None,
                    users=None,
                )
            with cls._rdb_context():
                # for each deployment old_user_id is in co_owners, remove old_user_id from co_owners
                r.table("deployments").get_all(old_user_id, index="co_owners").update(
                    {"co_owners": r.row["co_owners"].difference([old_user_id])}
                ).run(cls._rdb_connection)

            # change owner
            for i in range(0, len(deployments_ids), 100):
                batch_deployments_ids = deployments_ids[i : i + 100]
                with cls._rdb_context():
                    r.table("deployments").get_all(
                        r.args(batch_deployments_ids)
                    ).update(
                        {
                            "user": user_data["new_user"]["user"],
                            "co_owners": r.literal([]),
                        }
                    ).run(
                        cls._rdb_connection
                    )

    @classmethod
    def change_storage_ownership(cls, domain_data, user_id):
        storage_ids = []
        for disk in domain_data["create_dict"]["hardware"]["disks"]:
            if disk.get("storage_id"):
                storage_ids.append(disk["storage_id"])
        with cls._rdb_context():
            r.table("storage").get_all(*storage_ids).update({"user_id": user_id}).run(
                cls._rdb_connection
            )
        with cls._rdb_context():
            r.table("domains").get(domain_data["id"]).update(
                {"create_dict": domain_data["create_dict"]}
            ).run(cls._rdb_connection)

    @classmethod
    def check_user_duplicated_domain_name(
        cls, name, user_id, kind="desktop", item_id=None
    ):
        """_From /api/libv2/validators.py check_user_duplicated_domain_name()"""
        with cls._rdb_context():
            user_domains_with_name = (
                r.table("domains")
                .get_all([kind, user_id], index="kind_user")
                .filter(
                    lambda item: (item["name"] == name.strip())
                    & (item["id"] != item_id)
                )
                .count()
                .run(cls._rdb_connection)
            )
        if user_domains_with_name > 0:
            user_name = Caches.get_document("users", user_id, ["name"])
            raise Error(
                "conflict",
                "User " + user_name + " already has " + kind + " with name " + name,
                traceback.format_exc(),
                description_code=(
                    "new_desktop_name_exists"
                    if kind == "desktop"
                    else "new_template_name_exists"
                ),
            )

    @classmethod
    def owns_domain_id(cls, payload, domain_id):
        try:

            # User is admin
            if payload.get("role_id", "") == "admin":
                return True

            domain = Caches.get_document("domains", domain_id)

            if not domain:
                # Will be caught by the except and raise a generic error
                raise Error(
                    "not_found",
                    "Desktop not found",
                    traceback.format_exc(),
                    "not_found",
                )

            # User is owner
            if domain["user"] == payload["user_id"]:
                return True

            # User is advanced and the desktop is from one of its deployments
            if payload.get("role_id", "") == "advanced" and domain["tag"]:
                cls.owns_deployment_id(payload, domain["tag"])
                return True

            # User is manager and the desktop is from its categories
            if payload["role_id"] == "manager":
                if payload.get("category_id", "") == domain["category"]:
                    return True

            # Templates shared with this user via the alloweds mechanism.
            # The new-desktop form calls /item/desktop/{id}/get-info for
            # templates too (the URL says "desktop" but the same handler
            # serves both kinds), and a non-owner user must be able to
            # read the template they were granted access to in order to
            # build a desktop from it.
            if domain.get("kind") == "template" and Alloweds.is_allowed(
                payload, domain, "domains"
            ):
                return True

        except Error:
            pass

        raise Error(
            "forbidden",
            "Not enough access rights to access this domain_id " + str(domain_id),
            traceback.format_exc(),
            description_code="not_enough_rights_desktop",
        )

    @classmethod
    def owns_deployment_id(cls, payload, deployment_id, check_co_owner=True):
        try:

            # User is admin
            if payload.get("role_id", "") == "admin":
                return True

            deployment = Caches.get_document("deployments", deployment_id)

            if not deployment:
                # Will be caught by the except and raise a generic error
                raise Error(
                    "not_found",
                    "Deployment not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )

            if not check_co_owner:
                if deployment["user"] == payload["user_id"]:
                    return True
            else:
                if (
                    deployment["user"] == payload["user_id"]
                    or payload["user_id"] in deployment["co_owners"]
                ):
                    return True

            if payload.get("role_id", "") == "manager":
                deployment_user = Caches.get_document("users", deployment["user"])
                deployment_category = deployment_user["category"]

                if deployment_category == payload.get("category_id", ""):
                    return True

        except Error:
            pass

        raise Error(
            "forbidden",
            "Not enough access rights to access this deployment_id "
            + str(deployment_id),
            traceback.format_exc(),
            description_code="not_enough_rights_deployment" + str(deployment_id),
        )

    @classmethod
    def owns_deployment_desktop_id(cls, payload, desktop_id, check_co_owners=True):
        desktop = Caches.get_document("domains", desktop_id)
        if desktop is None:
            raise Error(
                "not_found",
                f"Desktop {desktop_id} not found",
                traceback.format_exc(),
                "not_found",
            )

        if payload.get("role_id", "user") != "user" and desktop.get("tag"):
            try:
                cls.owns_deployment_id(
                    payload, desktop["tag"], check_co_owners=check_co_owners
                )
            except Exception:
                return False
            return True
        return False

    @classmethod
    def owns_media_id(cls, payload, media_id):
        """
        Get the media_id from route path and return it if the user has access to it.
        """
        try:

            # User is admin
            if payload.get("role_id", "") == "admin":
                return media_id

            media = Caches.get_document("media", media_id, ["user", "category"])

            if media is None:
                raise Error(
                    "not_found",
                    f"Media {media_id} not found",
                    traceback.format_exc(),
                    "not_found",
                )

            # User is owner
            if media["user"] == payload["user_id"]:
                return media_id

            # User is manager and the media is from its categories
            if payload["role_id"] == "manager":
                if payload.get("category_id", "") == media["category"]:
                    return media_id

        except Error:
            pass

        raise Error(
            "forbidden",
            "Not enough access rights to access this media_id " + str(media_id),
            traceback.format_exc(),
            description_code="not_enough_rights_media" + str(media_id),
        )

    @classmethod
    def owns_booking_id(cls, payload, booking_id):
        """Return ``booking_id`` if the caller owns it, else 403/404.

        Mirrors v3 ``api/views/decorators.py::ownsBookingId``:
        - admins always pass
        - the booking owner (``bookings.user_id == payload.user_id``)
          passes
        - a manager whose ``category_id`` matches the booking owner's
          category passes
        """
        if payload.get("role_id", "") == "admin":
            return booking_id

        booking_user_id = Caches.get_document("bookings", booking_id, ["user_id"])
        if booking_user_id is None:
            raise Error(
                "not_found",
                f"Booking {booking_id} not found",
                traceback.format_exc(),
                description_code="not_found",
            )

        if booking_user_id == payload["user_id"]:
            return booking_id

        if payload.get("role_id", "") == "manager":
            booking_user = Caches.get_document("users", booking_user_id, ["category"])
            if booking_user is None:
                raise Error(
                    "not_found",
                    f"Booking user {booking_user_id} not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
            if booking_user.get("category") == payload.get("category_id"):
                return booking_id

        raise Error(
            "forbidden",
            f"Not enough access rights to access this booking_id {booking_id}",
            traceback.format_exc(),
            description_code="not_enough_rights_booking",
        )

    @classmethod
    def get_user_data(cls, user_id="admin"):
        if user_id == "admin":
            with cls._rdb_context():
                user = (
                    r.table("users")
                    .get("local-default-admin-admin")
                    .pluck("id", "username", "category", "group")
                    .run(cls._rdb_connection)
                )
        else:
            with cls._rdb_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "username", "category", "group")
                    .run(cls._rdb_connection)
                )
        return {
            "category": user["category"],
            "group": user["group"],
            "user": user["id"],
            "username": user["username"],
        }

    @classmethod
    def generate_db_media(cls, path_downloaded, filesize):
        media_id = str(uuid.uuid4())
        admin_data = cls.get_user_data()

        icon = False
        if path_downloaded.split(".")[-1] == "iso":
            icon = "fa-circle-o"
            kind = "iso"
        if path_downloaded.split(".")[-1] == "fd":
            icon = "fa-floppy-o"
            kind = "floppy"
        if path_downloaded.split(".")[-1].startswith("qcow"):
            icon = "fa-hdd-o"
            kind = path_downloaded.split(".")[-1]
        if not icon:
            raise Error(
                "precondition_required",
                "Skipping uploaded file as has unknown extension",
                traceback.format_exc(),
                description_code="unknown_extension",
            )

        with cls._rdb_context():
            # TODO(move-api-hypervisors-to-common): This will always fail
            username = (
                r.table("users").get(parts[-2])["username"].run(cls._rdb_connection)
            )
        if username == None:
            raise Error(
                "not_found",
                "Username not found",
                traceback.format_exc(),
                description_code="not_found",
            )

        return {
            "accessed": int(time.time()),
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
            "category": admin_data["category"],
            "description": "Scanned from storage.",
            "detail": "",
            "group": admin_data["group"],
            "hypervisors_pools": ["default"],
            "icon": icon,
            "id": media_id,
            "kind": kind,
            "name": path_downloaded.split("/")[-1],
            "path": "/".join(
                path_downloaded.rsplit("/", 6)[2:]
            ),  # "default/default/local/admin-admin/dsl-4.4.10.iso" ,
            "path_downloaded": path_downloaded,
            "progress": {
                "received": filesize,
                "received_percent": 100,
                "speed_current": "10M",
                "speed_download_average": "10M",
                "speed_upload_average": "0",
                "time_left": "--:--:--",
                "time_spent": "0:00:05",
                "time_total": "0:00:05",
                "total": filesize,
                "total_percent": 100,
                "xferd": "0",
                "xferd_percent": "0",
            },
            "status": "Downloaded",
            "url-isard": False,
            "url-web": False,
            "user": admin_data["user"],  # "local-default-admin-admin" ,
            "username": admin_data["username"],
        }

    @classmethod
    def check_task_priority(cls, payload, priority):
        """_From api/views/StorageView check_task_priority(payload, priority)_

        Check and normalize the task priority value.

        :param payload: The user payload
        :type payload: dict
        :param priority: The priority value to check
        :type priority: str
        :return: The normalized priority value
        :rtype: str

        """
        if payload.get("role_id", "") != "admin":
            priority = "low"
        else:
            if priority not in ["low", "default", "high"]:
                raise Error(
                    error="bad_request",
                    description=f"Priority must be low, default or high",
                )
        return priority

    @classmethod
    def check_task_retry(cls, payload, retry):
        """_From api/views/StorageView check_task_retry(payload, retry)_
        Check and normalize the task retry value.

        :param payload: The user payload
        :type payload: dict
        :param retry: The retry value to check
        :type retry: int or None
        :return: The normalized retry value
        :rtype: int or None

        """
        if payload["role_id"] != "admin" or retry is None:
            retry = 0
        else:
            if not isinstance(retry, int):
                try:
                    retry = int(retry)
                except ValueError:
                    raise Error(
                        error="bad_request",
                        description="Retry should be an integer between 0 and 5",
                    )
            if retry < 0 or retry > 5:
                raise Error(
                    error="bad_request",
                    description="Retry should be an integer between 0 and 5",
                )
        return retry
