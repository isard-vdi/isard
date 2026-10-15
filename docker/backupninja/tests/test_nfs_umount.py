"""nfs_umount.sh must not unmount /backup while a borg is running."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "nfs_umount.sh"


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, *, borg_running):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    called = tmp_path / "umount-called"
    _exe(bindir / "pgrep", "exit 0\n" if borg_running else "exit 1\n")
    _exe(bindir / "umount", f'echo called >> "{called}"\nexit 0\n')
    r = subprocess.run(
        ["sh", str(JOB)],
        env={
            **os.environ,
            "PATH": f"{bindir}:{os.environ['PATH']}",
            "BACKUP_NFS_SERVER": "nfs.invalid",
            "BACKUP_NFS_FOLDER": "/export/none",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return r, called.exists()


def _info(stdout):
    return any(line.startswith("Info: ") for line in stdout.splitlines())


def test_skips_umount_while_borg_running(tmp_path):
    r, called = _run(tmp_path, borg_running=True)
    assert not called
    assert r.returncode == 0
    assert _info(r.stdout)


def test_umounts_when_no_borg(tmp_path):
    _, called = _run(tmp_path, borg_running=False)
    assert called
