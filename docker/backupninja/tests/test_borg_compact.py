"""borg_compact.sh must turn a failed compact into a line backupninja counts."""

import os
import pathlib
import stat
import subprocess

import pytest

HELPER = pathlib.Path(__file__).resolve().parents[1] / "borg_compact.sh"
LOCK_MSG = "Failed to create/acquire the lock /repo/lock.exclusive (timeout)."


def _run(tmp_path, borg_output, borg_rc, repo_exists=True):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = bindir / "borg"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "$@" > "{tmp_path}/args"\n'
        f"printf '%s\\n' '{borg_output}' >&2\n"
        f"exit {borg_rc}\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    repo = tmp_path / "repo"
    if repo_exists:
        repo.mkdir()
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
    proc = subprocess.run(
        ["sh", str(HELPER), str(repo)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc, repo


def _status_lines(stdout):
    return [l for l in stdout.splitlines() if l.startswith(("Warning:", "Error:"))]


def test_success_reports_nothing(tmp_path):
    proc, repo = _run(tmp_path, "compaction freed 10 MB", 0)
    assert proc.returncode == 0
    assert _status_lines(proc.stdout) == []
    args = (tmp_path / "args").read_text()
    assert "compact" in args and str(repo) in args


def test_lock_timeout_is_a_warning(tmp_path):
    proc, _ = _run(tmp_path, LOCK_MSG, 2)
    assert proc.returncode == 2
    [line] = _status_lines(proc.stdout)
    assert line.startswith("Warning:") and "locked" in line
    assert LOCK_MSG in proc.stdout


def test_borg_warning_exit_is_a_warning(tmp_path):
    proc, _ = _run(tmp_path, "something borg warns about", 1)
    [line] = _status_lines(proc.stdout)
    assert line.startswith("Warning:")


@pytest.mark.parametrize("rc", [2, 73])
def test_other_failure_is_an_error(tmp_path, rc):
    proc, _ = _run(tmp_path, "Repository /repo does not exist.", rc)
    assert proc.returncode == rc
    [line] = _status_lines(proc.stdout)
    assert line.startswith("Error:") and f"exit {rc}" in line


def test_missing_repository_is_skipped(tmp_path):
    proc, _ = _run(tmp_path, "unused", 2, repo_exists=False)
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert not (tmp_path / "args").exists()
