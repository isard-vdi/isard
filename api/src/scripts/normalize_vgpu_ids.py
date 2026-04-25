#!/usr/bin/env python3
"""Normalize vGPU profile identifiers to the canonical BRAND-MODEL-PROFILE shape.

vGPU identifiers in IsardVDI must contain exactly two dashes — one separating
BRAND from MODEL, one separating MODEL from PROFILE — so that every consumer
can split them with ``split("-")`` (3 tokens) without per-card special cases.
Earlier discovery code allowed two violations of this invariant:

  - whitespace inside MODEL (commercial names like "RTX Pro 6000 Blackwell DC"),
  - extra dashes inside the PROFILE suffix (MIG-backed profiles like
    "1-4Q", "2-24Q", "4-96Q").

Either shape produces ids that downstream code mis-splits, leaving stale
rows in ``reservables_vgpus``, ``gpus.profiles_enabled``,
``domains.create_dict.reservables.vgpus``, and ghost ``gpu_profiles``.

This script rewrites those rows in place. It is idempotent: a database that
already conforms to the invariant is a no-op. It is generic: no card model,
brand, or profile name is hard-coded — the canonicalization is driven by a
regex over the four NVIDIA suffix classes (Q/A/B/C).

Run inside the api container::

    docker exec -i isard-api python3 < api/src/scripts/normalize_vgpu_ids.py

Or, if mounted at runtime::

    docker exec isard-api python3 /isard/api/src/scripts/normalize_vgpu_ids.py
"""

import re
import sys

from rethinkdb import r

# Profile suffix shapes published by sysfs ``mdev_supported_types/<id>/name``:
#   simple time-sliced:    "<MODEL>-<MEM><CLASS>"        e.g. A40-4Q, A40-2B
#   MIG-backed with slot:  "<MODEL>-<SLOT>-<MEM><CLASS>" e.g. A100-1-5C
# <CLASS> is one of Q (workstation), A (VDI apps), B (virtual desktop),
# C (compute).
_PROFILE_SUFFIX_RE = re.compile(r"-(\d+-\d+[ABCQ]|\d+[ABCQ])$")


def _canon_profile(profile_id):
    """Return the canonical 2-dash form of a vGPU profile id.

    Strips internal whitespace from MODEL, replaces dashes inside the PROFILE
    suffix with underscores. Returns the input unchanged when no rewriting is
    needed (idempotent). Returns the input unchanged when the shape is not
    recognised, so non-vGPU strings flow through untouched.
    """
    if not isinstance(profile_id, str):
        return profile_id
    cleaned = re.sub(r"\s+", "", profile_id)
    m = _PROFILE_SUFFIX_RE.search(cleaned)
    if not m:
        return cleaned if cleaned != profile_id else profile_id
    suffix = m.group(1)
    if "-" in suffix:
        new_suffix = suffix.replace("-", "_")
        cleaned = cleaned[: m.start()] + "-" + new_suffix
    return cleaned


def _canon_model(model):
    """Return the canonical dash-and-space-free MODEL string."""
    if not isinstance(model, str):
        return model
    return model.replace(" ", "").replace("-", "")


def _is_recognised(profile_id):
    """Truthy iff profile_id matches the BRAND-MODEL-<suffix> shape."""
    return isinstance(profile_id, str) and bool(
        _PROFILE_SUFFIX_RE.search(re.sub(r"\s+", "", profile_id))
    )


def _dedupe(seq):
    """Order-preserving dedupe."""
    seen = set()
    return [x for x in seq if not (x in seen or seen.add(x))]


def _rewrite_reservables_vgpus(conn):
    print("=== reservables_vgpus ===")
    changed = 0
    for row in r.table("reservables_vgpus").run(conn):
        rid = row.get("id")
        new_id = _canon_profile(rid)
        new_model = _canon_model(row.get("model", ""))
        if new_id == rid and new_model == row.get("model"):
            continue
        print(f"  rename {rid!r} -> {new_id!r}")
        new_row = dict(row, id=new_id, model=new_model)
        if r.table("reservables_vgpus").get(new_id).run(conn) is None:
            r.table("reservables_vgpus").insert(new_row).run(conn)
        r.table("reservables_vgpus").get(rid).delete().run(conn)
        changed += 1
    print(f"  rewrote {changed} row(s)")


def _rewrite_gpus_profiles_enabled(conn):
    print("=== gpus.profiles_enabled ===")
    changed = 0
    for g in r.table("gpus").run(conn):
        old = g.get("profiles_enabled") or []
        new = _dedupe(_canon_profile(p) for p in old)
        if new != old:
            print(f"  {g['id']}: {old} -> {new}")
            r.table("gpus").get(g["id"]).update({"profiles_enabled": new}).run(conn)
            changed += 1
    print(f"  rewrote {changed} gpu row(s)")


def _rewrite_domains_reservables_vgpus(conn):
    print("=== domains.create_dict.reservables.vgpus ===")
    changed = 0
    doms = (
        r.table("domains")
        .has_fields({"create_dict": {"reservables": {"vgpus": True}}})
        .pluck("id", "name", {"create_dict": {"reservables": {"vgpus": True}}})
        .run(conn)
    )
    for d in doms:
        old = d["create_dict"]["reservables"].get("vgpus") or []
        new = [_canon_profile(v) for v in old]
        if new != old:
            print(f"  {d['id'][:8]} {d.get('name')!r}: {old} -> {new}")
            r.table("domains").get(d["id"]).update(
                {"create_dict": {"reservables": {"vgpus": new}}}
            ).run(conn)
            changed += 1
    print(f"  rewrote {changed} domain(s)")


def _delete_unrecognised_gpu_profiles(conn):
    """Drop ``gpu_profiles`` rows whose id is not a parseable vGPU profile.

    Old discovery quirks produced ids like ``NVIDIA-Foo`` (no suffix at all)
    or ``NVIDIA-Foo1`` (trailing digit fallback) that the live discovery no
    longer emits. They never match the lookup that the engine performs and
    only clutter the admin UI. Anything matching the recognised suffix shape
    is left alone, so this is safe even if some valid id happens to have an
    unusual MODEL prefix.
    """
    print("=== gpu_profiles ghosts ===")
    deleted = 0
    for row in r.table("gpu_profiles").run(conn):
        gid = row.get("id")
        if _is_recognised(gid):
            continue
        print(f"  delete unrecognised gpu_profiles id={gid!r}")
        r.table("gpu_profiles").get(gid).delete().run(conn)
        deleted += 1
    print(f"  deleted {deleted} ghost row(s)")


def _rewrite_resource_planner(conn):
    print("=== resource_planner.subitem_id ===")
    if "resource_planner" not in r.table_list().run(conn):
        print("  (table absent — skipping)")
        return
    changed = 0
    for row in r.table("resource_planner").run(conn):
        sid = row.get("subitem_id")
        new_sid = _canon_profile(sid)
        if new_sid != sid:
            print(f"  {row.get('id', '?')[:8]}: {sid!r} -> {new_sid!r}")
            r.table("resource_planner").get(row["id"]).update(
                {"subitem_id": new_sid}
            ).run(conn)
            changed += 1
    print(f"  rewrote {changed} row(s)")


def _verify(conn):
    print("=== verification ===")
    res_bad = (
        r.table("reservables_vgpus")
        .filter(lambda x: x["id"].match(" "))
        .count()
        .run(conn)
    )
    print(f"  reservables_vgpus with spaces: {res_bad}")

    gpus_bad = (
        r.table("gpus")
        .filter(lambda g: g["profiles_enabled"].contains(lambda p: p.match(" ")))
        .count()
        .run(conn)
    )
    print(f"  gpus with spaced profiles_enabled: {gpus_bad}")

    doms_bad = (
        r.table("domains")
        .has_fields({"create_dict": {"reservables": {"vgpus": True}}})
        .filter(
            lambda d: d["create_dict"]["reservables"]["vgpus"].contains(
                lambda v: v.match(" ")
            )
        )
        .count()
        .run(conn)
    )
    print(f"  domains with spaced vgpus: {doms_bad}")


def main():
    try:
        conn = r.connect("isard-db", 28015, db="isard")
    except Exception as e:
        print(f"Error connecting to isard-db: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        _rewrite_reservables_vgpus(conn)
        _rewrite_gpus_profiles_enabled(conn)
        _rewrite_domains_reservables_vgpus(conn)
        _delete_unrecognised_gpu_profiles(conn)
        _rewrite_resource_planner(conn)
        _verify(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
