#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from ..flask_rethink import RDB

db = RDB(app)
db.init_app(app)

import traceback

from ..._common.api_exceptions import Error
from ..helpers import _check, _parse_string
from ..validators import _validate_item, _validate_table


class Reservables:
    def __init__(self):
        self.reservable = {}
        self.items = ["gpus"]
        self.reservable["gpus"] = ResourceItemsGpus()
        self.reservable["usbs"] = ResourceItemsUsbs()

    def list_reservables(self):
        return self.items

    def list_items(self, item_type):
        return self.reservable[item_type].list_items()

    def add_item(self, item_type, item):
        return self.reservable[item_type].add_item(item)

    def list_profiles(self, item_type):
        return self.reservable[item_type].list_profiles()

    def enable_subitems(self, item_type, item_id, subitem_id, enabled):
        return self.reservable[item_type].enable_subitem(item_id, subitem_id, enabled)

    def list_subitems(self, item_type, item_id):
        return self.reservable[item_type].list_subitems(item_id)

    def list_subitems_enabled(self, item_type, item_id):
        return self.reservable[item_type].list_subitems_enabled(item_id)

    def get_subitem(self, item_type, item_id, subitem):
        return self.reservable[item_type].get_subitem(item_id, subitem)

    def get_subitem_parent_item(self, item_type, subitem):
        return self.reservable[item_type].get_subitem_parent_item(subitem)

    def get_subitem_units(self, item_type, item_id, subitem):
        return self.reservable[item_type].get_subitem_units(item_id, subitem)

    def planning_item_can_overlap(self, item_type, item_id):
        return self.reservable[item_type].planning_item_can_overlap(item_id)

    def planning_subitem_can_overlap(self, item_type, item_id, subitem):
        return self.reservable[item_type].planning_subitem_can_overlap(item_id, subitem)

    def planning_subitem_join_before(self, item_type, item_id, subitem_id):
        return self.reservable[item_type].planning_subitem_join_before(
            item_id, subitem_id
        )

    def planning_subitem_join_after(self, item_type, item_id, subitem_id):
        return self.reservable[item_type].planning_subitem_join_after(
            item_id, subitem_id
        )

    def planning_schedule_subitem(self, item_type, item_id, subitem_id):
        return self.reservable[item_type].planning_schedule_subitem(item_id, subitem_id)

    def get_default_subitem(self, item_type, item_id):
        return self.reservable[item_type].get_default_subitem(item_id)

    def set_subitem(self, item_type, item_id, subitem):
        return self.reservable[item_type].set_subitem(item_id, subitem)

    def deassign_desktops_with_gpu(self, item_type, item_id, desktops=None):
        return self.reservable[item_type].deassign_desktops_with_gpu(item_id, desktops)

    def check_last_subitem(self, item_type, item_id):
        return self.reservable[item_type].check_last_subitem(item_id)

    def check_desktops_with_profile(self, item_type, item_id):
        return self.reservable[item_type].check_desktops_with_profile(item_id)


class ResourceItemsGpus:
    def list_items(self):
        with app.app_context():
            return list(r.table("gpus").run(db.conn))

    def add_item(self, data):
        with app.app_context():
            gpu_profile = r.table("gpu_profiles").get(data["bookable"]).run(db.conn)
        if not gpu_profile:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        new_gpu = {
            "architecture": gpu_profile["architecture"],
            "brand": gpu_profile["brand"],
            "description": data["description"]
            if data["description"]
            else gpu_profile["description"],
            "memory": gpu_profile["memory"],
            "model": gpu_profile["model"],
            "name": data["name"],
            "profiles_enabled": [],
            "physical_device": None,
        }
        _validate_item("gpus", new_gpu)

        if not _check(
            r.table("gpus").insert(new_gpu, conflict="update").run(db.conn), "inserted"
        ):
            raise Error(
                "internal_server",
                "Unable to insert bookable in database.",
                description_code="unable_to_insert",
            )

        return new_gpu

    def list_profiles(self):
        with app.app_context():
            return list(r.table("gpu_profiles").run(db.conn))

    def enable_subitem(self, item_id, subitem_id, enabled):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        enabled_profiles = item["profiles_enabled"]
        if enabled:
            enabled_profiles.append(subitem_id)
        else:
            enabled_profiles.remove(subitem_id)
        if not _check(
            r.table("gpus")
            .get(item_id)
            .update({"profiles_enabled": enabled_profiles})
            .run(db.conn),
            "replaced",
        ):
            raise Error(
                "internal_server",
                "Unable to update bookable in database.",
                description_code="unable_to_update_bookable",
            )
        gpus_enabled_subitem = list(
            r.table("gpus")
            .filter(lambda gpu: gpu["profiles_enabled"].contains(subitem_id))
            .run(db.conn)
        )
        if enabled:
            self.add_reservable_vgpu(item_id, subitem_id)
        elif len(gpus_enabled_subitem) == 0:
            self.delete_reservable_vgpu(subitem_id)
        return item

    def add_reservable_vgpu(self, item_id, subitem_id):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
            subitem = self.get_subitem(item_id, subitem_id)
            if not subitem:
                raise Error(
                    "not_found",
                    "Gpu profile id not found in gpu_profiles table",
                    description_code="not_found",
                )
            new_reservable_vgpu = {
                "allowed": {
                    "categories": False,
                    "groups": False,
                    "roles": ["admin"],
                    "users": False,
                },
                "brand": item["brand"],
                "description": item["brand"]
                + " vGPU "
                + item["model"]
                + " with profile "
                + subitem["profile"]
                + " with "
                + str(subitem["memory"])
                + " vRAM with maximum "
                + str(subitem["units"])
                + " vGPUs per device",
                "heads": 1,
                "id": item["brand"] + "-" + item["model"] + "-" + subitem["profile"],
                "model": item["model"],
                "name": "GPU "
                + item["brand"]
                + " "
                + item["model"]
                + " "
                + str(subitem["memory"]),
                "profile": subitem["profile"],
                "ram": subitem["memory"],
                "vram": subitem["memory"],
                "units": subitem["units"],
                "priority_id": "default",
            }
            if not _check(
                r.table("reservables_vgpus")
                .insert(new_reservable_vgpu, conflict="update")
                .run(db.conn),
                "replaced",
            ):
                raise Error(
                    "internal_server",
                    "Unable to update bookable in database.",
                    description_code="unable_to_update_bookable",
                )
            else:
                with app.app_context():
                    total_profiles = (
                        r.table("gpus")
                        .filter(
                            lambda profiles: profiles["profiles_enabled"].contains(
                                new_reservable_vgpu["id"]
                            )
                        )
                        .count()
                        .run(db.conn)
                    )
                    units_profile = list(
                        r.table("reservables_vgpus")
                        .filter(lambda id: id["id"].eq(new_reservable_vgpu["id"]))[
                            "units"
                        ]
                        .run(db.conn)
                    )
                    total_units = total_profiles * units_profile[0]

                    r.table("reservables_vgpus").filter(
                        {"id": new_reservable_vgpu["id"]}
                    ).update({"total_units": total_units}).run(db.conn)

    def delete_reservable_vgpu(self, subitem_id):
        with app.app_context():
            if r.table("reservables_vgpus").get(subitem_id).run(db.conn):
                if not _check(
                    r.table("reservables_vgpus").get(subitem_id).delete().run(db.conn),
                    "deleted",
                ):
                    raise Error(
                        "internal_server",
                        "Reservable vgpu id not found in reservables_vgpus table",
                        traceback.format_exc(),
                    )
            else:
                raise Error(
                    "not_found",
                    "Reservable vgpu id not found in reservables_vgpus table",
                )

    def list_subitems(self, item_id):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        try:
            with app.app_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(db.conn)
                )[0]["profiles"]
        except:
            raise Error("not_found", "Gpu id not found in gpu definitions table")
        return subitems

    def list_subitems_enabled(self, item_id):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        try:
            with app.app_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(db.conn)
                )[0]["profiles"]
        except:
            raise Error(
                "not_found",
                "Gpu id not found in gpu definitions table",
                description_code="not_found",
            )
        return [
            subitem for subitem in subitems if subitem["id"] in item["profiles_enabled"]
        ]

    def get_subitem(self, item_id, subitem_id):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error("not_found", "Gpu id " + item_id + " not found in gpu table")
        try:
            with app.app_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all(
                        [item["brand"], item["model"]],
                        index="brand-model",
                    )
                    .run(db.conn)
                )[0]["profiles"]
            subitem = [s for s in subitems if s["id"] == subitem_id][0]
        except:
            log.debug(traceback.format_exc())
            raise Error(
                "not_found", "Gpu id " + item_id + " not found in gpu definitions table"
            )
        return subitem

    def check_last_subitem(self, subitem_id):
        last = 0
        query = r.table("gpus")["profiles_enabled"]
        all_profiles_enabled = query.run(db.conn)
        for profiles in all_profiles_enabled:
            for pf in profiles:
                if subitem_id == pf:
                    last += 1
                if last > 1:
                    return False
        return True

    def check_desktops_with_profile(self, subitem_id):
        query = r.table("domains").filter(
            lambda domain: domain["create_dict"]["reservables"]["vgpus"].contains(
                subitem_id
            )
        )
        with app.app_context():
            desktops = list(query.pluck("name", "username", "kind", "id").run(db.conn))
        return desktops

    def deassign_desktops_with_gpu(self, item_id, desktops=None):
        query = r.table("domains")
        if not desktops:
            query = query.filter(
                lambda domain: domain["create_dict"]["reservables"]["vgpus"].contains(
                    item_id
                )
            )
        else:
            query = query.get_all(r.args(desktops))

        if not _check(
            query.update({"create_dict": {"reservables": {"vgpus": []}}}).run(db.conn),
            "replaced",
        ):
            raise Error(
                "internal_server",
                "Internal server error ",
                traceback.format_exc(),
            )
        return desktops

    def get_subitem_parent_item(self, subitem):
        parts = subitem.split("-")
        return {"brand": parts[0], "model": parts[1], "profile": parts[1]}

    def get_subitem_units(self, item_id, subitem):
        return self.get_subitem(item_id, subitem)["units"]

    def get_default_subitem(self, item_id):
        ## TODO: Get from gpu table item_id
        return "1Q"

    def set_subitem(self, item_id, subitem_id):
        None

    def planning_item_can_overlap(self, item_id):
        return False

    def planning_subitem_can_overlap(self, item_id, subitem_id):
        return True

    def planning_subitem_join_before(self, item_id, subitem_id):
        return True

    def planning_subitem_join_after(self, item_id, subitem_id):
        return True

    def planning_schedule_subitem(self, item_id, subitem_id):
        return True

    def add_item_cascade_actions(self, item_id):
        None

    def delete_item_cascade_actions(self, item_id):
        None

    def add_subitem_cascade_actions(self, subitem_id):
        None

    def delete_subitemcascade_actions(self, subitem_id):
        None


class ResourceItemsUsbs:
    def list_items(self):
        with app.app_context():
            return list(r.table("usbs").run(db.conn))

    def list_subitems(self, item_id):
        with app.app_context():
            item = r.table("usbs").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with app.app_context():
                subitems = list(
                    r.table("usb_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(db.conn)
                )[0]["profiles"]
        except:
            raise Error(
                "not_found",
                "Usb id not found in usb definitions table",
                description_code="not_found",
            )
        return subitems

    def list_subitems_enabled(self, item_id):
        with app.app_context():
            item = r.table("usbs").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with app.app_context():
                subitems = list(
                    r.table("usb_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(db.conn)
                )[0]["profiles"]
        except:
            raise Error("not_found", "Usb id not found in usb definitions table")
        return [
            subitem for subitem in subitems if subitem["id"] in item["profiles_enabled"]
        ]

    def get_subitem(self, item_id, subitem_id):
        with app.app_context():
            item = r.table("usbs").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with app.app_context():
                subitem = list(
                    r.table("usb_profiles")
                    .get_all(
                        [item["brand"], item["model"], subitem_id],
                        index="brand-model",
                    )
                    .run(db.conn)
                )[0]["profiles"]
            subitem = [s for s in subitems if s["id"] == subitem_id][0]
        except:
            raise Error("not_found", "Usb id not found in usb definitions table")
        return subitem

    def get_subitem_parent_item(self, subitem):
        parts = subitem.split("-")
        return {"brand": parts[0], "model": parts[1], "profile": parts[1]}

    def get_subitem_units(self, item_id, subitem):
        return self.get_subitem(item_id, subitem)["units"]

    def get_default_subitem(self, item_id):
        ## TODO: Get from gpu table item_id
        return "1Q"

    def set_subitem(self, item_id, subitem_id):
        None

    def planning_item_can_overlap(self, item_id):
        return True

    def planning_subitem_can_overlap(self, item_id, subitem_id):
        return False

    def planning_subitem_join_before(self, item_id, subitem_id):
        return True

    def planning_subitem_join_after(self, item_id, subitem_id):
        return True

    def planning_schedule_subitem(self, item_id, subitem_id):
        return False

    def add_item_cascade_actions(self, item_id):
        None

    def delete_item_cascade_actions(self, item_id):
        None

    def add_subitem_cascade_actions(self, subitem_id):
        None

    def delete_subitemcascade_actions(self, subitem_id):
        None
