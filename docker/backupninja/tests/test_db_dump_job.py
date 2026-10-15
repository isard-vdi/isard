"""The db dump must keep the previous dump and refuse an empty one."""

import os
import pathlib
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "22-db-dump.sh"

FAKE = """#!/bin/sh
t=""; prev=""
for a in "$@"; do [ "$prev" = "-f" ] && t="$a"; prev="$a"; done
if [ "$FAKE_RC" -eq 0 ] && [ -n "$t" ]; then
    case "$FAKE_PRODUCES" in
        full) printf 'DBDATA' > "$t" ;;
        empty) : > "$t" ;;
    esac
fi
exit "$FAKE_RC"
"""

SETUP_ENV = {
    "my_empty_variable": "",
    "RETHINKDB_HOST": "isard-db",
    "RETHINKDB_PORT": "28015",
    "BACKUP_DB_WHEN": "everyday at 01:00",
    # PATH is a runtime ref in the job and must survive envsubst
}


def _run(tmp_path, envsubst, *, rc, produces, preexisting=False):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "rethinkdb-dump").write_text(FAKE)
    (bindir / "rethinkdb-dump").chmod(0o755)

    dumpdir = tmp_path / "dbdump"
    dumpdir.mkdir()
    if preexisting:
        (dumpdir / "isard-db-OLD.tar.gz").write_text("previous-good-dump")

    rendered = tmp_path / "22.sh"
    rendered.write_text(envsubst(JOB.read_text(), SETUP_ENV))

    r = subprocess.run(
        ["sh", str(rendered)],
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "DBDUMP_DIR": str(dumpdir),
            "FAKE_RC": str(rc),
            "FAKE_PRODUCES": produces,
            "LOG_FILE": str(tmp_path / "log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    dumps = sorted(p.name for p in dumpdir.glob("isard-db*.tar.gz"))
    return r, dumps


def _fatal(stdout):
    return any(line.startswith("Fatal: ") for line in stdout.splitlines())


def test_success_keeps_only_the_new_dump(tmp_path, envsubst):
    r, dumps = _run(tmp_path, envsubst, rc=0, produces="full", preexisting=True)
    assert r.returncode == 0
    assert not _fatal(r.stdout)
    assert dumps and "isard-db-OLD.tar.gz" not in dumps
    assert len(dumps) == 1


def test_failure_keeps_previous_dump_and_is_fatal(tmp_path, envsubst):
    r, dumps = _run(tmp_path, envsubst, rc=1, produces="full", preexisting=True)
    assert _fatal(r.stdout)
    assert r.returncode != 0
    assert dumps == ["isard-db-OLD.tar.gz"]


def test_empty_dump_is_fatal_and_keeps_previous(tmp_path, envsubst):
    r, dumps = _run(tmp_path, envsubst, rc=0, produces="empty", preexisting=True)
    assert _fatal(r.stdout)
    assert r.returncode != 0
    assert dumps == ["isard-db-OLD.tar.gz"]
