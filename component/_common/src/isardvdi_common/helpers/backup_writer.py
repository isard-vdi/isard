#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Streaming gzipped-JSONL backup writer.

Used by any feature that destructively rewrites or deletes rdb rows
and wants a recoverable dump of the originals before they vanish.
First adopted by the ``usage_consumption`` rollup; now also used by
``logs_desktops`` / ``logs_users`` retention deletes.

Single-file-per-run design — gzip is streaming so memory stays bounded
regardless of total volume, and a single ``.jsonl.gz`` is the right
container for a single output stream (tar.gz only buys anything when
there are many files).
"""

import gzip
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional, TextIO

log = logging.getLogger(__name__)


def _json_default(value):
    """JSON serializer for ``datetime`` (and any other awkward types)."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class BackupWriter:
    """Streams rows to ``<backup_dir>/<prefix>_<UTC-ts>.jsonl.gz``.

    The writer is a context manager so the caller can guarantee the
    file is closed (and gzip footer flushed) on the way out.

    Example::

        with BackupWriter("/var/lib/isard/backup", "logs_desktops_delete") as bk:
            bk.write_rows(rows)
        # File: /var/lib/isard/backup/logs_desktops_delete_20260503T180852Z.jsonl.gz
    """

    def __init__(self, backup_dir: str, prefix: str) -> None:
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = os.path.join(backup_dir, f"{prefix}_{ts}.jsonl.gz")
        self._fh: Optional[TextIO] = None
        self.rows_written = 0
        self.bytes_written = 0

    def __enter__(self) -> "BackupWriter":
        self._fh = gzip.open(self.path, "wt", encoding="utf-8")
        log.info("backup -> %s", self.path)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        if self.rows_written:
            try:
                self.bytes_written = os.path.getsize(self.path)
            except OSError:
                self.bytes_written = -1
            log.info(
                "backup closed: %d rows, %.1f KB compressed",
                self.rows_written,
                self.bytes_written / 1024,
            )
        return False

    def write_rows(self, rows) -> None:
        """Stream a batch of dict rows as JSON lines to the open file.

        Caller is responsible for re-fetching the rows from rdb if it
        wants the most recent state — the writer just serializes
        whatever it's handed. Datetime instances are normalised to
        ISO-8601 strings so the dump is replay-safe.
        """
        if self._fh is None:
            return
        for row in rows:
            line = json.dumps(row, default=_json_default, ensure_ascii=False)
            self._fh.write(line + "\n")
            self.rows_written += 1
