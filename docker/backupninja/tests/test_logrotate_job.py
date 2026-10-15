"""The logrotate cron entry must not rotate while a borg is running."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "logrotate_backupninja.sh"


def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, *, borg_running):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ran = tmp_path / "logrotate-ran"
    _exe(bindir / "pgrep", "exit 0\n" if borg_running else "exit 1\n")
    _exe(bindir / "logrotate", f'echo ran >> "{ran}"\nexit 0\n')
    r = subprocess.run(
        ["sh", str(JOB)],
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )
    return r, ran.exists()


def test_skips_rotation_while_borg_running(tmp_path):
    r, rotated = _run(tmp_path, borg_running=True)
    assert r.returncode == 0
    assert not rotated


def test_rotates_when_no_borg(tmp_path):
    r, rotated = _run(tmp_path, borg_running=False)
    assert rotated
