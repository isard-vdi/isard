"""The redis dump must authenticate, keep the previous dump and refuse an empty one."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "32-redis-dump.sh"

# Fake redis-cli driven entirely by env, so there is no nested-quote rendering.
FAKE = """#!/bin/sh
echo "${REDISCLI_AUTH-}" > "$FAKE_AUTHFILE"
t=""; prev=""
for a in "$@"; do [ "$prev" = "--rdb" ] && t="$a"; prev="$a"; done
if [ "$FAKE_RC" -eq 0 ] && [ -n "$t" ]; then
    case "$FAKE_PRODUCES" in
        full) printf 'RDBDATA' > "$t" ;;
        empty) : > "$t" ;;
    esac
fi
exit "$FAKE_RC"
"""

SETUP_ENV = {
    "my_empty_variable": "",
    "REDIS_HOST": "isard-redis",
    "REDIS_PORT": "6379",
    "BACKUP_REDIS_WHEN": "everyday at 01:00",
}


def _run(tmp_path, envsubst, *, rc, produces, password="", preexisting=False):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "redis-cli").write_text(FAKE)
    (bindir / "redis-cli").chmod(0o755)

    dumpdir = tmp_path / "redisdump"
    dumpdir.mkdir()
    if preexisting:
        (dumpdir / "dump-OLD.rdb").write_text("previous-good-dump")

    rendered = tmp_path / "32.sh"
    rendered.write_text(envsubst(JOB.read_text(), SETUP_ENV))
    authfile = tmp_path / "auth"

    r = subprocess.run(
        ["sh", str(rendered)],
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "REDISDUMP_DIR": str(dumpdir),
            "REDIS_PASSWORD": password,
            "FAKE_RC": str(rc),
            "FAKE_PRODUCES": produces,
            "FAKE_AUTHFILE": str(authfile),
            "LOG_FILE": str(tmp_path / "log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    dumps = sorted(p.name for p in dumpdir.glob("dump*.rdb"))
    auth = authfile.read_text().strip() if authfile.exists() else None
    return r, dumps, auth


def _fatal(stdout):
    return any(line.startswith("Fatal: ") for line in stdout.splitlines())


def test_uses_rediscli_auth_when_password_set(tmp_path, envsubst):
    _, _, auth = _run(tmp_path, envsubst, rc=0, produces="full", password="s3cret")
    assert auth == "s3cret"


def test_no_auth_env_when_no_password(tmp_path, envsubst):
    _, _, auth = _run(tmp_path, envsubst, rc=0, produces="full", password="")
    assert auth == ""


def test_success_keeps_only_the_new_dump(tmp_path, envsubst):
    r, dumps, _ = _run(
        tmp_path, envsubst, rc=0, produces="full", password="x", preexisting=True
    )
    assert r.returncode == 0
    assert not _fatal(r.stdout)
    assert dumps and "dump-OLD.rdb" not in dumps
    assert len(dumps) == 1


def test_failure_keeps_previous_dump_and_is_fatal(tmp_path, envsubst):
    r, dumps, _ = _run(
        tmp_path, envsubst, rc=1, produces="full", password="x", preexisting=True
    )
    assert _fatal(r.stdout)
    assert r.returncode != 0
    assert dumps == ["dump-OLD.rdb"]  # previous dump NOT deleted


def test_empty_dump_is_fatal_and_keeps_previous(tmp_path, envsubst):
    r, dumps, _ = _run(
        tmp_path, envsubst, rc=0, produces="empty", password="x", preexisting=True
    )
    assert _fatal(r.stdout)
    assert r.returncode != 0
    assert dumps == ["dump-OLD.rdb"]  # empty dump discarded, previous kept
