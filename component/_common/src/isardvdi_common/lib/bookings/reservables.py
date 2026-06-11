#!/usr/bin/env python
# coding=utf-8
# Copyright 2025 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging as log
import re as _re
import traceback
from typing import Literal
from uuid import uuid4

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.api_admin import ApiAdmin
from isardvdi_common.lib.bookings.gpu_realizability import split_qualifier
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
    with ResourceItemsGpus._rdb_context():
        cards = list(
            r.table("gpus")
            .pluck("physical_device", "profiles_enabled")
            .run(ResourceItemsGpus._rdb_connection)
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


def _pci_id_to_sysfs(pci_underscored):
    """``0000_41_00_0`` -> ``0000:41:00.0`` (the sysfs/pci_devices key form).

    Mirrors the transform the engine uses in
    ``services/db/hypervisors.py`` so a card's ``physical_device`` BDF can be
    looked up in ``hypervisors.pci_devices``.
    """
    s = pci_underscored.replace("_", ":", 2)
    return s[:-2] + "." + s[-1] if len(s) >= 2 else s


def get_vgpus_placements():
    """Map each reservable id to the ``{hyp_id: {numa_node, ...}}`` its cards occupy.

    A reservable can be enabled on several physical cards across one or more
    hypervisors, and within a multi-socket host on cards bound to different NUMA
    nodes. Returns ``{reservable_id: {hyp_id: sorted([numa_node, ...])}}`` using
    only real nodes (``>= 0``; ``-1``/unknown/single-socket affinity is dropped),
    so the UI can group selectable cards by (server, socket) and hint when two
    profiles can share a socket. The card's NUMA node lives in
    ``hypervisors.pci_devices[<sysfs_bdf>].numa_node`` (discovered from sysfs).
    """
    with ResourceItemsGpus._rdb_context():
        cards = list(
            r.table("gpus")
            .pluck("physical_device", "profiles_enabled")
            .run(ResourceItemsGpus._rdb_connection)
        )
        hypers = list(
            r.table("hypervisors")
            .pluck("id", "pci_devices")
            .run(ResourceItemsGpus._rdb_connection)
        )
    # {hyp_id: {sysfs_bdf: numa_node}}
    numa_by_hyp_bdf = {
        h["id"]: (h.get("pci_devices") or {}) for h in hypers if h.get("id")
    }
    placements = {}  # {reservable_id: {hyp_id: set(numa_node)}}
    for card in cards:
        physical_device = card.get("physical_device") or ""
        if "-pci_" not in physical_device:
            continue
        hyp_id, pci_part = physical_device.rsplit("-pci_", 1)
        if not hyp_id:
            continue
        sysfs_bdf = _pci_id_to_sysfs(pci_part)
        numa = (numa_by_hyp_bdf.get(hyp_id, {}).get(sysfs_bdf, {}) or {}).get(
            "numa_node"
        )
        try:
            numa = int(numa)
        except (TypeError, ValueError):
            numa = None
        if numa is None or numa < 0:
            continue
        for profile_id in card.get("profiles_enabled") or []:
            placements.setdefault(profile_id, {}).setdefault(hyp_id, set()).add(numa)
    return placements


def attach_vgpu_hypervisor_groups(vgpus, show_names):
    """Tag each vGPU profile with the hypervisor groups that can host it.

    A multi-profile desktop must keep all its profiles on one hypervisor, so the
    UI needs to know which profiles share a host. Always attach
    ``hypervisor_groups`` (anonymized stable indices — two profiles are
    co-selectable iff their lists intersect). When ``show_names`` (admin/webapp)
    also attach the real ``hypervisors`` names for grouped labels. Tolerates
    items missing an ``id`` and a non-list input.

    Also attach the NUMA-socket placement of each profile's cards so the UI can
    sub-group server → socket and hint when two profiles can share a socket
    (best memory bandwidth). ``numa_by_group`` keys on the anonymized hypervisor
    index (``{"1": [0, 1]}``); with ``show_names`` also ``numa_by_hypervisor``
    keyed on the real hypervisor id. Nodes are real (``>= 0``) only, so a
    single-socket / unknown-NUMA server yields an empty mapping and the UI shows
    no socket layer.
    """
    if not isinstance(vgpus, list):
        return vgpus
    return _tag_vgpus_with_groups(
        vgpus, get_vgpus_hypervisors(), get_vgpus_placements(), show_names
    )


def _tag_vgpus_with_groups(vgpus, hyp_map, placements, show_names):
    """Pure tagging step of :func:`attach_vgpu_hypervisor_groups` (no DB).

    ``hyp_map`` is ``{reservable_id: [hyp_id, ...]}`` and ``placements`` is
    ``{reservable_id: {hyp_id: iterable(numa_node)}}``. Kept dependency-free so it
    can be unit-tested without booting Flask.
    """
    if not isinstance(vgpus, list):
        return vgpus
    ordered_hyps = sorted({h for v in vgpus for h in hyp_map.get(v.get("id"), [])})
    anon_index = {h: i + 1 for i, h in enumerate(ordered_hyps)}
    for v in vgpus:
        hyps = hyp_map.get(v.get("id"), [])
        v["hypervisor_groups"] = [anon_index[h] for h in hyps]
        placement = placements.get(v.get("id"), {})
        v["numa_by_group"] = {
            str(anon_index[h]): sorted(nodes)
            for h, nodes in placement.items()
            if h in anon_index and nodes
        }
        if show_names:
            v["hypervisors"] = hyps
            v["numa_by_hypervisor"] = {
                h: sorted(nodes) for h, nodes in placement.items() if nodes
            }
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
        with cls._rdb_context():
            items = list(query.run(cls._rdb_connection))
        # Cache gpu_warnings / gpu_notes per hypervisor to avoid repeated queries
        hyp_gpu_warnings = {}
        hyp_gpu_notes = {}
        for item in items:
            if item.get("active_profile"):
                with cls._rdb_context():
                    matching_profiles = list(
                        r.table("gpu_profiles")
                        .get_all(
                            [item["brand"], item["model"]],
                            index="brand-model",
                        )
                        .concat_map(lambda doc: doc["profiles"])
                        .filter(lambda p: p["profile"] == item["active_profile"])
                        .run(cls._rdb_connection)
                    )
                # ``HypervisorsProcessed.ensure_gpu_profiles`` seeds every
                # discovered (brand, model) pair on hypervisor registration
                # with the full profile catalog (passthrough + vgpu + mig).
                # A missing entry here therefore signals stale data: a GPU
                # model that was renamed by ``_normalize_gpu_model``, or a
                # legacy desktop bound to a card whose hypervisor has never
                # re-registered. Fall back to ``available_units = 0``
                # instead of 500'ing the whole admin listing.
                if not matching_profiles:
                    log.warning(
                        "gpu_profiles[%s/%s] missing active_profile %r; "
                        "stale catalog — re-register the hypervisor to "
                        "rebuild the entry",
                        item["brand"],
                        item["model"],
                        item["active_profile"],
                    )
                    item["available_units"] = 0
                else:
                    # ``available_units`` here is the CATALOG capacity for the
                    # active profile (max vGPUs the card supports). The
                    # change-handler ``vgpus`` event carries the same field
                    # name but reports the LIVE mdev pool size — they
                    # usually agree but transiently diverge during boot or
                    # after a profile switch. Both frontends ignore the
                    # divergence and accept whichever arrives last.
                    available_units = matching_profiles[0]
                    item["available_units"] = available_units["units"]
                    item["active_profile"] = cls.get_subitem(
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
                    with cls._rdb_context():
                        hyp_data = (
                            r.table("hypervisors")
                            .get(hyp_id)
                            .pluck("gpu_warnings", "gpu_notes")
                            .default({})
                            .run(cls._rdb_connection)
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

    @classmethod
    def add_item(cls, data):
        with cls._rdb_context():
            duplicates = list(
                r.table("gpus")
                .filter({"name": data["name"]})
                .limit(1)
                .run(cls._rdb_connection)
            )
        if duplicates:
            raise Error(
                "conflict",
                f'A GPU with name "{data["name"]}" already exists.',
                description_code="duplicated_name",
            )
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
            # Required by ``GPUsModel`` (``Literal["gpus", "usbs"]``) and by
            # the polymorphic dispatch in
            # ``ReservablesPlannerProcess.check_subitem_*``. Omitting it
            # tripped a Pydantic ResourceValidationError below and surfaced
            # as a 500 on ``POST /api/v4/item/reservable/gpus``. Tracked as
            # Bug 36 in APIV4_LOAD_TESTING_BUGS_FOUND.md.
            "reservable_type": "gpus",
        }
        GPUsModel(**new_gpu)

        with cls._rdb_context():
            insert_result = (
                r.table("gpus")
                .insert(new_gpu, conflict="update")
                .run(cls._rdb_connection)
            )
        if not Helpers._check(insert_result, "inserted"):
            raise Error(
                "internal_server",
                "Unable to insert bookable in database.",
                description_code="unable_to_insert",
            )
        generated = insert_result.get("generated_keys") or []
        if generated:
            new_gpu["id"] = generated[0]
        return new_gpu

    @classmethod
    def list_profiles(cls):
        with cls._rdb_context():
            return list(r.table("gpu_profiles").run(cls._rdb_connection))

    @classmethod
    def enable_subitem(cls, item_id, subitem_id, enabled):
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
            with cls._rdb_context():
                clashes = list(
                    r.table("reservables_vgpus")
                    .filter(lambda res: res["id"].match("~" + variant + "$"))
                    .pluck("id")
                    .run(cls._rdb_connection)
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
        with cls._rdb_context():
            item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        if not item:
            raise Error(
                "not_found",
                "Gpu id not found in gpu table",
                description_code="not_found",
            )
        # Idempotent: a repeated enable must not duplicate the id in
        # profiles_enabled (a double-click / retried PUT otherwise leaves a
        # dangling copy that only an equal number of disables can clear), and a
        # disable strips every occurrence so the reservable is fully released.
        enabled_profiles = item["profiles_enabled"]
        if enabled:
            if subitem_id not in enabled_profiles:
                enabled_profiles.append(subitem_id)
        else:
            enabled_profiles = [p for p in enabled_profiles if p != subitem_id]
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
        else:
            # Non-last disable: a realizing card went away but the reservable
            # survives. enable_subitem is the single choke point every disable
            # caller goes through (admin PUT, delete_item loop, GPU reconcile),
            # so recompute the total_units invariant HERE rather than in each
            # caller (it was previously left stale -> capacity overcount).
            cls.recompute_total_units(subitem_id)
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
                        & profiles["physical_device"].default(None).ne(None)
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
            # Bypass the ApiAdmin 5 s TTL cache so the Bookables admin
            # listing reflects the new row immediately after enable.
            ApiAdmin.clear_admin_table_list_cache("reservables_vgpus")

    @classmethod
    def recompute_total_units(cls, subitem_id):
        """Recompute ``reservables_vgpus.total_units`` for one profile.

        ``total_units = (# gpus whose profiles_enabled contains subitem_id) *
        units``. This centralizes the formula already used by
        :meth:`add_reservable_vgpu` so that DISABLING a non-last card (via
        :meth:`enable_subitem`, which does not recompute) keeps the invariant
        correct. No-op when the reservable no longer exists (it was the last
        card and the row was already deleted)."""
        with cls._rdb_context():
            reservable = (
                r.table("reservables_vgpus").get(subitem_id).run(cls._rdb_connection)
            )
        if not reservable:
            return
        with cls._rdb_context():
            total_profiles = (
                r.table("gpus")
                .filter(
                    lambda gpu: gpu["profiles_enabled"].contains(subitem_id)
                    & gpu["physical_device"].default(None).ne(None)
                )
                .count()
                .run(cls._rdb_connection)
            )
        total_units = total_profiles * reservable.get("units", 0)
        with cls._rdb_context():
            r.table("reservables_vgpus").get(subitem_id).update(
                {"total_units": total_units}
            ).run(cls._rdb_connection)
        # apiv4-integration: bypass the ApiAdmin 5 s TTL cache so the Bookables
        # admin listing reflects the corrected capacity immediately.
        ApiAdmin.clear_admin_table_list_cache("reservables_vgpus")

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
                ApiAdmin.clear_admin_table_list_cache("reservables_vgpus")
            else:
                raise Error(
                    "not_found",
                    "Reservable vgpu id not found in reservables_vgpus table",
                )

    @classmethod
    def _variants_by_base(cls):
        """Map each base reservable id (``brand-model-suffix``) to the set of
        ``~<name>`` variant names currently defined for it across all cards.

        Sourced from ``reservables_vgpus`` so the admin UI can offer the exact
        names already in use for a profile (to join the same profile over several
        cards without retyping/mistyping the label)."""
        with cls._rdb_context():
            ids = list(
                r.table("reservables_vgpus").pluck("id").run(cls._rdb_connection)
            )
        out = {}
        for row in ids:
            base, name = split_qualifier(row["id"])
            if name:
                out.setdefault(base, set()).add(name)
        return out

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
        # Attach the variant names already defined for each base profile so the
        # admin can re-use an exact "~<name>" (instead of free-typing it) to join
        # the same profile across cards. Empty list when none exist yet.
        variants_by_base = cls._variants_by_base()
        for subitem in subitems:
            subitem["variants"] = sorted(variants_by_base.get(subitem.get("id"), set()))
        return subitems

    @classmethod
    def list_subitems_enabled(cls, item_id):
        try:
            with cls._rdb_context():
                item = r.table("gpus").get(item_id).run(cls._rdb_connection)
        except r.errors.ReqlError:
            raise Error(
                "not_found",
                "GPU reservables not configured.",
                description_code="not_found",
            )
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
        except (IndexError, KeyError, r.errors.ReqlError):
            raise Error(
                "not_found",
                "Gpu id not found in gpu definitions table",
                description_code="not_found",
            )
        enabled = item.get("profiles_enabled") or []
        return [subitem for subitem in subitems if subitem["id"] in enabled]

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
            # Resolve against the BASE id; an optional "~<variant>" qualifier is
            # an admin label on the reservable, not part of the hardware profile
            # catalog, so strip it before matching gpu_profiles.
            base_subitem_id = split_qualifier(subitem_id)[0]
            subitem = [s for s in subitems if s.get("id") == base_subitem_id][0]
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
        # Drop any "~<variant>" qualifier, then split on the FIRST two dashes only
        # so a dashed-MIG suffix (e.g. "1-2Q") stays intact; profile is the suffix
        # part, not the model (the previous parts[1]/parts[1] was a bug).
        base = split_qualifier(subitem)[0]
        parts = base.split("-", 2)
        return {
            "brand": parts[0],
            "model": parts[1] if len(parts) > 1 else "",
            "profile": parts[2] if len(parts) == 3 else "",
        }

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
        try:
            with cls._rdb_context():
                item = r.table("usbs").get(item_id).run(cls._rdb_connection)
        except r.errors.ReqlError:
            raise Error(
                "not_found",
                "USB reservables not configured.",
                description_code="not_found",
            )
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
        except (IndexError, KeyError, r.errors.ReqlError):
            raise Error("not_found", "Usb id not found in usb definitions table")
        enabled = item.get("profiles_enabled") or []
        return [subitem for subitem in subitems if subitem["id"] in enabled]

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


class ReservablesProcessed(RethinkSharedConnection):
    """Generic Layer-2 helpers for reservable items (gpus, usbs).

    Per-type behaviour (profile assignment, plan computations) lives
    in the existing ``ResourceItems<Type>`` classes. This class hosts
    the table-agnostic CRUD that the apiv4 service layer dispatches
    via ``reservable_type``.
    """

    @classmethod
    def get_item(cls, table: str, item_id: str) -> dict | None:
        """Return a single reservable row by id, or ``None`` if missing.

        ``table`` is the rethinkdb table name (``gpus`` / ``usbs``);
        the apiv4 service maps the reservable_type to the table.
        """
        with cls._rdb_context():
            return r.table(table).get(item_id).run(cls._rdb_connection)

    @classmethod
    def name_exists_for_other(cls, table: str, name: str, exclude_item_id: str) -> bool:
        """Return ``True`` if any row in ``table`` carries ``name`` and
        is not ``exclude_item_id``.

        Used to enforce per-table uniqueness on rename.
        """
        with cls._rdb_context():
            existing = list(
                r.table(table)
                .filter(
                    lambda row: (row["name"] == name) & (row["id"] != exclude_item_id)
                )
                .run(cls._rdb_connection)
            )
        return bool(existing)

    @classmethod
    def update_item(cls, table: str, item_id: str, update_data: dict) -> None:
        """Apply ``update_data`` to ``item_id`` in ``table``.

        Idempotent on a missing row (rdb returns skipped=1, no error).
        Empty ``update_data`` is also a no-op.
        """
        if not update_data:
            return
        with cls._rdb_context():
            r.table(table).get(item_id).update(update_data).run(cls._rdb_connection)
