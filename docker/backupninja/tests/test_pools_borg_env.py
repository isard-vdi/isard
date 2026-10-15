"""The pools borg job must tolerate an unencrypted or relocated repo."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "87-pools-borg.sh"


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_borg_invoked_with_relocation_and_unknown_tolerance(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "d.qcow2").write_bytes(b"x")
    envfile = tmp_path / "borg-env"
    _exe(bindir / "isardvdi-backup-pool-paths", f'printf "%s\\n" "{pool}"\n')
    _exe(bindir / "flock", "exit 0\n")
    _exe(
        bindir / "borg",
        f'printf "%s %s\\n" "$BORG_RELOCATED_REPO_ACCESS_IS_OK" '
        f'"$BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK" >> "{envfile}"\nexit 0\n',
    )
    subprocess.run(
        ["sh", str(JOB)],
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "BACKUP_POOLS_NICE": "env",
            "BACKUP_POOLS_PRUNE": "",
            "LOG_FILE": str(tmp_path / "log"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert envfile.exists()
    assert "yes yes" in envfile.read_text()
