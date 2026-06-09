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

import re as _re
import traceback

from isardvdi_common.api_exceptions import Error

from ..gpu_realizability import split_qualifier
from ..helpers import _check
from ..validators import _validate_item

# An optional admin "~<variant>" qualifier differentiates otherwise-identical
# brand-model-profile cards into distinct selectable reservables. Restricted to
# lowercase alphanumerics so it can never collide with the id/suffix parsing
# (which keys on "-" and the reserved "~" delimiter, and where ".","_","+" already
# occur inside MIG suffixes).
_VARIANT_RE = _re.compile(r"^[a-z0-9]{1,20}$")


def get_vgpus_hypervisors():
    """Map each bookable vGPU reservable id to the hypervisors that can host it.

    A profile is hostable on a hypervisor when that hypervisor has a physical
    card with the profile enabled (``gpus.profiles_enabled``). The hypervisor id
    is the card id prefix (``<hyp_id>-pci_<bdf>``). Returns ``{reservable_id:
    sorted([hyp_id, ...])}`` — used to keep a multi-profile desktop's profiles on
    a single hypervisor (a guest runs on one host).
    """
    with app.app_context():
        cards = list(
            r.table("gpus").pluck("physical_device", "profiles_enabled").run(db.conn)
        )
    hyp_by_profile = {}
    for card in cards:
        physical_device = card.get("physical_device") or ""
        hyp_id = (
            physical_device.rsplit("-pci_", 1)[0]
            if "-pci_" in physical_device
            else physical_device
        )
        if not hyp_id:
            continue
        for profile_id in card.get("profiles_enabled") or []:
            hyp_by_profile.setdefault(profile_id, set()).add(hyp_id)
    return {profile_id: sorted(hyps) for profile_id, hyps in hyp_by_profile.items()}


def attach_vgpu_hypervisor_groups(vgpus, show_names):
    """Tag each vGPU profile with the hypervisor groups that can host it.

    A multi-profile desktop must keep all its profiles on one hypervisor, so the
    UI needs to know which profiles share a host. Always attach
    ``hypervisor_groups`` (anonymized stable indices — two profiles are
    co-selectable iff their lists intersect). When ``show_names`` (admin/webapp)
    also attach the real ``hypervisors`` names for grouped labels. Tolerates
    items missing an ``id`` and a non-list input.
    """
    if not isinstance(vgpus, list):
        return vgpus
    hyp_map = get_vgpus_hypervisors()
    ordered_hyps = sorted({h for v in vgpus for h in hyp_map.get(v.get("id"), [])})
    anon_index = {h: i + 1 for i, h in enumerate(ordered_hyps)}
    for v in vgpus:
        hyps = hyp_map.get(v.get("id"), [])
        v["hypervisor_groups"] = [anon_index[h] for h in hyps]
        if show_names:
            v["hypervisors"] = hyps
    return vgpus


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

    def recompute_reservable_total_units(self, item_type, subitem_id):
        return self.reservable[item_type].recompute_total_units(subitem_id)

    def list_subitems(self, item_type, item_id):
        return self.reservable[item_type].list_subitems(item_id)

    def list_subitems_enabled(self, item_type, item_id):
        return self.reservable[item_type].list_subitems_enabled(item_id)

    def update_item(self, item_type, item_id, data):
        return self.reservable[item_type].update_item(item_id, data)

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


class ResourceItemsGpus:
    def list_items(self):
        query = r.table("gpus").merge(
            lambda gpu: r.branch(
                gpu["physical_device"].eq(None),
                {"active_profile": None, "changing_to_profile": None},
                r.table("vgpus")
                .get(gpu["physical_device"])
                .default({})
                .do(
                    lambda vgpu: {
                        "active_profile": vgpu["vgpu_profile"].default(None),
                        "changing_to_profile": vgpu["changing_to_profile"].default(
                            None
                        ),
                        "desktops_started": r.table("vgpus")
                        .filter(lambda row: row["id"] == gpu["physical_device"])
                        .concat_map(lambda row: row["mdevs"].default({}).values())
                        .concat_map(lambda mdev_group: mdev_group.values())
                        .filter(lambda mdev: mdev["domain_started"] != False)
                        .map(lambda mdev: mdev["domain_started"])
                        .default([])
                        .coerce_to("array"),
                    }
                ),
            )
        )
        with app.app_context():
            items = list(query.run(db.conn))
        # Cache gpu_warnings / gpu_notes per hypervisor to avoid repeated queries
        hyp_gpu_warnings = {}
        hyp_gpu_notes = {}
        for item in items:
            if item.get("active_profile"):
                with app.app_context():
                    available_units = list(
                        r.table("gpu_profiles")
                        .get_all(
                            [item["brand"], item["model"]],
                            index="brand-model",
                        )
                        .concat_map(lambda doc: doc["profiles"])
                        .filter(lambda p: p["profile"] == item["active_profile"])
                        .run(db.conn)
                    )[0]
                item["available_units"] = available_units["units"]
                item["active_profile"] = self.get_subitem(
                    item["id"], available_units["id"]
                )["profile"]
            # Attach gpu_warnings / gpu_notes for this GPU's hypervisor
            phys = item.get("physical_device") or ""
            # physical_device format: "hyper_id-pci_XXXX_XX_XX_X"
            parts = phys.rsplit("-pci_", 1)
            hyp_id = parts[0] if len(parts) == 2 else None
            pci_bdf = parts[1].replace("_", ":", 2) if len(parts) == 2 else ""
            if pci_bdf:
                pci_bdf = pci_bdf[: len(pci_bdf) - 2] + "." + pci_bdf[-1]
            if hyp_id and hyp_id not in hyp_gpu_warnings:
                try:
                    with app.app_context():
                        hyp_data = (
                            r.table("hypervisors")
                            .get(hyp_id)
                            .pluck("gpu_warnings", "gpu_notes")
                            .default({})
                            .run(db.conn)
                        )
                    hyp_gpu_warnings[hyp_id] = hyp_data.get("gpu_warnings", [])
                    hyp_gpu_notes[hyp_id] = hyp_data.get("gpu_notes", [])
                except Exception:
                    hyp_gpu_warnings[hyp_id] = []
                    hyp_gpu_notes[hyp_id] = []
            # Filter warnings relevant to this specific GPU's PCI address
            all_warnings = hyp_gpu_warnings.get(hyp_id, [])
            item["gpu_warnings"] = (
                ([w for w in all_warnings if pci_bdf and pci_bdf in w] or all_warnings)
                if all_warnings
                else []
            )
            # Filter notes relevant to this specific GPU's PCI address
            all_notes = hyp_gpu_notes.get(hyp_id, [])
            item["gpu_notes"] = (
                ([n for n in all_notes if pci_bdf and pci_bdf in n] or all_notes)
                if all_notes
                else []
            )
        return list(items)

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
        _validate_item("gpus", new_gpu)

        with app.app_context():
            if not _check(
                r.table("gpus").insert(new_gpu, conflict="update").run(db.conn),
                "inserted",
            ):
                raise Error(
                    "internal_server",
                    "Unable to insert bookable in database.",
                    description_code="unable_to_insert",
                )

        return new_gpu

    def update_item(self, item_id, data):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        with app.app_context():
            if not _check(
                r.table("gpus").get(item_id).update(data).run(db.conn),
                "replaced",
            ):
                raise Error(
                    "internal_server",
                    "Unable to update GPU in database.",
                    description_code="unable_to_update",
                )
        with app.app_context():
            return r.table("gpus").get(item_id).run(db.conn)

    def list_profiles(self):
        with app.app_context():
            return list(r.table("gpu_profiles").run(db.conn))

    def enable_subitem(self, item_id, subitem_id, enabled):
        # Reject a malformed "~<variant>" qualifier early (choke point for every
        # enable/disable caller) so a bad label can never reach id/suffix parsing.
        variant = split_qualifier(subitem_id)[1]
        if variant is not None and not _VARIANT_RE.match(variant):
            raise Error(
                "bad_request",
                "Invalid vGPU variant name '%s' (use 1-20 lowercase alphanumerics)"
                % variant,
                description_code="bad_request",
            )
        # A variant name must map to a SINGLE base profile: the same "~<name>" may
        # be re-used to join the identical profile across several cards (same base
        # id), but never attached to a DIFFERENT profile (a different brand-model-
        # suffix, i.e. a different RAM size) -- that would be an operator mistake.
        # Only guard when enabling; a disable targets an id that already exists.
        if enabled and variant is not None:
            base = split_qualifier(subitem_id)[0]
            with app.app_context():
                clashes = list(
                    r.table("reservables_vgpus")
                    .filter(lambda res: res["id"].match("~" + variant + "$"))
                    .pluck("id")
                    .run(db.conn)
                )
            for res in clashes:
                if split_qualifier(res["id"])[0] != base:
                    raise Error(
                        "bad_request",
                        "vGPU variant '%s' is already used by profile '%s'; pick a "
                        "different name or the matching profile."
                        % (variant, res["id"]),
                        description_code="bad_request",
                    )
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
        with app.app_context():
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
        with app.app_context():
            gpus_enabled_subitem = list(
                r.table("gpus")
                .filter(lambda gpu: gpu["profiles_enabled"].contains(subitem_id))
                .run(db.conn)
            )
        if enabled:
            self.add_reservable_vgpu(item_id, subitem_id)
        # if it's the last profile of this kind, delete it
        elif len(gpus_enabled_subitem) == 0:
            self.delete_reservable_vgpu(subitem_id)
        else:
            # Non-last disable: a realizing card went away but the reservable
            # survives. enable_subitem is the single choke point every disable
            # caller goes through (admin PUT, delete_item loop, GPU reconcile),
            # so recompute the total_units invariant HERE rather than in each
            # caller (it was previously left stale -> capacity overcount).
            self.recompute_total_units(subitem_id)
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
        # Canonical base id from the card + profile; preserve any "~<variant>"
        # qualifier the admin attached so two same brand-model-profile cards can
        # be distinct, separately-bookable reservables. The variant is also shown
        # in the human name/description.
        variant = split_qualifier(subitem_id)[1]
        base_id = item["brand"] + "-" + item["model"] + "-" + subitem["profile"]
        reservable_id = base_id + ("~" + variant if variant else "")
        variant_label = " [" + variant + "]" if variant else ""
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
            + variant_label
            + " with "
            + str(subitem["memory"])
            + " vRAM with maximum "
            + str(subitem["units"])
            + " vGPUs per device",
            "heads": 1,
            "id": reservable_id,
            "model": item["model"],
            "name": "GPU "
            + item["brand"]
            + " "
            + item["model"]
            + " "
            + str(subitem["memory"])
            + variant_label,
            "profile": subitem["profile"],
            "ram": subitem["memory"],
            "vram": subitem["memory"],
            "units": subitem["units"],
            "priority_id": "default",
        }
        with app.app_context():
            replaced = _check(
                r.table("reservables_vgpus")
                .insert(new_reservable_vgpu, conflict="update")
                .run(db.conn),
                "replaced",
            )
        if not replaced:
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
                        & profiles["physical_device"].default(None).ne(None)
                    )
                    .count()
                    .run(db.conn)
                )
            with app.app_context():
                units_profile = list(
                    r.table("reservables_vgpus")
                    .filter(lambda id: id["id"].eq(new_reservable_vgpu["id"]))["units"]
                    .run(db.conn)
                )
            total_units = total_profiles * units_profile[0]

            with app.app_context():
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

    def recompute_total_units(self, subitem_id):
        """Recompute ``reservables_vgpus.total_units`` for one profile.

        ``total_units = (# gpus whose profiles_enabled contains subitem_id) *
        units``. This centralizes the formula already used by
        :meth:`add_reservable_vgpu` so that DISABLING a non-last card (via
        :meth:`enable_subitem`, which does not recompute) keeps the invariant
        correct. No-op when the reservable no longer exists (it was the last
        card and the row was already deleted)."""
        with app.app_context():
            reservable = r.table("reservables_vgpus").get(subitem_id).run(db.conn)
        if not reservable:
            return
        with app.app_context():
            total_profiles = (
                r.table("gpus")
                .filter(
                    lambda gpu: gpu["profiles_enabled"].contains(subitem_id)
                    & gpu["physical_device"].default(None).ne(None)
                )
                .count()
                .run(db.conn)
            )
        total_units = total_profiles * reservable.get("units", 0)
        with app.app_context():
            r.table("reservables_vgpus").get(subitem_id).update(
                {"total_units": total_units}
            ).run(db.conn)

    def _variants_by_base(self):
        """Map each base reservable id (``brand-model-suffix``) to the set of
        ``~<name>`` variant names currently defined for it across all cards.

        Sourced from ``reservables_vgpus`` so the admin UI can offer the exact
        names already in use for a profile (to join the same profile over several
        cards without retyping/mistyping the label)."""
        with app.app_context():
            ids = list(r.table("reservables_vgpus").pluck("id").run(db.conn))
        out = {}
        for row in ids:
            base, name = split_qualifier(row["id"])
            if name:
                out.setdefault(base, set()).add(name)
        return out

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
        # Attach the variant names already defined for each base profile so the
        # admin can re-use an exact "~<name>" (instead of free-typing it) to join
        # the same profile across cards. Empty list when none exist yet.
        variants_by_base = self._variants_by_base()
        for subitem in subitems:
            subitem["variants"] = sorted(variants_by_base.get(subitem.get("id"), set()))
        return subitems

    def list_subitems_enabled(self, item_id):
        with app.app_context():
            item = r.table("gpus").get(item_id).run(db.conn)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table: " + str(item_id),
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
                )[0].get("profiles")
            # Resolve against the BASE id; an optional "~<variant>" qualifier is
            # an admin label on the reservable, not part of the hardware profile
            # catalog, so strip it before matching gpu_profiles.
            base_subitem_id = split_qualifier(subitem_id)[0]
            subitem = [s for s in subitems if s.get("id") == base_subitem_id][0]
        except:
            log.debug(traceback.format_exc())
            raise Error(
                "not_found", "Gpu id " + item_id + " not found in gpu definitions table"
            )
        return subitem

    def check_last_subitem(self, subitem_id):
        last = 0
        with app.app_context():
            all_profiles_enabled = r.table("gpus")["profiles_enabled"].run(db.conn)
        for profiles in all_profiles_enabled:
            for pf in profiles:
                if subitem_id == pf:
                    last += 1
                if last > 1:
                    return False
        return True

    def check_desktops_with_profile(self, subitem_id):
        with app.app_context():
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
                .run(db.conn)
            )
        return desktops

    def check_deployments_with_profile(self, subitem_id):
        with app.app_context():
            deployments = list(
                r.table("deployments")
                .get_all(subitem_id, index="vgpus")
                .pluck("id", "user", "tag_name")
                .map(
                    lambda doc: {
                        "id": doc["id"],
                        "user": doc["user"],
                        "username": r.table("users")
                        .get(doc["user"])["username"]
                        .default("deleted-user"),
                        "tag_name": doc["tag_name"],
                    }
                )
                .run(db.conn)
            )
        return deployments

    def deassign_desktops_with_gpu(self, item_id, desktops):
        query = r.table("domains")
        if desktops is None:
            query = query.get_all(item_id, index="vgpus")
        else:
            query = query.get_all(r.args(desktops))

        with app.app_context():
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
                db.conn
            )
        return desktops

    def deassign_deployments_with_gpu(self, item_id, deployments=None):
        deployments_batch_size = 100
        for i in range(0, len(deployments), deployments_batch_size):
            batch_deployments = deployments[i : i + deployments_batch_size]
            with app.app_context():
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
                ).run(db.conn)

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

    def add_subitem_cascade_actions(self, subitem_id):
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

    def add_subitem_cascade_actions(self, subitem_id):
        None
