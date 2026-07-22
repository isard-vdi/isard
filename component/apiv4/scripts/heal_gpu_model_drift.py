#!/usr/bin/env python3
"""One-shot heal for ``gpus.model`` rows that drifted away from the catalog.

A card's ``gpus.model`` is the join key against ``gpu_profiles`` (and through
it ``reservables_vgpus``, ``profiles_enabled``, and any user booking that
references a reservable id). When the model derivation changed across a
hypervisor restart (driver flip vfio-pci ↔ nvidia, naming-convention update,
discovery path swap), the row's ``model`` field was overwritten while the
catalog and user state stayed under the old name. The bookings page 404s on
the lookup and the operator-curated ``profiles_enabled`` becomes a list of
ids that resolve to a different model.

This script reverts ``gpus.model`` (and the matching ``vgpus.model``) back to
the value the surrounding catalog still references. The legacy model is the
one most ``profiles_enabled`` ids parse to: ``<BRAND>-<MODEL>-<SUFFIX>``. We
trust the operator-enabled list as the source of truth — those entries
reflect the catalog the user can actually book against.

Per-card rules:
  * If ``gpus.model`` already matches a ``gpu_profiles`` row, no-op.
  * If ``profiles_enabled`` references at least one id whose ``MODEL`` token
    is present in ``gpu_profiles`` and that target row exists, revert
    ``gpus.model`` (and ``vgpus.model``) to that legacy value.
  * If no consensus model can be inferred (empty profiles_enabled, mixed
    legacy ids, no matching gpu_profiles row), leave the row untouched and
    log it for manual review.

Dry-run by default; pass ``--apply`` to commit. Idempotent.

Run inside the apiv4 container::

    docker exec -i isard-apiv4 python3 < component/apiv4/scripts/heal_gpu_model_drift.py
    # or with --apply:
    docker exec isard-apiv4 python3 /opt/isardvdi/scripts/heal_gpu_model_drift.py --apply
"""

import os
import re
import sys
from collections import Counter

from rethinkdb import r

DB_HOST = os.environ.get("RETHINKDB_HOST", "isard-db")
DB_PORT = int(os.environ.get("RETHINKDB_PORT", "28015"))
DB_NAME = os.environ.get("RETHINKDB_DB", "isard")

# Match "<BRAND>-<MODEL>-<SUFFIX>" where suffix is the trailing
# "<digit>...<class>" or "<digit>g.<digit>gb..." or "passthrough".
# We extract MODEL by stripping the brand prefix and the suffix, with brand
# from the row itself so card-specific brands work.
_SUFFIX_RE = re.compile(
    r"-(passthrough|\d+g\.\d+gb(?:[+_].+)?|\d+-\d+[ABCQ]|\d+[ABCQ])$"
)


def _model_from_reservable_id(reservable_id, brand):
    """Best-effort parse of the MODEL token from a ``BRAND-MODEL-SUFFIX`` id.

    Returns None when the shape doesn't match or the brand prefix is wrong.
    """
    if not isinstance(reservable_id, str):
        return None
    prefix = brand + "-"
    if not reservable_id.startswith(prefix):
        return None
    tail = reservable_id[len(prefix) :]
    m = _SUFFIX_RE.search(tail)
    if not m:
        return None
    return tail[: m.start()] or None


def _consensus_model(profiles_enabled, brand):
    """Pick the model token most ``profiles_enabled`` ids agree on.

    Ties or empty input return None.
    """
    candidates = [
        m
        for m in (_model_from_reservable_id(pid, brand) for pid in profiles_enabled)
        if m
    ]
    if not candidates:
        return None
    counts = Counter(candidates)
    top = counts.most_common(1)[0]
    if top[1] == 0:
        return None
    return top[0]


def _heal(conn, apply_changes):
    fixed = 0
    skipped = 0
    noop = 0
    for card in r.table("gpus").run(conn):
        cid = card["id"]
        brand = card.get("brand")
        cur_model = card.get("model")
        profiles_enabled = card.get("profiles_enabled") or []
        if not brand or not cur_model:
            print(f"  SKIP {cid!r}: missing brand or model")
            skipped += 1
            continue

        # 1) Already healthy?
        cur_match = list(
            r.table("gpu_profiles")
            .get_all([brand, cur_model], index="brand-model")
            .run(conn)
        )
        if cur_match:
            print(f"  OK   {cid!r} model={cur_model!r} (gpu_profiles row exists)")
            noop += 1
            continue

        # 2) Find a target model from profiles_enabled.
        target = _consensus_model(profiles_enabled, brand)
        if not target:
            print(
                f"  SKIP {cid!r} model={cur_model!r}: no consensus from "
                f"profiles_enabled={profiles_enabled!r}; manual review needed"
            )
            skipped += 1
            continue
        if target == cur_model:
            # consensus model equals current but no gpu_profiles row exists
            # for it: catalog itself is missing, not a drift problem
            print(
                f"  SKIP {cid!r} model={cur_model!r}: consensus matches but "
                f"no gpu_profiles row exists for ({brand!r}, {target!r})"
            )
            skipped += 1
            continue

        target_match = list(
            r.table("gpu_profiles")
            .get_all([brand, target], index="brand-model")
            .run(conn)
        )
        if not target_match:
            print(
                f"  SKIP {cid!r}: consensus target=({brand!r}, {target!r}) has "
                f"no gpu_profiles row; refusing to set a model that wouldn't "
                f"resolve either"
            )
            skipped += 1
            continue

        physical_device = card.get("physical_device")
        print(
            f"  HEAL {cid!r}: model {cur_model!r} -> {target!r} "
            f"(profiles_enabled refs {len(profiles_enabled)} id(s); "
            f"target gpu_profiles row exists)"
        )
        fixed += 1
        if not apply_changes:
            continue

        r.table("gpus").get(cid).update({"model": target}).run(conn)
        if physical_device:
            r.table("vgpus").get(physical_device).update(
                {"model": target, "info": {"model": target}}
            ).run(conn)

    return fixed, skipped, noop


def main():
    apply_changes = "--apply" in sys.argv[1:]
    conn = r.connect(host=DB_HOST, port=DB_PORT, db=DB_NAME)
    try:
        mode = "APPLY" if apply_changes else "DRY-RUN"
        print(f"=== heal_gpu_model_drift [{mode}] ===")
        fixed, skipped, noop = _heal(conn, apply_changes)
        print(
            f"=== summary: heal={fixed} skip={skipped} noop={noop} "
            f"(use --apply to commit)" + ("" if apply_changes else "")
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
