#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""CLI wrapper around :mod:`isardvdi_common.lib.usage.rollup`.

Run from a host that can reach the rethinkdb cluster (uses
``RETHINKDB_HOST`` / ``RETHINKDB_PORT`` / ``RETHINKDB_DB``, same env
convention as ``initdb/upgrade.py``).

Usage:

    python -m engine.scripts.rollup_usage_consumption \\
        --mode={backfill|incremental} [--dry-run] [--qps=10] [--confirm]

The same library is imported by apiv4's daily consolidator chain to
run the incremental tier on each day's consolidation.
"""

import argparse
import json
import logging
import os
import sys
import time

from isardvdi_common.lib.usage.retention import load_config
from isardvdi_common.lib.usage.rollup import (
    BackupWriter,
    empty_stats,
    run_backfill,
    run_incremental,
)
from rethinkdb import r

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("LOG_LEVEL", "INFO"),
)
log = logging.getLogger("rollup_usage_consumption")


def _connect():
    return r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(os.environ.get("RETHINKDB_PORT", "28015")),
        db=os.environ.get("RETHINKDB_DB", "isard"),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=("backfill", "incremental"),
        required=True,
        help="backfill = one-shot full table; incremental = daily transition windows.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--qps", type=int, default=10)
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-dry-run.",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help=(
            "Stream every source row that gets aggregated or deleted to a "
            "gzipped JSONL file under this directory before the destructive "
            "rdb write. One file per run. Required for non-dry-run unless "
            "--no-backup is given."
        ),
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help=(
            "Skip writing the source-row backup. Strongly discouraged "
            "outside of dry-run / sandbox tests — the rolled-up rows replace "
            "originals atomically and there is no automatic rollback."
        ),
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.confirm:
        log.error("non-dry-run requires --confirm. Aborting.")
        return 2
    if not args.dry_run and not args.no_backup and not args.backup_dir:
        log.error(
            "non-dry-run requires --backup-dir <path> "
            "(or --no-backup to opt out, not recommended). Aborting."
        )
        return 2

    conn = _connect()
    retention = load_config(conn)
    log.info(
        "starting rollup_usage_consumption mode=%s dry_run=%s qps=%d "
        "daily_months=%d weekly_months=%d total_months=%s",
        args.mode,
        args.dry_run,
        args.qps,
        retention.daily_months,
        retention.weekly_months,
        retention.total_months,
    )
    stats = empty_stats()
    started = time.monotonic()
    runner = run_backfill if args.mode == "backfill" else run_incremental
    backup_cm = (
        BackupWriter(args.backup_dir, args.mode)
        if args.backup_dir and not args.dry_run
        else None
    )
    try:
        if backup_cm is not None:
            with backup_cm as backup:
                runner(
                    conn,
                    retention,
                    qps=args.qps,
                    dry_run=args.dry_run,
                    stats=stats,
                    backup=backup,
                )
        else:
            runner(conn, retention, qps=args.qps, dry_run=args.dry_run, stats=stats)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    summary = {
        **stats,
        "elapsed_s": round(time.monotonic() - started, 2),
        "mode": args.mode,
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary), flush=True)
    log.info("done")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
