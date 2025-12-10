#!/usr/bin/env python3
"""
Script to find and stop stale domains that have been in "Started" status
for longer than a specified time threshold.

Usage:
    cleanup_stale_domains.py --minutes <N>
    cleanup_stale_domains.py --minutes <N> --dry-run

Options:
    --minutes N    Find domains started more than N minutes ago (required)
    --dry-run      Only show what would be done, don't prompt for action
"""

import argparse
import random
import sys
import time
from datetime import datetime

from rethinkdb import r


def format_timestamp(ts):
    """Convert Unix timestamp to human-readable format."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def format_age(ts):
    """Format age from timestamp to human-readable string."""
    age_seconds = int(time.time()) - ts
    if age_seconds < 60:
        return f"{age_seconds}s ago"
    elif age_seconds < 3600:
        return f"{age_seconds // 60}m ago"
    else:
        hours = age_seconds // 3600
        minutes = (age_seconds % 3600) // 60
        return f"{hours}h {minutes}m ago"


def check_inconsistencies(domains):
    """
    Check for inconsistencies between server and server_autostart fields.
    Returns list of domains with issues (server_autostart=True but server=False).
    """
    inconsistent = []
    for d in domains:
        server = d.get("server", False)
        server_autostart = d.get("server_autostart", False)
        if server_autostart and not server:
            inconsistent.append(d)
    return inconsistent


def filter_server_domains(domains):
    """
    Separate domains into:
    - actionable: non-server domains (server=False or absent)
    - servers: server domains to be skipped (server=True or server_autostart=True)
    """
    actionable = []
    servers = []
    for d in domains:
        if d.get("server", False) or d.get("server_autostart", False):
            servers.append(d)
        else:
            actionable.append(d)
    return actionable, servers


def get_stale_domains(minutes):
    """Query domains that have been Started for more than N minutes."""
    threshold = int(time.time()) - (minutes * 60)
    stale_domains = list(
        r.db("isard")
        .table("domains")
        .get_all(["desktop", "Started"], index="kind_status")
        .filter(lambda d: d["accessed"] < threshold)
        .order_by("accessed")
        .pluck("id", "accessed", "name", "server", "server_autostart")
        .run()
    )
    return stale_domains


def update_domain_status(domain_id, target_status):
    """
    Atomically update domain status only if still Started.
    Returns True if updated, False if skipped (status already changed).
    """
    result = (
        r.db("isard")
        .table("domains")
        .get(domain_id)
        .update(
            lambda row: r.branch(
                row["status"].match("Started"),
                {"status": target_status, "accessed": int(time.time())},
                {},
            ),
            return_changes=True,
        )
        .run()
    )
    return bool(result.get("changes"))


def main():
    parser = argparse.ArgumentParser(
        description="Find and stop stale domains that have been Started too long."
    )
    parser.add_argument(
        "--minutes",
        type=int,
        required=True,
        help="Find domains started more than N minutes ago",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be done, don't prompt for action",
    )
    args = parser.parse_args()

    if args.minutes < 1:
        print("Error: --minutes must be at least 1")
        sys.exit(1)

    print("Connecting to RethinkDB...")
    try:
        r.connect("isard-db", 28015).repl()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

    print(f"Querying domains started more than {args.minutes} minutes ago...")
    stale_domains = get_stale_domains(args.minutes)

    if not stale_domains:
        print("No stale domains found.")
        sys.exit(0)

    print(
        f"\nFound {len(stale_domains)} domains started more than {args.minutes} minutes ago."
    )

    # Check for inconsistencies in server fields
    inconsistent = check_inconsistencies(stale_domains)
    if inconsistent:
        print(
            f"\nWARNING: Found {len(inconsistent)} domains with inconsistent server fields:"
        )
        print("  (server_autostart=True but server=False)")
        for d in inconsistent:
            print(f"    {d['id']}")
        print("  These will be SKIPPED from any action.")

    # Filter out server domains
    actionable, servers = filter_server_domains(stale_domains)
    if servers:
        print(
            f"\nSkipping {len(servers)} server domains (server=True or server_autostart=True)"
        )

    if not actionable:
        print("\nNo actionable domains remaining after filtering.")
        sys.exit(0)

    # Show oldest/newest from actionable domains only
    oldest = actionable[0]
    newest = actionable[-1]

    print(f"\nOldest: {oldest['id']}")
    print(f"        Name: {oldest.get('name', 'N/A')}")
    print(
        f"        Started: {format_timestamp(oldest['accessed'])} ({format_age(oldest['accessed'])})"
    )
    print()
    print(f"Newest: {newest['id']}")
    print(f"        Name: {newest.get('name', 'N/A')}")
    print(
        f"        Started: {format_timestamp(newest['accessed'])} ({format_age(newest['accessed'])})"
    )
    print()
    print(f"{len(actionable)} domains available for action.")

    if args.dry_run:
        print("\nDry run mode - no changes will be made.")
        print("\nDomain IDs that would be affected:")
        for d in actionable:
            print(f"  {d['id']} ({format_age(d['accessed'])})")
        sys.exit(0)

    print("\nActions:")
    print("  [s] Set all to Shutting-down (graceful)")
    print("  [f] Set all to Stopping (force)")
    print("  [q] Quit without changes")
    print()

    while True:
        choice = input("Choice: ").strip().lower()
        if choice in ["s", "f", "q"]:
            break
        print("Invalid choice. Please enter 's', 'f', or 'q'.")

    if choice == "q":
        print("Aborted.")
        sys.exit(0)

    target_status = "Shutting-down" if choice == "s" else "Stopping"
    total = len(actionable)
    updated = 0
    skipped = 0

    print(f"\nProcessing {total} domains (setting to {target_status})...")

    for i, domain in enumerate(actionable, 1):
        domain_id = domain["id"]
        success = update_domain_status(domain_id, target_status)

        if success:
            print(f"[{i}/{total}] {domain_id}: {target_status} ✓")
            updated += 1
        else:
            print(f"[{i}/{total}] {domain_id}: skipped (status changed)")
            skipped += 1

        if i < total:
            sleep_time = 0.5 + random.uniform(-0.25, 0.25)
            time.sleep(sleep_time)

    print(f"\nComplete: {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    main()
