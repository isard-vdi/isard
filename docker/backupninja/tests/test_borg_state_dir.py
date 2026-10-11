"""borg's cache and registry must live next to the repositories, under /backup."""

import pathlib

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
