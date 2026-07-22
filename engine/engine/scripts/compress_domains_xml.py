#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Offline migration: compress legacy plain-string ``domains.xml``
values to zstd-encoded RethinkDB binary in place.

Run from a host that can reach the rethinkdb cluster (uses
``RETHINKDB_HOST`` / ``RETHINKDB_PORT`` / ``RETHINKDB_DB`` env vars,
same convention as ``initdb/upgrade.py``).

The update is atomic per row via ``r.branch(type_of == "STRING", ...,
{})`` so a concurrent writer that has already converted the row turns
each call into a no-op. The script is therefore safe to interrupt and
re-run.

Usage:

    python -m engine.scripts.compress_domains_xml [--dry-run]
        [--batch=200] [--qps=20] [--confirm]

Stats are printed periodically and as a final JSON line on stdout.
"""

import argparse
import json
import logging
import os
import sys
import time

import zstandard as zstd
from rethinkdb import r

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=os.environ.get("LOG_LEVEL", "INFO"),
)
log = logging.getLogger("compress_domains_xml")

# Match the helper's defaults so the script and runtime are aligned.
ZSTD_LEVEL = int(os.environ.get("ISARD_XML_ZSTD_LEVEL", "3"))
MIN_BYTES = int(os.environ.get("ISARD_XML_ZSTD_MIN_BYTES", "512"))


def _connect():
    return r.connect(
        host=os.environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(os.environ.get("RETHINKDB_PORT", "28015")),
        db=os.environ.get("RETHINKDB_DB", "isard"),
    )


class _TokenBucket:
    """Per-thread token bucket for rate-limiting writes.

    ``qps`` operations per second, refilled continuously. Single
    consumer, no lock — the migration is single-threaded.
    """

    def __init__(self, qps: int):
        self.rate = max(1, qps)
        self.capacity = float(self.rate)
        self.tokens = float(self.rate)
        self.last = time.monotonic()

    def take(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens < 1.0:
            sleep_for = (1.0 - self.tokens) / self.rate
            time.sleep(sleep_for)
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


def _compress(text: str) -> bytes:
    return zstd.ZstdCompressor(level=ZSTD_LEVEL).compress(text.encode("utf-8"))


def _process_row(conn, row, *, dry_run: bool, stats: dict, bucket: _TokenBucket):
    domain_id = row["id"]
    fetched = r.table("domains").get(domain_id).pluck("xml").run(conn) or {}
    xml = fetched.get("xml")
    if xml is None:
        stats["skipped_none"] += 1
        return
    if not isinstance(xml, str):
        # Already binary (or some other unexpected non-str type)
        stats["skipped_already"] += 1
        return
    encoded_len = len(xml.encode("utf-8"))
    if encoded_len < MIN_BYTES:
        stats["skipped_short"] += 1
        return

    stats["bytes_before"] += encoded_len
    if dry_run:
        # Estimate compressed size for the final report so admins
        # can decide whether to run the real pass.
        stats["bytes_after"] += len(_compress(xml))
        stats["compressed"] += 1
        return

    compressed = _compress(xml)
    bucket.take()
    try:
        result = (
            r.table("domains")
            .get(domain_id)
            .update(
                lambda doc: r.branch(
                    doc["xml"].type_of().eq("STRING"),
                    {"xml": r.binary(compressed)},
                    {},
                )
            )
            .run(conn)
        )
    except Exception as exc:  # noqa: BLE001 — migration tolerates rdb hiccups
        log.warning("update failed for %s: %s", domain_id, str(exc)[:200])
        stats["errors"] += 1
        return

    if result.get("replaced", 0):
        stats["compressed"] += 1
        stats["bytes_after"] += len(compressed)
    elif result.get("unchanged", 0):
        # r.branch returned the no-op object — another writer beat us
        stats["skipped_already"] += 1
    else:
        stats["errors"] += 1
        log.warning("unexpected update result for %s: %s", domain_id, result)


def _print_progress(stats: dict, started: float) -> None:
    elapsed = max(1e-6, time.monotonic() - started)
    rate = stats["scanned"] / elapsed
    log.info(
        "scanned=%d compressed=%d skipped_short=%d skipped_already=%d "
        "skipped_none=%d errors=%d (%.0f rows/s)",
        stats["scanned"],
        stats["compressed"],
        stats["skipped_short"],
        stats["skipped_already"],
        stats["skipped_none"],
        stats["errors"],
        rate,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n", 1)[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write — only report projected savings.",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=200,
        help="ID-stream cursor batch size (default: 200).",
    )
    parser.add_argument(
        "--qps",
        type=int,
        default=20,
        help="Max writes per second (default: 20).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required for non-dry-run.",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.confirm:
        log.error("non-dry-run requires --confirm. Aborting.")
        return 2

    conn = _connect()
    log.info(
        "starting compress_domains_xml dry_run=%s qps=%d batch=%d level=%d threshold=%d",
        args.dry_run,
        args.qps,
        args.batch,
        ZSTD_LEVEL,
        MIN_BYTES,
    )
    bucket = _TokenBucket(args.qps)
    stats = {
        "scanned": 0,
        "compressed": 0,
        "skipped_short": 0,
        "skipped_already": 0,
        "skipped_none": 0,
        "errors": 0,
        "bytes_before": 0,
        "bytes_after": 0,
    }
    started = time.monotonic()
    last_progress = started
    try:
        cursor = (
            r.table("domains")
            .has_fields("xml")
            .pluck("id")
            .run(conn, array_limit=10_000_000)
        )
        for row in cursor:
            stats["scanned"] += 1
            _process_row(conn, row, dry_run=args.dry_run, stats=stats, bucket=bucket)
            now = time.monotonic()
            if now - last_progress >= 5.0:
                _print_progress(stats, started)
                last_progress = now
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    elapsed = time.monotonic() - started
    summary = {
        **stats,
        "elapsed_s": round(elapsed, 2),
        "ratio": (
            round(stats["bytes_before"] / stats["bytes_after"], 2)
            if stats["bytes_after"]
            else None
        ),
        "saved_mb": round(
            (stats["bytes_before"] - stats["bytes_after"]) / 1_000_000, 2
        ),
        "dry_run": args.dry_run,
    }
    print(json.dumps(summary), flush=True)
    log.info("done")
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
