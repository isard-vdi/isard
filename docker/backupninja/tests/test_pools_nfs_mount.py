"""A manual pools run must mount the NFS itself when the session did not."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "87-pools-borg.sh"


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, *, nfs_enabled):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "disk.qcow2").write_bytes(b"x")
    _exe(bindir / "isardvdi-backup-pool-paths", f'printf "%s\\n" "{pool}"\n')
    _exe(bindir / "flock", "exit 0\n")
    _exe(bindir / "borg", "exit 0\n")
    mounted = tmp_path / "mounted"
    _exe(bindir / "fake-nfs-mount", f'echo mounted >> "{mounted}"\nexit 0\n')

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "NFS_MOUNT_CMD": str(bindir / "fake-nfs-mount"),
        "BACKUP_POOLS_NICE": "env",
        "BACKUP_POOLS_PRUNE": "",
        "LOG_FILE": str(tmp_path / "log"),
    }
    if nfs_enabled:
        env["BACKUP_NFS_ENABLED"] = "true"
    subprocess.run(
        ["sh", str(JOB)], env=env, capture_output=True, text=True, check=False
    )
    return mounted.exists()


def test_manual_pools_run_mounts_nfs(tmp_path):
    assert _run(tmp_path, nfs_enabled=True)


def test_no_mount_when_nfs_disabled(tmp_path):
    assert not _run(tmp_path, nfs_enabled=False)
