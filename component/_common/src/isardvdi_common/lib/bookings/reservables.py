#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import traceback
from typing import Literal
from uuid import uuid4

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from pydantic import BaseModel, Field
from rethinkdb import r


class GPUsModel(BaseModel):
    """From api/schemas/gpus.yml"""

    id: str = str(uuid4())
    name: str = Field(max_length=50)
    memory: str
    model: str
    description: str = Field(max_length=255, default="")
    brand: str
    reservable_type: Literal["gpus", "usbs"]


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

    def deassign_deployments_with_gpu(self, item_type, item_id, deployments=None):
        return self.reservable[item_type].deassign_deployments_with_gpu(
            item_id, deployments
        )

    def check_last_subitem(self, item_type, item_id):
        return self.reservable[item_type].check_last_subitem(item_id)

    def check_desktops_with_profile(self, item_type, item_id):
        return self.reservable[item_type].check_desktops_with_profile(item_id)

    def check_deployments_with_profile(self, item_type, item_id):
        return self.reservable[item_type].check_deployments_with_profile(item_id)

    def delete_bookings(self, item_type, item_id, data):
        return self.reservable[item_type].delete_bookings(item_id, data)

    def get_plans_bookings(self, item_type, item_id):
        return self.reservable[item_type].get_plans_bookings(item_id)


class ResourceItemsGpus(RethinkSharedConnection):

    @classmethod
    def list_items(cls):
        query = r.table("gpus").merge(
            lambda gpu: r.branch(
                gpu["physical_device"].eq(None),
                {"active_profile": None, "changing_to_profile": None},
                r.table("vgpus")
                .get(gpu["physical_device"])
                .pluck("vgpu_profile", "changing_to_profile")
                .do(
                    lambda vgpu: {
                        "active_profile": vgpu["vgpu_profile"],
                        "changing_to_profile": vgpu["changing_to_profile"],
                        "desktops_started": r.table("vgpus")
                        .filter(lambda row: row["id"] == gpu["physical_device"])
                        .concat_map(lambda row: row["mdevs"].values())
                        .concat_map(lambda mdev_group: mdev_group.values())
                        .filter(lambda mdev: mdev["domain_started"] != False)
                        .map(lambda mdev: mdev["domain_started"])
                        .default([])
                        .coerce_to("array"),
                    }
                ),
            )
        )
        with cls._rdb_context():
            items = list(query.run(cls._rdb_connection))
        hyp_gpu_warnings = {}
        for item in items:
            if item.get("active_profile"):
                with cls._rdb_context():
                    available_units = list(
                        r.table("gpu_profiles")
                        .get_all(
                            [item["brand"], item["model"]],
                            index="brand-model",
                        )
                        .concat_map(lambda doc: doc["profiles"])
                        .filter(lambda p: p["profile"] == item["active_profile"])
                        .run(cls._rdb_connection)
                    )[0]
                item["available_units"] = available_units["units"]
                item["active_profile"] = cls.get_subitem(
                    item["id"], available_units["id"]
                )["profile"]
            # Attach gpu_warnings for this GPU's hypervisor
            phys = item.get("physical_device") or ""
            # physical_device format: "hyper_id-pci_XXXX_XX_XX_X"
            parts = phys.rsplit("-pci_", 1)
            hyp_id = parts[0] if len(parts) == 2 else None
            pci_bdf = parts[1].replace("_", ":", 2) if len(parts) == 2 else ""
            if pci_bdf:
                pci_bdf = pci_bdf[: len(pci_bdf) - 2] + "." + pci_bdf[-1]
            if hyp_id and hyp_id not in hyp_gpu_warnings:
                try:
                    with cls._rdb_context():
                        hyp_data = (
                            r.table("hypervisors")
                            .get(hyp_id)
                            .pluck("gpu_warnings")
                            .default({})
                            .run(cls._rdb_connection)
                        )
                    hyp_gpu_warnings[hyp_id] = hyp_data.get("gpu_warnings", [])
                except Exception:
                    hyp_gpu_warnings[hyp_id] = []
            # Filter warnings relevant to this specific GPU's PCI address
            all_warnings = hyp_gpu_warnings.get(hyp_id, [])
            item["gpu_warnings"] = (
                ([w for w in all_warnings if pci_bdf and pci_bdf in w] or all_warnings)
                if all_warnings
                else []
            )
        return list(items)

    @classmethod
    def add_item(cls, data):
        with cls._rdb_context():
            gpu_profile = (
                r.table("gpu_profiles").get(data["bookable"]).run(cls._rdb_connection)
            )
        if not gpu_profile:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        new_gpu = {
            "architecture": gpu_profile["architecture"],
            "brand": gpu_profile["brand"],
            "description": (
                data["description"]
                if data["description"]
                else gpu_profile["description"]
            ),
            "memory": gpu_profile["memory"],
            "model": gpu_profile["model"],
            "name": data["name"],
            "profiles_enabled": [],
            "physical_device": None,
        }
        GPUsModel(**new_gpu)

        with cls._rdb_context():
            if not Helpers._check(
                r.table("gpus")
                .insert(new_gpu, conflict="update")
                .run(cls._rdb_connection),
                "inserted",
            ):
                raise Error(
                    "internal_server",
                    "Unable to insert bookable in database.",
                    description_code="unable_to_insert",
                )

        return new_gpu

    @classmethod
    def list_profiles(cls):
        with cls._rdb_context():
            return list(r.table("gpu_profiles").run(cls._rdb_connection))

    @classmethod
    def enable_subitem(cls, item_id, subitem_id, enabled):
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
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
        with cls._rdb_context():
            if not Helpers._check(
                r.table("gpus")
                .get(item_id)
                .update({"profiles_enabled": enabled_profiles})
                .run(cls._rdb_connection),
                "replaced",
            ):
                raise Error(
                    "internal_server",
                    "Unable to update bookable in database.",
                    description_code="unable_to_update_bookable",
                )
        with cls._rdb_context():
            gpus_enabled_subitem = list(
                r.table("gpus")
                .filter(lambda gpu: gpu["profiles_enabled"].contains(subitem_id))
                .run(cls._rdb_connection)
            )
        if enabled:
            cls.add_reservable_vgpu(item_id, subitem_id)
        # if it's the last profile of this kind, delete it
        elif len(gpus_enabled_subitem) == 0:
            cls.delete_reservable_vgpu(subitem_id)
        return item

    @classmethod
    def add_reservable_vgpu(cls, item_id, subitem_id):
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        subitem = cls.get_subitem(item_id, subitem_id)
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
        with cls._rdb_context():
            replaced = Helpers._check(
                r.table("reservables_vgpus")
                .insert(new_reservable_vgpu, conflict="update")
                .run(cls._rdb_connection),
                "replaced",
            )
        if not replaced:
            raise Error(
                "internal_server",
                "Unable to update bookable in database.",
                description_code="unable_to_update_bookable",
            )
        else:
            with cls._rdb_context():
                total_profiles = (
                    r.table("gpus")
                    .filter(
                        lambda profiles: profiles["profiles_enabled"].contains(
                            new_reservable_vgpu["id"]
                        )
                    )
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                units_profile = list(
                    r.table("reservables_vgpus")
                    .filter(lambda id: id["id"].eq(new_reservable_vgpu["id"]))["units"]
                    .run(cls._rdb_connection)
                )
            total_units = total_profiles * units_profile[0]

            with cls._rdb_context():
                r.table("reservables_vgpus").filter(
                    {"id": new_reservable_vgpu["id"]}
                ).update({"total_units": total_units}).run(cls._rdb_connection)

    @classmethod
    def delete_reservable_vgpu(cls, subitem_id):
        with cls._rdb_context():
            if r.table("reservables_vgpus").get(subitem_id).run(cls._rdb_connection):
                if not Helpers._check(
                    r.table("reservables_vgpus")
                    .get(subitem_id)
                    .delete()
                    .run(cls._rdb_connection),
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

    @classmethod
    def list_subitems(cls, item_id):
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        try:
            with cls._rdb_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(cls._rdb_connection)
                )[0]["profiles"]
        except (IndexError, KeyError):
            raise Error("not_found", "Gpu id not found in gpu definitions table")
        return subitems

    @classmethod
    def list_subitems_enabled(cls, item_id):
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table: " + str(item_id),
                description_code="not_found",
            )
        try:
            with cls._rdb_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(cls._rdb_connection)
                )[0]["profiles"]
        except (IndexError, KeyError):
            raise Error(
                "not_found",
                "Gpu id not found in gpu definitions table",
                description_code="not_found",
            )
        return [
            subitem for subitem in subitems if subitem["id"] in item["profiles_enabled"]
        ]

    @classmethod
    def get_subitem(cls, item_id, subitem_id):
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error("not_found", "Gpu id " + item_id + " not found in gpu table")
        try:
            with cls._rdb_context():
                subitems = list(
                    r.table("gpu_profiles")
                    .get_all(
                        [item["brand"], item["model"]],
                        index="brand-model",
                    )
                    .run(cls._rdb_connection)
                )[0].get("profiles")
            subitem = [s for s in subitems if s.get("id") == subitem_id][0]
        except (IndexError, KeyError, TypeError):
            log.debug(traceback.format_exc())
            raise Error(
                "not_found", "Gpu id " + item_id + " not found in gpu definitions table"
            )
        return subitem

    @classmethod
    def check_last_subitem(cls, subitem_id):
        last = 0
        with cls._rdb_context():
            all_profiles_enabled = r.table("gpus")["profiles_enabled"].run(
                cls._rdb_connection
            )
        for profiles in all_profiles_enabled:
            for pf in profiles:
                if subitem_id == pf:
                    last += 1
                if last > 1:
                    return False
        return True

    @classmethod
    def check_desktops_with_profile(cls, subitem_id):
        with cls._rdb_context():
            desktops = list(
                r.table("domains")
                .get_all(subitem_id, index="vgpus")
                .eq_join("user", r.table("users"))
                .pluck(
                    {
                        "left": {
                            "name": True,
                            "username": True,
                            "kind": True,
                            "id": True,
                            "user": True,
                        },
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
                        "name": doc["left"]["name"],
                        "username": doc["left"]["username"],
                        "kind": doc["left"]["kind"],
                        "user": doc["left"]["user"],
                        "category": r.table("categories").get(doc["right"]["category"])[
                            "name"
                        ],
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
        return desktops

    @classmethod
    def check_deployments_with_profile(cls, subitem_id):
        with cls._rdb_context():
            deployments = list(
                r.table("deployments")
                .get_all(subitem_id, index="vgpus")
                .pluck("id", "user", "name")
                .map(
                    lambda doc: {
                        "id": doc["id"],
                        "user": doc["user"],
                        "username": r.table("users").get(doc["user"])["username"],
                        "name": doc["name"],
                    }
                )
                .run(cls._rdb_connection)
            )
        return deployments

    @classmethod
    def deassign_desktops_with_gpu(cls, item_id, desktops):
        query = r.table("domains")
        if desktops is None:
            query = query.get_all(item_id, index="vgpus")
        else:
            query = query.get_all(r.args(desktops))

        with cls._rdb_context():
            query.filter(
                (r.row.has_fields({"create_dict": {"reservables": {"vgpus": True}}}))
            ).update(
                {
                    "create_dict": {
                        "reservables": {"vgpus": None},
                        "hardware": {
                            "videos": ["default"],
                        },
                    }
                }
            ).run(
                cls._rdb_connection
            )
        return desktops

    @classmethod
    def deassign_deployments_with_gpu(cls, item_id, deployments=None):
        deployments_batch_size = 100
        for i in range(0, len(deployments), deployments_batch_size):
            batch_deployments = deployments[i : i + deployments_batch_size]
            with cls._rdb_context():
                r.table("deployments").get_all(r.args(batch_deployments)).update(
                    lambda deployment: {
                        "create_dict": deployment["create_dict"].map(
                            lambda create_item: create_item.merge(
                                {
                                    "reservables": create_item["reservables"].merge(
                                        {
                                            "vgpus": r.branch(
                                                create_item["reservables"]["vgpus"]
                                                .difference([item_id])
                                                .is_empty(),
                                                None,
                                                create_item["reservables"][
                                                    "vgpus"
                                                ].difference([item_id]),
                                            )
                                        }
                                    )
                                }
                            )
                        )
                    }
                ).run(cls._rdb_connection)

    @classmethod
    def get_subitem_parent_item(cls, subitem):
        parts = subitem.split("-")
        return {"brand": parts[0], "model": parts[1], "profile": parts[1]}

    @classmethod
    def get_subitem_units(cls, item_id, subitem):
        return cls.get_subitem(item_id, subitem)["units"]

    @classmethod
    def get_default_subitem(cls, item_id):
        ## TODO: Get from gpu table item_id
        return "1Q"

    @classmethod
    def set_subitem(cls, item_id, subitem_id):
        None

    @classmethod
    def planning_item_can_overlap(cls, item_id):
        return False

    @classmethod
    def planning_subitem_can_overlap(cls, item_id, subitem_id):
        return True

    @classmethod
    def planning_subitem_join_before(cls, item_id, subitem_id):
        return True

    @classmethod
    def planning_subitem_join_after(cls, item_id, subitem_id):
        return True

    @classmethod
    def planning_schedule_subitem(cls, item_id, subitem_id):
        return True

    @classmethod
    def add_item_cascade_actions(cls, item_id):
        None

    @classmethod
    def add_subitem_cascade_actions(cls, subitem_id):
        None


class ResourceItemsUsbs(RethinkSharedConnection):

    @classmethod
    def list_items(cls):
        with cls._rdb_context():
            return list(r.table("usbs").run(cls._rdb_connection))

    @classmethod
    def list_subitems(cls, item_id):
        with cls._rdb_context():
            item = r.table("usbs").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with cls._rdb_context():
                subitems = list(
                    r.table("usb_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(cls._rdb_connection)
                )[0]["profiles"]
        except (IndexError, KeyError):
            raise Error(
                "not_found",
                "Usb id not found in usb definitions table",
                description_code="not_found",
            )
        return subitems

    @classmethod
    def list_subitems_enabled(cls, item_id):
        with cls._rdb_context():
            item = r.table("usbs").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with cls._rdb_context():
                subitems = list(
                    r.table("usb_profiles")
                    .get_all([item["brand"], item["model"]], index="brand-model")
                    .run(cls._rdb_connection)
                )[0]["profiles"]
        except (IndexError, KeyError):
            raise Error("not_found", "Usb id not found in usb definitions table")
        return [
            subitem for subitem in subitems if subitem["id"] in item["profiles_enabled"]
        ]

    @classmethod
    def get_subitem(cls, item_id, subitem_id):
        with cls._rdb_context():
            item = r.table("usbs").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Usb id not found in usb table",
                description_code="not_found",
            )
        try:
            with cls._rdb_context():
                subitem = list(
                    r.table("usb_profiles")
                    .get_all(
                        [item["brand"], item["model"], subitem_id],
                        index="brand-model",
                    )
                    .run(cls._rdb_connection)
                )[0]["profiles"]
            subitem = [s for s in subitems if s["id"] == subitem_id][0]
        except (IndexError, KeyError, NameError):
            raise Error("not_found", "Usb id not found in usb definitions table")
        return subitem

    @classmethod
    def get_subitem_parent_item(cls, subitem):
        parts = subitem.split("-")
        return {"brand": parts[0], "model": parts[1], "profile": parts[1]}

    @classmethod
    def get_subitem_units(cls, item_id, subitem):
        return cls.get_subitem(item_id, subitem)["units"]

    @classmethod
    def get_default_subitem(cls, item_id):
        ## TODO: Get from gpu table item_id
        return "1Q"

    @classmethod
    def set_subitem(cls, item_id, subitem_id):
        None

    @classmethod
    def planning_item_can_overlap(cls, item_id):
        return True

    @classmethod
    def planning_subitem_can_overlap(cls, item_id, subitem_id):
        return False

    @classmethod
    def planning_subitem_join_before(cls, item_id, subitem_id):
        return True

    @classmethod
    def planning_subitem_join_after(cls, item_id, subitem_id):
        return True

    @classmethod
    def planning_schedule_subitem(cls, item_id, subitem_id):
        return False

    @classmethod
    def add_item_cascade_actions(cls, item_id):
        None

    @classmethod
    def add_subitem_cascade_actions(cls, subitem_id):
        None
