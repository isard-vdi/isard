"""The disks job must hand BACKUP_DISKS_CREATE_OPTIONS to the borg handler."""

import pathlib
import string

JOB = pathlib.Path(__file__).resolve().parents[1] / "backup.d" / "82-disks-borg.borg"


def _render(env):
    # envsubst semantics: unset variables become empty strings
    class _Env(dict):
        def __missing__(self, key):
            return ""

    return string.Template(JOB.read_text()).substitute(_Env(env))


def _source_section(text):
    section, out = None, {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[source]" and "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def test_create_options_are_passed_to_the_handler():
    opts = "--sparse --chunker-params fixed,4194304"
    source = _source_section(_render({"BACKUP_DISKS_CREATE_OPTIONS": opts}))
    assert source["create_options"] == opts


def test_create_options_default_to_empty():
    source = _source_section(_render({}))
    assert source["create_options"] == ""
