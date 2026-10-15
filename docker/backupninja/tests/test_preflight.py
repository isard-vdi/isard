"""The session preflight must check /backup and report at column 0 on stdout."""

import os
import pathlib
import stat
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "session_preflight.sh"


def _fake_df(bindir, percent):
    df = bindir / "df"
    df.write_text(
        "#!/bin/sh\n"
        'printf "Filesystem 1K-blocks Used Available Capacity Mounted\\n"\n'
        f'printf "/dev/fake 100 {percent} 10 {percent}%% %s\\n" "$2"\n'
    )
    df.chmod(df.stat().st_mode | stat.S_IXUSR)


def _run(tmp_path, percent, target_exists=True, min_free=None):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    _fake_df(bindir, percent)
    target = tmp_path / "backup"
    if target_exists:
        target.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "BACKUP_TARGET": str(target),
        # BACKUP_DIR is the HOST path and must NOT be what the job checks.
        "BACKUP_DIR": str(tmp_path / "does-not-exist-host-path"),
        "LOG_FILE": str(tmp_path / "log"),
    }
    if min_free is not None:
        env["BACKUP_MIN_FREE_PERCENT"] = str(min_free)
    return subprocess.run(
        ["sh", str(JOB)], env=env, capture_output=True, text=True, check=False
    )


def _has_col0(text, keyword):
    return any(line.startswith(keyword) for line in text.splitlines())


def test_full_target_is_fatal_at_col0_on_stdout(tmp_path):
    r = _run(tmp_path, percent=95, min_free=10)
    assert _has_col0(r.stdout, "Fatal: "), r.stdout
    assert r.returncode != 0


def test_healthy_target_is_info_at_col0_and_exit0(tmp_path):
    r = _run(tmp_path, percent=40, min_free=10)
    assert _has_col0(r.stdout, "Info: "), r.stdout
    assert r.returncode == 0


def test_checks_backup_target_not_backup_dir(tmp_path):
    # BACKUP_DIR points at a missing host path; a healthy /backup must still pass
    r = _run(tmp_path, percent=40, min_free=10)
    assert _has_col0(r.stdout, "Info: "), r.stdout
    assert "does-not-exist-host-path" not in r.stdout


def test_missing_target_is_fatal(tmp_path):
    r = _run(tmp_path, percent=40, target_exists=False, min_free=10)
    assert _has_col0(r.stdout, "Fatal: "), r.stdout
    assert r.returncode != 0


def test_status_never_written_only_to_logfile(tmp_path):
    # The whole point: status goes to stdout (counted), not just the log.
    r = _run(tmp_path, percent=95, min_free=10)
    log = tmp_path / "log"
    logged = log.read_text() if log.exists() else ""
    # Even if it also logs, the counted copy must be on stdout.
    assert _has_col0(r.stdout, "Fatal: "), (r.stdout, logged)
