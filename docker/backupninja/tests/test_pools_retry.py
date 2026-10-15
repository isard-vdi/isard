"""The pools job retries files borg skipped and warns per file still unreadable."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "87-pools-borg.sh"

FAKE_BORG = """#!/bin/sh
{ echo CALL; for a in "$@"; do printf '%s\\n' "$a"; done; } >> "$ARGV"
arch=""
for a in "$@"; do case "$a" in *::*) arch="$a" ;; esac; done
case "$1" in
  create)
    case "$arch" in
      *-retry) [ "$FAKE_RETRY_OK" = "1" ] && exit 0 ;;
    esac
    printf "%s: open: [Errno 11] Resource temporarily unavailable: '%s'\\n" "$FAKE_SKIP" "$FAKE_SKIP"
    exit 1 ;;
  *) exit 0 ;;
esac
"""


def _exe(path, body):
    path.write_text(body if body.startswith("#!") else "#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, *, retry_ok):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    disk = pool / "disk.qcow2"
    disk.write_bytes(b"x")

    _exe(bindir / "isardvdi-backup-pool-paths", f'printf "%s\\n" "{pool}"\n')
    _exe(bindir / "flock", "exit 0\n")
    _exe(bindir / "borg", FAKE_BORG)
    argv = tmp_path / "argv"

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BACKUP_POOLS_NICE": "env",
        "BACKUP_POOLS_PRUNE": "",
        "LOG_FILE": str(tmp_path / "log"),
        "ARGV": str(argv),
        "FAKE_SKIP": str(disk),
    }
    if retry_ok:
        env["FAKE_RETRY_OK"] = "1"
    r = subprocess.run(
        ["sh", str(JOB)], env=env, capture_output=True, text=True, check=False
    )
    calls = []
    if argv.exists():
        for chunk in argv.read_text().split("CALL\n"):
            if chunk.strip():
                calls.append(chunk.strip("\n").split("\n"))
    return r, calls, str(disk)


def _creates(calls):
    return [c for c in calls if c and c[0] == "create"]


def _archive(call):
    return next(a for a in call if "::" in a)


def test_retry_archive_is_created(tmp_path):
    _, calls, _ = _run(tmp_path, retry_ok=False)
    archives = [_archive(c) for c in _creates(calls)]
    assert any(
        a.startswith("/backup/pools::") and a.endswith("-retry") for a in archives
    )
    assert any(
        a.startswith("/backup/pools::") and not a.endswith("-retry") for a in archives
    )


def test_warns_and_cleans_up_when_retry_recovers_nothing(tmp_path):
    r, calls, disk = _run(tmp_path, retry_ok=False)
    assert any(
        line == f"Warning: BACKUP_SKIPPED_FILE: {disk}"
        for line in r.stdout.splitlines()
    )
    # the empty companion archive is deleted
    assert any(c and c[0] == "delete" for c in calls)


def test_no_warning_when_retry_recovers(tmp_path):
    r, calls, _ = _run(tmp_path, retry_ok=True)
    assert "BACKUP_SKIPPED_FILE:" not in r.stdout
    assert not any(c and c[0] == "delete" for c in calls)
