"""The disks-info job must log the enabled disk types, not an empty list."""

import os
import pathlib
import re
import subprocess

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "80-disks-info.sh"

_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def envsubst(text, env):
    """Faithful GNU envsubst: substitute $VAR / ${VAR}; a bare $ (e.g. the
    first $ of $${x}, or $( ) is left literal so the inner reference survives."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "$":
            m = _REF.match(text, i)
            if m:
                out.append(env.get(m.group(1) or m.group(2), ""))
                i = m.end()
                continue
            out.append("$")
            i += 1
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _render_and_run(tmp_path, *, templates, groups, media):
    # setup-time env: run.sh normalises each flag to "include = ..." or "".
    setup_env = {
        "my_empty_variable": "",
        "BACKUP_DISKS_TEMPLATES_ENABLED": (
            "include = /opt/isard/templates" if templates else ""
        ),
        "BACKUP_DISKS_GROUPS_ENABLED": "include = /opt/isard/groups" if groups else "",
        "BACKUP_DISKS_MEDIA_ENABLED": "include = /opt/isard/media" if media else "",
    }
    rendered = tmp_path / "80-disks-info.sh"
    rendered.write_text(envsubst(JOB.read_text(), setup_env))

    log = tmp_path / "log"
    subprocess.run(
        ["sh", str(rendered)],
        env={**os.environ, "LOG_FILE": str(log)},
        capture_output=True,
        text=True,
        check=False,
    )
    for line in log.read_text().splitlines():
        if "BACKUP_DISK_TYPES:" in line:
            return line.split("BACKUP_DISK_TYPES:", 1)[1].split()
    return None


def test_all_three_types_listed(tmp_path):
    types = _render_and_run(tmp_path, templates=True, groups=True, media=True)
    assert types == ["templates", "groups", "media"]


def test_subset_listed(tmp_path):
    types = _render_and_run(tmp_path, templates=True, groups=False, media=True)
    assert types == ["templates", "media"]


def test_single_type_listed(tmp_path):
    types = _render_and_run(tmp_path, templates=False, groups=True, media=False)
    assert types == ["groups"]
