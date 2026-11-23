# SPDX-License-Identifier: AGPL-3.0-or-later

"""The password every restored user gets comes from the operator, or is random and kept in a 0600 file."""

from __future__ import annotations

import stat
from pathlib import Path

import bcrypt
import pytest
from anonymize_db.cli import USER_PASSWORD_ENV, build_parser, resolve_user_password
from anonymize_db.scrub import ADMIN_ID, Scrubber


def _users(scrubber: Scrubber) -> list[dict]:
    return scrubber.users(
        [
            {"id": ADMIN_ID, "password": "x"},
            {"id": "local-default-user-0001", "password": "y", "email": "a@b.c"},
        ]
    )


def test_every_user_gets_the_password_the_scrubber_was_given():
    for row in _users(Scrubber(user_password="operator-chosen")):
        assert bcrypt.checkpw(b"operator-chosen", row["password"].encode())


def test_without_a_password_each_run_gets_a_random_one():
    a, b = Scrubber(), Scrubber()
    assert a.user_password != b.user_password
    assert len(a.user_password) >= 20
    for row in _users(a):
        assert bcrypt.checkpw(a.user_password.encode(), row["password"].encode())


def test_the_environment_variable_sets_the_password(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(USER_PASSWORD_ENV, "from-env")
    password, path = resolve_user_password(None, tmp_path / "anon.tar.gz")
    assert (password, path) == ("from-env", None)
    assert list(tmp_path.iterdir()) == []


def test_the_password_file_wins_over_the_environment(monkeypatch, tmp_path: Path):
    monkeypatch.setenv(USER_PASSWORD_ENV, "from-env")
    src = tmp_path / "pw"
    src.write_text("from-file\nignored\n", encoding="utf-8")
    assert resolve_user_password(src, tmp_path / "anon.tar.gz") == ("from-file", None)


def test_an_empty_password_file_is_refused(tmp_path: Path):
    src = tmp_path / "pw"
    src.write_text("\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        resolve_user_password(src, tmp_path / "anon.tar.gz")


def test_a_generated_password_lands_in_a_0600_file_and_not_on_stdout(
    monkeypatch, tmp_path: Path, capsys
):
    monkeypatch.delenv(USER_PASSWORD_ENV, raising=False)
    password, path = resolve_user_password(None, tmp_path / "anon.tar.gz")
    assert path == tmp_path / "anon.tar.gz.password"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8") == password + "\n"
    out = capsys.readouterr()
    assert password not in out.out and password not in out.err


def test_the_help_names_the_password_options():
    text = build_parser().format_help()
    assert "--user-password-file" in text
    assert USER_PASSWORD_ENV in text
