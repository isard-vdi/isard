#!/usr/bin/env python
# coding=utf-8
# License: AGPLv3
"""v189 vGPU upgrade helpers.

On apiv4-integration this migration runs as **v198** (upstream main ships
it as v189 in MR !4496; v196 is the auth action_after_migrate refactor and
v197 is the cutover reconciliation; the ``v189_*`` names are kept verbatim
for cross-branch diffability).

The pure canon/unify/merge helpers live at module level with `re` as the only
hard dependency so ``upgrade_vgpu_unify_test.py`` can load this file directly
(``upgrade.py`` itself cannot be imported bare: humanfriendly, rethinkdb,
config). The v189 DB cascade functions take the ``Upgrade`` instance and are
only callable from the initdb runtime, where rethinkdb and the package-relative
log resolve.
"""

import json
import re

try:  # pragma: no cover - present in the initdb runtime, absent in unit tests
    from rethinkdb import RethinkDB

    from .log import log

    r = RethinkDB()
except ImportError:
    r = None
    log = None


_VGPU_PROFILE_SUFFIX_RE = re.compile(
    r"-(\d+-\d+[ABCQ]|\d+[ABCQ]|\d+g\.\d+gb(?:_[a-z]+)?|passthrough)$"
)


def _canon_vgpu_profile(profile_id):
    """Canonical two-dash vGPU id. Idempotent; non-vGPU strings pass through."""
    if not isinstance(profile_id, str):
        return profile_id
    cleaned = re.sub(r"\s+", "", profile_id)
    m = _VGPU_PROFILE_SUFFIX_RE.search(cleaned)
    if not m:
        return cleaned if cleaned != profile_id else profile_id
    suffix = m.group(1).replace("-", "_")
    prefix = cleaned[: m.start()]
    if "-" in prefix:
        brand, _, model = prefix.partition("-")
        prefix = f"{brand}-{model.replace('-', '')}"
    return f"{prefix}-{suffix}"


def _canon_vgpu_model(model):
    """Canonical dash- and space-free MODEL string."""
    if not isinstance(model, str):
        return model
    return model.replace(" ", "").replace("-", "")


def _dedupe_ordered(seq):
    """Order-preserving dedupe."""
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


# --- model-token unification (v189) ------------------------------------------
# Physically identical cards (same PCI device) historically received DIFFERENT
# MODEL tokens depending on which discovery path produced the name: the vGPU
# profile name ("RTXPro6000BlackwellDC"), the nvidia-smi product name
# ("RTXPRO6000BlackwellServerEdition"), or the sysfs + pci.ids die-label
# fallback used when NVML fails ("GB202GL[RTXPRO6000BlackwellServerEdition]",
# "GA107GL[A2/A16]"). They then fragmented into disjoint reservable/profile
# pools, so a profile booked on one card could not schedule on an identical one.
#
# This collapses the known stale tokens onto one canonical token per model.
# Mirrors the runtime alias in gpu_discovery._MODEL_ALIASES (keyed there by PCI
# device-id; keyed here by the stored model string, since the migration has no
# hardware access). Matching is space/dash/slash- and case-insensitive; the
# canonical OUTPUT is verbatim. Unmapped tokens map to themselves, so this is a
# no-op for already-consistent installs (A40, L40S, single-source A16, …).
def _unify_norm(token):
    return token.replace(" ", "").replace("-", "").replace("/", "").lower()


_MODEL_SURVIVOR = {
    _unify_norm("RTXPro6000BlackwellDC"): "RTXPro6000BlackwellDC",
    _unify_norm("RTXPRO6000BlackwellServerEdition"): "RTXPro6000BlackwellDC",
    _unify_norm("GB202GL[RTXPRO6000BlackwellServerEdition]"): "RTXPro6000BlackwellDC",
    _unify_norm("A16"): "A16",
    _unify_norm("GA107GL[A2A16]"): "A16",
}


def _unify_model(model):
    """Canonical survivor token for a stored MODEL string (identity if unmapped)."""
    if not isinstance(model, str):
        return model
    return _MODEL_SURVIVOR.get(_unify_norm(model), model)


def _unify_then_canon(profile_id):
    """Unify the MODEL segment of a BRAND-MODEL-SUFFIX id, then canonicalize.

    Runs _canon_vgpu_profile first (exactly two dashes, canonical suffix), then
    rewrites the MODEL segment to its survivor token. Idempotent; non-vGPU
    strings pass through unchanged.
    """
    cid = _canon_vgpu_profile(profile_id)
    if isinstance(cid, str) and cid.count("-") == 2:
        brand, model, suffix = cid.split("-", 2)
        new_model = _unify_model(model)
        if new_model != model:
            return f"{brand}-{new_model}-{suffix}"
    return cid


def _merge_allowed(a, b):
    """UNION two IsardVDI ``allowed`` dicts (False=none, True=all, list=subset)."""
    out = {}
    for k in ("roles", "categories", "groups", "users"):
        av = a.get(k, False) if isinstance(a, dict) else False
        bv = b.get(k, False) if isinstance(b, dict) else False
        if av is True or bv is True:
            out[k] = True
        else:
            la = av if isinstance(av, list) else []
            lb = bv if isinstance(bv, list) else []
            merged = _dedupe_ordered(la + lb)
            out[k] = merged if merged else False
    return out


def _merge_reservable_patch(survivor, loser):
    """Fields to set on the survivor reservable when a loser collapses onto it:
    UNION ``allowed``, MAX the numeric capacity fields. ``total_units`` is
    recomputed separately once profiles_enabled membership is final."""
    patch = {"allowed": _merge_allowed(survivor.get("allowed"), loser.get("allowed"))}
    for f in ("units", "heads", "ram", "vram"):
        vals = [
            v for v in (survivor.get(f), loser.get(f)) if isinstance(v, (int, float))
        ]
        if vals:
            patch[f] = max(vals)
    return patch


def v189_backfill_and_canon_vgpus(upgrade):
    """v189 on the vgpus table, single pass: backfill intent fields on rows
    missing them AND canonicalize vgpu_profile/requested_profile."""
    if not r.table_list().contains("vgpus").run(upgrade.conn):
        log.info("vgpus table absent; nothing to backfill/canonicalize.")
        return
    changed = 0
    for v in r.table("vgpus").run(upgrade.conn):
        vp = v.get("vgpu_profile")
        canon_vp = _canon_vgpu_profile(vp)
        patch = {}
        if canon_vp != vp:
            patch["vgpu_profile"] = canon_vp
        if "requested_profile" not in v:
            # seed operator intent from the (canonicalized) current profile
            patch["requested_profile"] = canon_vp
            patch["operator_passthrough"] = vp == "passthrough"
        else:
            rp = v.get("requested_profile")
            canon_rp = _canon_vgpu_profile(rp)
            if canon_rp != rp:
                patch["requested_profile"] = canon_rp
        # Unify the MODEL token (and its info mirror) so the runtime vgpus
        # row agrees with the unified gpus.model / catalog.
        gm = v.get("model")
        if isinstance(gm, str):
            new_gm = _unify_model(_canon_vgpu_model(gm))
            if new_gm != gm:
                patch["model"] = new_gm
                info = v.get("info")
                if isinstance(info, dict) and isinstance(info.get("model"), str):
                    patch["info"] = {"model": new_gm}
        if patch:
            r.table("vgpus").get(v["id"]).update(patch).run(upgrade.conn)
            changed += 1
    log.info(f"vgpus v189: backfilled/canonicalized/unified {changed} row(s).")


def v189_canonicalize_vgpu_ids(upgrade):
    """v189: rewrite dash-form vGPU ids to canonical underscore form across
    the catalog and every reference, idempotently and crash-safely.

    No early return: every step is a no-op once already canonical, so a
    re-run after a partial failure self-heals (important — this supersedes
    the standalone normalize script, so there is no separate recovery tool).

    Ordering for the reservables_vgpus primary-key rename: insert canonical
    rows first, rewrite every reference, delete the stale rows last -- so no
    referenced id is ever briefly missing (safe even if the scheduler/engine
    are momentarily active during the init window; no need to stop them).

    v189 also UNIFIES the MODEL token: physically identical cards that
    fragmented into different model tokens (see _MODEL_SURVIVOR) are
    collapsed onto one canonical token, so a profile booked on one card
    schedules on any identical card. ``unify`` = suffix-canon + model
    rewrite; it is used for every scheduling-critical reference
    (reservables_vgpus, gpus.model/profiles_enabled, resource_planner,
    bookings, domains, deployments). gpu_profiles keeps only the in-place
    suffix-canon here (its row id carries the model, and re-registration's
    ensure_gpu_profiles re-seeds the canonical catalog row right after the
    upgrade restart) — this migration never deletes gpu_profiles rows.
    """
    canon = _canon_vgpu_profile  # suffix-only canon (gpu_profiles in place)
    unify = _unify_then_canon  # suffix-canon + MODEL-token unification

    # gpu_profiles: the per-model catalog (row id = NVIDIA-<model>, nested
    # profiles[] ids = NVIDIA-<model>-<suffix>).
    #   - NON-loser model -> canonicalize profiles[] IN PLACE (suffix
    #     dash->underscore, dedupe by id).
    #   - model that UNIFIES to a different survivor (e.g.
    #     GB202GL[...] -> RTXPro6000BlackwellDC) -> collapse the whole catalog
    #     row onto NVIDIA-<survivor>: merge its (unified, deduped) profiles[]
    #     into the survivor row (or RENAME loser->survivor when the survivor
    #     row doesn't exist, so the catalog is never lost), then DELETE the
    #     loser row. This is the ONE allowed gpu_profiles deletion: a targeted
    #     merge of a map-loser whose survivor exists/created -- NOT the
    #     bulk-predicate catalog-wipe bug that removed rows by a faulty regex.
    def _rewrite_profiles(profiles, loser_model, surv_model):
        out, seen = [], set()
        for p in profiles:
            if not isinstance(p, dict):
                out.append(p)
                continue
            np = dict(p)
            new_pid = unify(p.get("id"))
            np["id"] = new_pid
            if isinstance(new_pid, str) and new_pid.count("-") == 2:
                new_suffix = new_pid.split("-", 2)[2]
                old_suffix = p.get("profile")
                np["profile"] = new_suffix
                name = p.get("name")
                if isinstance(name, str):
                    if loser_model and surv_model and loser_model != surv_model:
                        name = name.replace(loser_model, surv_model)
                    if isinstance(old_suffix, str):
                        name = name.replace(old_suffix, new_suffix)
                    np["name"] = name
            if np["id"] in seen:
                continue  # drop a duplicate entry
            seen.add(np["id"])
            out.append(np)
        return out

    gp_changed = 0
    gp_merged = 0
    for gp in list(r.table("gpu_profiles").run(upgrade.conn)):
        profs = gp.get("profiles")
        if not isinstance(profs, list):
            continue
        model = gp.get("model")
        surv_model = (
            _unify_model(_canon_vgpu_model(model)) if isinstance(model, str) else model
        )
        unified = _rewrite_profiles(profs, model, surv_model)

        if not (isinstance(model, str) and surv_model != model):
            # not a loser: in-place suffix canon only
            if unified != profs:
                r.table("gpu_profiles").get(gp["id"]).update({"profiles": unified}).run(
                    upgrade.conn
                )
                gp_changed += 1
            continue

        # loser: collapse onto NVIDIA-<survivor>, then delete this row.
        surv_id = f"NVIDIA-{surv_model}"
        surv = r.table("gpu_profiles").get(surv_id).run(upgrade.conn)
        if surv is None:
            # rename loser -> survivor (keep the catalog entry)
            new_row = dict(gp)
            new_row["id"] = surv_id
            new_row["model"] = surv_model
            if isinstance(gp.get("name"), str):
                new_row["name"] = gp["name"].replace(model, surv_model)
            new_row["profiles"] = unified
            r.table("gpu_profiles").insert(new_row).run(upgrade.conn)
        else:
            # merge unified profiles into survivor (prefer survivor's entries)
            by_id = {
                p["id"]: p
                for p in (surv.get("profiles") or [])
                if isinstance(p, dict) and "id" in p
            }
            for p in unified:
                if isinstance(p, dict) and p.get("id") not in by_id:
                    by_id[p["id"]] = p
            r.table("gpu_profiles").get(surv_id).update(
                {"profiles": list(by_id.values())}
            ).run(upgrade.conn)
        r.table("gpu_profiles").get(gp["id"]).delete().run(upgrade.conn)
        gp_merged += 1

    # 1) reservables_vgpus: insert canonical (model-unified) rows; keep the
    #    old ones for now. A unified id can COLLIDE with an existing
    #    canonical row (e.g. a "...-RTXPro6000BlackwellDC-4Q" already present
    #    plus a stale "...-GB202GL[...]-4Q" that unifies onto it): merge the
    #    loser into the survivor (UNION allowed, MAX capacity) rather than
    #    overwrite. total_units is recomputed after profiles_enabled is final.
    rename = {}
    for row in r.table("reservables_vgpus").run(upgrade.conn):
        rid = row.get("id")
        new_id = unify(rid)
        new_model = _unify_model(_canon_vgpu_model(row.get("model", "")))
        if new_id == rid and new_model == row.get("model"):
            continue
        if new_id != rid:
            rename[rid] = new_id
            existing = r.table("reservables_vgpus").get(new_id).run(upgrade.conn)
            if existing is None:
                r.table("reservables_vgpus").insert(
                    {**row, "id": new_id, "model": new_model}
                ).run(upgrade.conn)
            else:
                patch = _merge_reservable_patch(existing, {**row, "model": new_model})
                r.table("reservables_vgpus").get(new_id).update(patch).run(upgrade.conn)
        elif new_model != row.get("model"):
            r.table("reservables_vgpus").get(rid).update({"model": new_model}).run(
                upgrade.conn
            )

    # 2) rewrite references (idempotent; unify() is a no-op once canonical).
    #    gpus: profiles_enabled AND the model join key (one row per physical
    #    GPU). Unifying gpus.model is what puts identical cards in one pool.
    #    id / gpu_uuid / physical_device / category are left untouched.
    for g in r.table("gpus").run(upgrade.conn):
        patch = {}
        old = g.get("profiles_enabled") or []
        new = _dedupe_ordered([unify(p) for p in old])
        if new != old:
            patch["profiles_enabled"] = new
        gm = g.get("model")
        if isinstance(gm, str):
            new_gm = _unify_model(_canon_vgpu_model(gm))
            if new_gm != gm:
                patch["model"] = new_gm
        if patch:
            r.table("gpus").get(g["id"]).update(patch).run(upgrade.conn)

    #    resource_planner.subitem_id (narrow to GPU plannings; small table)
    if r.table_list().contains("resource_planner").run(upgrade.conn):
        for rp in (
            r.table("resource_planner").filter({"item_type": "gpus"}).run(upgrade.conn)
        ):
            sid = rp.get("subitem_id")
            new_sid = unify(sid)
            if new_sid != sid:
                r.table("resource_planner").get(rp["id"]).update(
                    {"subitem_id": new_sid}
                ).run(upgrade.conn)

    #    bookings: rewrite BOTH reservables.vgpus AND the embedded
    #    plans[].subitem_id (each plan stores the full profile id). has_fields
    #    narrows server-side to GPU bookings (a GPU booking always carries
    #    reservables.vgpus; the reservables_vgpus index is NOT multi, so it
    #    can't be used for an element lookup).
    for b in (
        r.table("bookings")
        .has_fields({"reservables": {"vgpus": True}})
        .pluck("id", {"reservables": {"vgpus": True}}, "plans")
        .run(upgrade.conn)
    ):
        patch = {}
        vg = (b.get("reservables") or {}).get("vgpus") or []
        new_vg = [unify(v) for v in vg]
        if new_vg != vg:
            patch["reservables"] = {"vgpus": new_vg}
        plans = b.get("plans")
        if isinstance(plans, list):
            new_plans = []
            plans_changed = False
            for p in plans:
                if isinstance(p, dict) and isinstance(p.get("subitem_id"), str):
                    ns = unify(p["subitem_id"])
                    if ns != p["subitem_id"]:
                        p = {**p, "subitem_id": ns}
                        plans_changed = True
                new_plans.append(p)
            if plans_changed:
                patch["plans"] = new_plans
        if patch:
            r.table("bookings").get(b["id"]).update(patch).run(upgrade.conn)

    #    domains (BIG): create_dict is a dict; has_fields narrows server-side
    #    and the nested update deep-merges (touches only .vgpus).
    for d in (
        r.table("domains")
        .has_fields({"create_dict": {"reservables": {"vgpus": True}}})
        .pluck("id", {"create_dict": {"reservables": {"vgpus": True}}})
        .run(upgrade.conn)
    ):
        vg = d["create_dict"]["reservables"].get("vgpus") or []
        new = [unify(v) for v in vg]
        if new != vg:
            r.table("domains").get(d["id"]).update(
                {"create_dict": {"reservables": {"vgpus": new}}}
            ).run(upgrade.conn)

    #    deployments: create_dict is a LIST -- rewrite element-wise and write
    #    the full list back (a nested dict-merge can't target a list element).
    for dep in r.table("deployments").pluck("id", "create_dict").run(upgrade.conn):
        cds = dep.get("create_dict")
        if not isinstance(cds, list):
            continue
        changed = False
        for cd in cds:
            if not isinstance(cd, dict):
                continue
            res = cd.get("reservables")
            vg = res.get("vgpus") if isinstance(res, dict) else None
            if isinstance(vg, list):
                new = [unify(v) for v in vg]
                if new != vg:
                    res["vgpus"] = new
                    changed = True
        if changed:
            r.table("deployments").get(dep["id"]).update({"create_dict": cds}).run(
                upgrade.conn
            )

    # 2b) Recompute total_units on every (re)written reservable now that
    #     profiles_enabled membership is final: total_units = (cards whose
    #     profiles_enabled lists this reservable) * units. Unification can
    #     point more identical cards at one reservable, so a stale
    #     total_units would otherwise break the booking units invariant.
    # Recompute for the renamed/merged ids AND for every reservable still
    # referenced by any card's profiles_enabled: an already-canonical
    # SURVIVOR that absorbed cards via model unification takes the `continue`
    # above (new_id == rid), so it is absent from `rename` and would never be
    # recomputed -> its total_units would undercount the now-larger pool.
    recompute_ids = set(rename.values())
    for g in r.table("gpus").pluck("profiles_enabled").run(upgrade.conn):
        recompute_ids.update(g.get("profiles_enabled") or [])
    for new_id in recompute_ids:
        surv = r.table("reservables_vgpus").get(new_id).run(upgrade.conn)
        if not surv:
            continue
        units = surv.get("units") or 0
        cards = (
            r.table("gpus")
            .filter(
                lambda g: g["profiles_enabled"].contains(new_id)
                & g["physical_device"].default(None).ne(None)
            )
            .count()
            .run(upgrade.conn)
        )
        total_units = cards * units
        if surv.get("total_units") != total_units:
            r.table("reservables_vgpus").get(new_id).update(
                {"total_units": total_units}
            ).run(upgrade.conn)

    # 3) delete the stale (old) reservable rows last.
    for old_id in rename:
        r.table("reservables_vgpus").get(old_id).delete().run(upgrade.conn)

    log.info(
        f"v189 vGPU-id canon+unify: {gp_changed} gpu_profiles row(s) updated, "
        f"{gp_merged} catalog row(s) merged/removed; "
        f"{len(rename)} reservable id(s) renamed/unified; references rewritten."
    )


# Plain GI-name MIG profile suffix, e.g. "1g.24gb", "1g.24gb+gfx", "1g.24gb+me",
# "1g.24gb+me.all", "1g.24gb_me", "1g.24gb-me", "2g.48gb", "4g.96gb". These carve
# a single GPU-instance / expose no usable per-slice vGPU mdev, so they must not
# be bookable.
_PLAIN_GI_MIG_SUFFIX_RE = re.compile(r"^\d+g\.\d+gb")

# MIG-backed vGPU profile suffix "<slices>_<framebuffer><series>" (e.g. "1_24Q",
# "2_48Q"). Groups: slices, framebuffer-GB, series-letter. The slice separator is
# accepted as "_" OR "-": canonical ids use "_", but legacy reservable `profile`
# fields may still carry the dash form ("1-2Q") that id-canon did not rewrite.
_MIG_BACKED_SUFFIX_RE = re.compile(r"^(\d+)[-_](\d+)([ABCQ])$")


def _reservable_suffix(reservable_id):
    """``NVIDIA-<model>-<suffix>`` -> ``<suffix>`` (model is dash-free post-canon)."""
    if isinstance(reservable_id, str) and reservable_id.count("-") >= 2:
        return reservable_id.split("-", 2)[2]
    return None


def _mig_max_fb_from_suffixes(suffixes):
    """(slices, series) -> max framebuffer across the MIG-backed suffixes given.

    Per slice-tier only the largest framebuffer uses the GI's full memory; the
    smaller ones strand the rest of the GI. Computed from the complete catalog
    (gpu_profiles), since the enabled-reservables subset may omit the full one.
    """
    mx = {}
    for s in suffixes:
        if not isinstance(s, str):
            continue
        m = _MIG_BACKED_SUFFIX_RE.match(s)
        if m:
            key = (m.group(1), m.group(3))
            mx[key] = max(mx.get(key, 0), int(m.group(2)))
    return mx


def _is_non_full_use_suffix(suffix, mig_max_fb):
    """True if a profile suffix is NOT full-utilization and must be pruned:
      - plain GI-name MIG ("1g.24gb" & variants), or
      - a MIG-backed vGPU below the max framebuffer for its slice-tier (strands
        the GI's spare memory).
    Kept (full-utilization): whole-card "passthrough", time-sliced "<fb>Q", and
    the max-framebuffer MIG-backed profile per tier ("1_24Q"/"2_48Q"/"4_96Q").
    """
    if not isinstance(suffix, str):
        return False
    if _PLAIN_GI_MIG_SUFFIX_RE.match(suffix):
        return True
    m = _MIG_BACKED_SUFFIX_RE.match(suffix)
    if m:
        return int(m.group(2)) < mig_max_fb.get((m.group(1), m.group(3)), 0)
    return False


def v189_prune_non_full_use_gpu_profiles(upgrade):
    """v189: keep only full-utilization GPU profiles bookable.

    Removes both (a) the plain GI-name MIG profiles (single GI / no usable mdev)
    and (b) the partial-framebuffer MIG-backed vGPU profiles (e.g. 1_4Q on a
    24 GB 1g GI strands 20 GB). What stays: whole-card ``passthrough``,
    time-sliced ``<fb>Q`` (which partition the card's memory fully), and the
    max-framebuffer MIG-backed profile per slice-tier (``1_24Q``/``2_48Q``/
    ``4_96Q``). Pairs with ``ensure_gpu_profiles`` no longer emitting these.

    Idempotent (filtered delete/update; no-op on re-run). The per-model
    max-framebuffer is computed from the FULL gpu_profiles catalog, then applied
    to gpu_profiles, gpus.profiles_enabled and reservables_vgpus. A reservable
    still referenced by a booking is logged and kept (never drop a reservation).
    """
    conn = upgrade.conn

    # 1) gpu_profiles: per model, derive the tier max-fb from the FULL catalog,
    #    then drop non-full-use entries (in place; never delete the parent row).
    model_mig_max = {}
    gp_pruned = 0
    for gp in list(r.table("gpu_profiles").run(conn)):
        profs = gp.get("profiles")
        if not isinstance(profs, list):
            continue
        mig_max = _mig_max_fb_from_suffixes(
            [p.get("profile") for p in profs if isinstance(p, dict)]
        )
        model_mig_max[gp.get("model")] = mig_max
        kept = [
            p
            for p in profs
            if not (
                isinstance(p, dict)
                and _is_non_full_use_suffix(p.get("profile"), mig_max)
            )
        ]
        if len(kept) != len(profs):
            r.table("gpu_profiles").get(gp["id"]).update({"profiles": kept}).run(conn)
            gp_pruned += len(profs) - len(kept)

    # 2) reservables_vgpus: delete non-full-use rows not referenced by a booking.
    res_deleted = 0
    res_kept_booked = 0
    dropped_ids = set()
    for res in list(r.table("reservables_vgpus").run(conn)):
        mig_max = model_mig_max.get(res.get("model"), {})
        if not _is_non_full_use_suffix(res.get("profile"), mig_max):
            continue
        rid = res["id"]
        booked = (
            r.table("bookings")
            .filter(lambda b: b["reservables"]["vgpus"].default([]).contains(rid))
            .count()
            .run(conn)
        )
        if booked:
            log.warning(
                f"v189: reservable {rid} still has {booked} booking(s); kept in "
                f"place for manual review (not deleted)."
            )
            res_kept_booked += 1
            continue
        r.table("reservables_vgpus").get(rid).delete().run(conn)
        dropped_ids.add(rid)
        res_deleted += 1

    # 3) gpus.profiles_enabled: drop refs to dropped reservables / non-full-use.
    ge_pruned = 0
    for g in r.table("gpus").pluck("id", "profiles_enabled", "model").run(conn):
        enabled = g.get("profiles_enabled")
        if not isinstance(enabled, list):
            continue
        mig_max = model_mig_max.get(g.get("model"), {})
        kept = [
            rid
            for rid in enabled
            if rid not in dropped_ids
            and not _is_non_full_use_suffix(_reservable_suffix(rid), mig_max)
        ]
        if len(kept) != len(enabled):
            r.table("gpus").get(g["id"]).update({"profiles_enabled": kept}).run(conn)
            ge_pruned += len(enabled) - len(kept)

    log.info(
        f"v189: pruned non-full-use GPU profiles -- {gp_pruned} catalog entr(ies), "
        f"{ge_pruned} profiles_enabled ref(s), {res_deleted} reservable(s) deleted, "
        f"{res_kept_booked} kept (booked)."
    )


"""
Upgrade general actions
"""


def add_keys(self, table, keys, id=False):
    for key in keys:
        if id is False:
            r.table(table).update(key).run(self.conn)
        else:
            r.table(table).get(id).update(key).run(self.conn)


def del_keys(self, table, keys, id=False):
    for key in keys:
        if id is False:
            r.table(table).replace(r.row.without(key)).run(self.conn)
        else:
            r.table(table).get(id).replace(r.row.without(key)).run(self.conn)


def check_done(self, dict, must=[], mustnot=[]):
    log.info("Self check init")
    done = False
    # ~ check_done(cfg,['grafana','resources','voucher_access',{'engine':{'api':{'token'}}}],[{'engine':{'carbon'}}])
    for m in must:
        if type(m) is str:
            m = [m]
        if self.keys_exists(dict, m):
            done = True
            # ~ print(str(m)+' exists on dict. ok')
        # ~ else:
        # ~ print(str(m)+' not exists on dict. KO')

    for mn in mustnot:
        log.info(mn)
        if type(mn) is str:
            mn = [mn]
        if not self.keys_exists(dict, mn):
            done = True
            # ~ print(str(mn)+' not exists on dict. ok')
        # ~ else:
        # ~ print(str(mn)+' exists on dict. KO')
    return done


def keys_exists(self, element, keys):
    """
    Check if *keys (nested) exists in `element` (dict).
    """
    if type(element) is not dict:
        raise AttributeError("keys_exists() expects dict as first argument.")
    if len(keys) == 0:
        raise AttributeError("keys_exists() expects at least two arguments, one given.")

    _element = element
    for key in keys:
        log.info(key)
        try:
            _element = _element[key]
        except KeyError:
            return False
    return True


def index_create(self, table, indexes):
    indexes_ontable = r.table(table).index_list().run(self.conn)
    apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
    for i in apply_indexes:
        r.table(table).index_create(i).run(self.conn)
        r.table(table).index_wait(i).run(self.conn)


## To upgrade to default cards
def get_domain_stock_card(self, domain_id):
    total = 0
    for i in range(0, len(domain_id)):
        total += total + ord(domain_id[i])
    total = total % 48 + 1
    return self.get_card(str(total) + ".jpg", "stock")


def get_card(self, card_id, type):
    return {
        "id": card_id,
        "url": "/assets/img/desktops/" + type + "/" + card_id,
        "type": type,
    }


"""
System upgrades
"""


def _system_upgrades(self):
    """
    GPU_PROFILES DISK TABLE UPGRADES
    """

    log.info("Checking for new gpu_profiles...")

    try:
        f = open("./initdb/profiles/gpu_profiles.json")
        gpu_profiles = json.loads(f.read())
        f.close()
        r.table("gpu_profiles").insert(gpu_profiles, conflict="update").run(self.conn)
    except Exception as e:
        print(e)
    return True
