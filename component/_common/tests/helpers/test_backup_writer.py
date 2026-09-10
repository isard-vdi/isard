#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``isardvdi_common.helpers.backup_writer``.

Pins:

* gzipped JSONL output written under ``<dir>/<prefix>_<UTC-ts>.jsonl.gz``.
* Datetime instances ISO-encode (replay-safe).
* Empty-rows path leaves a valid (tiny) gzip header so downstream
  tooling can still ``gzip -d`` the artifact.
* Streaming append: multiple ``write_rows`` calls all land in the file.
"""

import gzip
import json
from datetime import datetime, timezone

from isardvdi_common.helpers.backup_writer import BackupWriter


class TestBackupWriter:
    def test_writes_jsonl_gz_with_streaming(self, tmp_path):
        rows = [
            {
                "pk": "p1",
                "date": datetime(2025, 9, 1, tzinfo=timezone.utc),
                "item_id": "i1",
                "inc": {"x": 1.5},
            },
            {
                "pk": "p2",
                "date": datetime(2025, 9, 2, tzinfo=timezone.utc),
                "item_id": "i2",
                "inc": {"x": 2},
            },
        ]
        with BackupWriter(str(tmp_path), "logs_desktops_delete") as backup:
            backup.write_rows(rows)
            assert backup.rows_written == 2

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name.startswith("logs_desktops_delete_")
        assert files[0].name.endswith(".jsonl.gz")
        with gzip.open(files[0], "rt", encoding="utf-8") as fh:
            lines = fh.read().strip().split("\n")
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["pk"] == "p1"
        # Datetime → ISO string so the dump is replay-safe.
        assert first["date"] == "2025-09-01T00:00:00+00:00"

    def test_appends_across_multiple_write_rows_calls(self, tmp_path):
        with BackupWriter(str(tmp_path), "rollup_backfill") as backup:
            backup.write_rows([{"a": 1}])
            backup.write_rows([{"a": 2}, {"a": 3}])
            assert backup.rows_written == 3

        files = list(tmp_path.iterdir())
        with gzip.open(files[0], "rt", encoding="utf-8") as fh:
            lines = fh.read().strip().split("\n")
        assert [json.loads(line)["a"] for line in lines] == [1, 2, 3]

    def test_no_rows_still_creates_readable_gzip(self, tmp_path):
        with BackupWriter(str(tmp_path), "logs_users_delete") as backup:
            assert backup.rows_written == 0

        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].name.endswith(".jsonl.gz")
        # Tiny — just the gzip header — but valid.
        assert files[0].stat().st_size < 100
        with gzip.open(files[0], "rt", encoding="utf-8") as fh:
            assert fh.read() == ""

    def test_filename_includes_utc_timestamp(self, tmp_path):
        with BackupWriter(str(tmp_path), "demo") as backup:
            pass
        name = backup.path.split("/")[-1]
        # Format: demo_YYYYMMDDTHHMMSSZ.jsonl.gz
        assert name.startswith("demo_") and name.endswith("Z.jsonl.gz")

    def test_creates_backup_dir_if_missing(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        # Dir doesn't exist yet; writer must create it.
        with BackupWriter(str(nested), "test") as backup:
            backup.write_rows([{"x": 1}])
        assert nested.exists()
        assert backup.rows_written == 1

    def test_non_serializable_values_are_str_coerced(self, tmp_path):
        class Custom:
            def __str__(self):
                return "custom-object"

        with BackupWriter(str(tmp_path), "demo") as backup:
            backup.write_rows([{"x": Custom()}])

        files = list(tmp_path.iterdir())
        with gzip.open(files[0], "rt", encoding="utf-8") as fh:
            (line,) = fh.read().strip().split("\n")
        assert json.loads(line) == {"x": "custom-object"}
