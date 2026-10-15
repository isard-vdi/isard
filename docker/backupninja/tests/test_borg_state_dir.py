"""borg's cache and registry must live next to the repositories, under /backup."""

import pathlib
import string

COMPOSE = (
    pathlib.Path(__file__).resolve().parents[3]
    / "docker-compose-parts"
    / "backupninja.yml"
)


def _entries():
    return [
        line.strip()[2:].strip()
        for line in COMPOSE.read_text().splitlines()
        if line.strip().startswith("- ")
    ]


def test_borg_dirs_are_under_the_backup_mount():
    entries = _entries()
    assert "BORG_CACHE_DIR=/backup/borg-cache" in entries
    assert "BORG_CONFIG_DIR=/backup/borg-config" in entries
    assert any(e.endswith(":/backup:rw") for e in entries)


def test_borg_dirs_are_not_bind_mounted_from_the_host():
    for entry in _entries():
        assert not entry.endswith(":/root/.cache/borg"), entry
        assert not entry.endswith(":/root/.config/borg"), entry


JOBS = sorted(
    (COMPOSE.parents[1] / "docker" / "backupninja" / "backup.d").glob("*.borg")
)


def _source_cache_directory(job, env):
    class _Env(dict):
        def __missing__(self, key):
            return ""

    section = None
    for line in string.Template(job.read_text()).substitute(_Env(env)).splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line
        elif section == "[source]" and line.startswith("cache_directory"):
            return line.partition("=")[2].strip()
    return None


def test_every_borg_job_points_the_handler_at_the_cache():
    # the borg handler unsets BORG_CACHE_DIR for a job without cache_directory
    assert JOBS
    for job in JOBS:
        cache = _source_cache_directory(job, {"BORG_CACHE_DIR": "/backup/borg-cache"})
        assert cache == "/backup/borg-cache", job.name
