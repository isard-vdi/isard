#!/usr/bin/env python3
"""One-shot heal for references to vGPU cards and profiles that no longer exist.

An install whose GPU cards were re-created under new ids is left with
``resource_planner`` rows, bookings and domains pointing at ids that are not in
``gpus`` / ``reservables_vgpus`` any more.

The sweep is safe because a ``gpus`` row is only ever removed by a deliberate
delete: a hypervisor going down clears ``physical_device`` and keeps the row, so
a missing card id means the card is gone and not that a host is off.

Planner rows and their bookings go with ``--apply``. Domains and deployments
carry what a user asked for, so resetting them to no-GPU needs the second,
explicit ``--include-desktops``.

Dry-run by default. Idempotent. Run inside the apiv4 container::

    docker exec isard-apiv4 python3 /tmp/heal_orphan_vgpu_references.py --apply
"""

import argparse
import os
import sys
from collections import defaultdict

from isardvdi_common.lib.bookings.reservables import Reservables
from isardvdi_common.lib.bookings.reservables_planner import ReservablesPlannerProccess
from rethinkdb import RethinkDB

r = RethinkDB()

DB_HOST = os.environ.get("RETHINKDB_HOST", "isard-db")
DB_PORT = int(os.environ.get("RETHINKDB_PORT", "28015"))
DB_NAME = os.environ.get("RETHINKDB_DB", "isard")


def _live(conn):
    cards = {g["id"] for g in r.table("gpus").pluck("id").run(conn)}
    profiles = {p["id"] for p in r.table("reservables_vgpus").pluck("id").run(conn)}
    return cards, profiles


def _orphan_plans(conn, cards, profiles):
    """(card, profile) pairs whose planner rows point at something gone."""
    pairs = defaultdict(int)
    for plan in (
        r.table("resource_planner")
        .filter({"item_type": "gpus"})
        .pluck("id", "item_id", "subitem_id")
        .run(conn)
    ):
        card, profile = plan.get("item_id"), plan.get("subitem_id")
        if card not in cards or profile not in profiles:
            pairs[(card, profile)] += 1
    return pairs


def _orphan_domain_profiles(conn, profiles):
    """Profiles referenced by a domain that are not in the catalog."""
    counts = defaultdict(int)
    for dom in (
        r.table("domains")
        .has_fields({"create_dict": {"reservables": True}})
        .pluck("id", {"create_dict": {"reservables": True}})
        .run(conn)
    ):
        vgpus = ((dom.get("create_dict") or {}).get("reservables") or {}).get("vgpus")
        for ref in vgpus if isinstance(vgpus, list) else []:
            if ref and ref != "None" and ref not in profiles:
                counts[ref] += 1
    return counts


def _orphan_deployments(conn, profiles):
    counts = defaultdict(list)
    for dep in r.table("deployments").pluck("id", "create_dict").run(conn):
        create = dep.get("create_dict")
        create = create if isinstance(create, dict) else {}
        vgpus = (create.get("reservables") or {}).get("vgpus")
        for ref in vgpus if isinstance(vgpus, list) else []:
            if ref and ref != "None" and ref not in profiles:
                counts[ref].append(dep["id"])
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the changes")
    parser.add_argument(
        "--include-desktops",
        action="store_true",
        help="also reset desktops and deployments holding a missing profile",
    )
    args = parser.parse_args()
    mode = "APPLY" if args.apply else "DRY-RUN"

    conn = r.connect(host=DB_HOST, port=DB_PORT, db=DB_NAME)
    try:
        cards, profiles = _live(conn)
        plans = _orphan_plans(conn, cards, profiles)
        domains = _orphan_domain_profiles(conn, profiles)
        deployments = _orphan_deployments(conn, profiles)

        print(f"=== heal_orphan_vgpu_references [{mode}] ===")
        print(f"live: {len(cards)} card(s), {len(profiles)} profile(s)")

        for (card, profile), rows in sorted(plans.items(), key=lambda kv: str(kv[0])):
            why = "card gone" if card not in cards else "profile gone"
            print(f"  plans  {rows:3d} row(s)  {card} / {profile}  ({why})")
        for profile, n in sorted(domains.items()):
            print(f"  domains{n:4d}          -> {profile}")
        for profile, ids in sorted(deployments.items()):
            print(f"  deploys{len(ids):4d}          -> {profile}")

        if args.apply:
            for card, profile in plans:
                deleted_plans, deleted_bookings = (
                    ReservablesPlannerProccess.delete_card_subitem_plans(card, profile)
                )
                print(
                    f"  swept {deleted_plans} plan(s) and {deleted_bookings} "
                    f"booking(s) for {card} / {profile}"
                )
            if args.include_desktops:
                reservables = Reservables()
                for profile in domains:
                    reservables.deassign_desktops_with_gpu("gpus", profile, None)
                    print(f"  reset desktops holding {profile}")
                for profile, ids in deployments.items():
                    reservables.deassign_deployments_with_gpu("gpus", profile, ids)
                    print(f"  reset {len(ids)} deployment(s) holding {profile}")
            elif domains or deployments:
                print("  desktops/deployments left alone (--include-desktops to reset)")

        print(
            f"=== summary: {sum(plans.values())} planner row(s) in {len(plans)} "
            f"pair(s), {sum(domains.values())} domain(s), "
            f"{sum(len(v) for v in deployments.values())} deployment(s)"
            + ("" if args.apply else " -- use --apply to commit")
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
