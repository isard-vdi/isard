"""The pools job must word-split BACKUP_POOLS_CREATE_OPTIONS into borg create."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "87-pools-borg.sh"


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, create_options):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "disk.qcow2").write_bytes(b"x")

    # one ready pool directory from the resolver
    _exe(bindir / "isardvdi-backup-pool-paths", f'printf "%s\\n" "{pool}"\n')
    # hermetic: no real per-repo lock, so the test is parallelism-safe
    _exe(bindir / "flock", "exit 0\n")
    # fake borg: one argv entry per line, each call framed by a CALL line
    argv = tmp_path / "argv"
    _exe(
        bindir / "borg",
        f'{{ echo CALL; for a in "$@"; do printf "%s\\n" "$a"; done; }} >> "{argv}"\n'
        "exit 0\n",
    )

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BACKUP_POOLS_CREATE_OPTIONS": create_options,
        "BACKUP_POOLS_NICE": "env",  # no-op wrapper so borg is invoked directly
        "BACKUP_POOLS_PRUNE": "",  # empty prune => job skips prune and exits 0
        "LOG_FILE": str(tmp_path / "log"),
    }
    subprocess.run(
        ["sh", str(JOB)], env=env, capture_output=True, text=True, check=False
    )

    calls = []
    if argv.exists():
        for chunk in argv.read_text().split("CALL\n"):
            if chunk.strip():
                calls.append(chunk.strip("\n").split("\n"))
    return calls


def _create_argv(calls):
    return next(c for c in calls if c and c[0] == "create")


def test_create_options_are_word_split_into_borg_create(tmp_path):
    create = _create_argv(_run(tmp_path, "--sparse --chunker-params fixed,4194304"))
    # each option is its OWN argv entry (word-split), not one quoted blob
    assert "--sparse" in create
    assert create[create.index("--chunker-params") + 1] == "fixed,4194304"
    # the options precede the archive spec
    archive = next(a for a in create if a.startswith("/backup/pools::"))
    assert create.index("--sparse") < create.index(archive)


def test_no_create_options_by_default(tmp_path):
    create = _create_argv(_run(tmp_path, ""))
    assert "--sparse" not in create
    assert "--chunker-params" not in create
    # the archive is still created from the resolved directories
    assert any(a.startswith("/backup/pools::") for a in create)
