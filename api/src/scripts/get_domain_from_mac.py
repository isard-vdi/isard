#!/usr/bin/env python3
#
# Copyright 2026 the IsardVDI project authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Script to get domain info from a MAC address.

MAC addresses in IsardVDI domains are stored in:
    domain.create_dict.hardware.interfaces = [{"id": "interface_id", "mac": "52:54:00:xx:xx:xx"}, ...]

This script queries the domains table to find a domain by its MAC address.

Usage:
    python get_domain_from_mac.py <mac_address>
    python get_domain_from_mac.py 52:54:00:12:34:56
    python get_domain_from_mac.py 52:54:00:12:34:56 --json
    python get_domain_from_mac.py 52:54:00:12:34:56 --full

Options:
    --json      Output as JSON
    --full      Show full domain document (default shows summary)
    --all       Show all domains with their MAC addresses

Environment variables:
    RETHINKDB_HOST  RethinkDB host (default: isard-db)
    RETHINKDB_PORT  RethinkDB port (default: 28015)
    RETHINKDB_DB    RethinkDB database (default: isard)
"""

import json
import os
import sys

from rethinkdb import r


def get_db_connection():
    """Get RethinkDB connection using environment variables or defaults."""
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", 28015))
    db = os.environ.get("RETHINKDB_DB", "isard")
    return r.connect(host, port, db)


def normalize_mac(mac):
    """Normalize MAC address format to lowercase with colons."""
    mac = mac.lower().replace("-", ":").replace(".", ":")
    # Handle format like 5254.0012.3456
    if len(mac) == 14 and mac.count(":") == 2:
        mac = ":".join([mac[i : i + 2] for i in range(0, 12, 2)])
    return mac


def get_domain_by_mac(conn, mac):
    """
    Find a domain by MAC address.

    Searches in domain.create_dict.hardware.interfaces for matching MAC.
    Returns the domain document or None if not found.
    """
    mac = normalize_mac(mac)

    # Query domains where any interface has the matching MAC
    domains = list(
        r.table("domains")
        .filter(
            lambda domain: domain["create_dict"]["hardware"]["interfaces"].contains(
                lambda iface: iface["mac"].downcase() == mac
            )
        )
        .run(conn)
    )

    if len(domains) == 0:
        return None
    if len(domains) == 1:
        return domains[0]

    # Multiple domains found (shouldn't happen, but return first)
    print(f"Warning: Found {len(domains)} domains with MAC {mac}", file=sys.stderr)
    return domains[0]


def get_domain_summary(domain):
    """Get a summary of relevant domain fields."""
    if not domain:
        return None

    interfaces = domain.get("create_dict", {}).get("hardware", {}).get("interfaces", [])
    interfaces_summary = [
        {"id": iface.get("id"), "mac": iface.get("mac")} for iface in interfaces
    ]

    return {
        "id": domain.get("id"),
        "name": domain.get("name"),
        "status": domain.get("status"),
        "kind": domain.get("kind"),
        "user": domain.get("user"),
        "category": domain.get("category"),
        "group": domain.get("group"),
        "hyp_started": domain.get("hyp_started"),
        "viewer": {
            "guest_ip": domain.get("viewer", {}).get("guest_ip"),
            "tls": domain.get("viewer", {}).get("tls"),
        },
        "interfaces": interfaces_summary,
        "server": domain.get("server"),
        "tag": domain.get("tag"),
        "persistent": domain.get("persistent"),
    }


def get_all_domains_macs(conn):
    """Get all domains with their MAC addresses."""
    domains = list(
        r.table("domains")
        .filter(
            lambda domain: domain["create_dict"]["hardware"]["interfaces"].count() > 0
        )
        .pluck(
            "id",
            "name",
            "status",
            "user",
            {"create_dict": {"hardware": {"interfaces": True}}},
        )
        .run(conn)
    )

    result = []
    for domain in domains:
        interfaces = (
            domain.get("create_dict", {}).get("hardware", {}).get("interfaces", [])
        )
        for iface in interfaces:
            result.append(
                {
                    "domain_id": domain.get("id"),
                    "domain_name": domain.get("name"),
                    "domain_status": domain.get("status"),
                    "user": domain.get("user"),
                    "interface_id": iface.get("id"),
                    "mac": iface.get("mac"),
                }
            )
    return result


def print_domain_info(domain, as_json=False, full=False):
    """Print domain information."""
    if not domain:
        print("Domain not found")
        return

    if as_json:
        if full:
            print(json.dumps(domain, indent=2, default=str))
        else:
            print(json.dumps(get_domain_summary(domain), indent=2, default=str))
        return

    summary = get_domain_summary(domain)

    print(f"\n{'='*60}")
    print(f"Domain found:")
    print(f"{'='*60}")
    print(f"  ID:          {summary['id']}")
    print(f"  Name:        {summary['name']}")
    print(f"  Status:      {summary['status']}")
    print(f"  Kind:        {summary['kind']}")
    print(f"  User:        {summary['user']}")
    print(f"  Category:    {summary['category']}")
    print(f"  Group:       {summary['group']}")
    print(f"  Hypervisor:  {summary['hyp_started'] or 'Not started'}")
    print(f"  Guest IP:    {summary['viewer']['guest_ip'] or 'Not assigned'}")
    print(f"  Server:      {summary['server']}")
    print(f"  Persistent:  {summary['persistent']}")
    print(f"  Tag:         {summary['tag'] or 'None'}")
    print(f"\n  Interfaces:")
    for iface in summary["interfaces"]:
        print(f"    - {iface['id']}: {iface['mac']}")
    print(f"{'='*60}\n")


def print_all_macs(conn, as_json=False):
    """Print all domains with their MAC addresses."""
    all_macs = get_all_domains_macs(conn)

    if as_json:
        print(json.dumps(all_macs, indent=2))
        return

    print(f"\n{'='*80}")
    print(f"All domains with MAC addresses:")
    print(f"{'='*80}")
    print(f"{'MAC':<20} {'Interface':<15} {'Domain ID':<40} {'Status':<10}")
    print(f"{'-'*20} {'-'*15} {'-'*40} {'-'*10}")
    for entry in all_macs:
        print(
            f"{entry['mac']:<20} {entry['interface_id']:<15} {entry['domain_id']:<40} {entry['domain_status']:<10}"
        )
    print(f"{'='*80}")
    print(f"Total: {len(all_macs)} interfaces\n")


def main():
    as_json = "--json" in sys.argv
    full = "--full" in sys.argv
    show_all = "--all" in sys.argv

    # Remove flags from argv
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]

    if len(args) == 0 and not show_all:
        print(__doc__)
        sys.exit(1)

    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"Error connecting to database: {e}", file=sys.stderr)
        sys.exit(1)

    if show_all:
        print_all_macs(conn, as_json)
        conn.close()
        sys.exit(0)

    mac = args[0]
    domain = get_domain_by_mac(conn, mac)

    if domain is None:
        print(f"No domain found with MAC address: {mac}")
        conn.close()
        sys.exit(1)

    print_domain_info(domain, as_json, full)
    conn.close()


if __name__ == "__main__":
    main()
