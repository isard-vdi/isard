"""71-config-source-check.sh is Fatal when the config backup would archive nothing."""

import os
import pathlib
import subprocess

JOB = (
    pathlib.Path(__file__).resolve().parents[1]
    / "backup.d"
    / "71-config-source-check.sh"
)


def _run(root):
    return subprocess.run(
        ["sh", str(JOB)],
        env={**os.environ, "CONFIG_SOURCE_ROOT": str(root)},
        capture_output=True,
        text=True,
        check=False,
    )


def _fatal(stdout):
    return any(line.startswith("Fatal: ") for line in stdout.splitlines())


def test_fatal_when_root_has_no_files(tmp_path):
    (tmp_path / "config").mkdir()  # exists but empty
    r = _run(tmp_path)
    assert _fatal(r.stdout)
    assert r.returncode != 0


def test_fatal_when_root_missing_entirely(tmp_path):
    r = _run(tmp_path / "nope")
    assert _fatal(r.stdout)
    assert r.returncode != 0


def test_ok_when_a_config_dir_has_a_file(tmp_path):
    d = tmp_path / "certs"
    d.mkdir()
    (d / "chain.pem").write_text("x")
    r = _run(tmp_path)
    assert not _fatal(r.stdout)
    assert r.returncode == 0
