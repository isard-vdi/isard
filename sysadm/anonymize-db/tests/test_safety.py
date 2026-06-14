"""Tests for the destructive-target confirmation gate."""

from __future__ import annotations

import pytest
from anonymize_db.safety import confirm_destructive_target

KW = dict(
    action="RESTORE into DB 'isard'",
    target_label="prod-db-node",
    accepted={"prod-db-node", "bastion.example.com"},
    endpoint="admin:prod-db-node@bastion.example.com -> 172.31.255.13:28015",
    details=["DB 'isard' holds 1234 rows across 45 tables — DROPPED and replaced."],
)


def test_confirm_target_match_proceeds():
    # exact match (case-insensitive) -> returns without raising
    confirm_destructive_target(confirm_target="PROD-DB-NODE", **KW)
    # an accepted alias (the domain) also works
    confirm_destructive_target(confirm_target="bastion.example.com", **KW)


def test_confirm_target_mismatch_aborts():
    with pytest.raises(SystemExit) as e:
        confirm_destructive_target(confirm_target="some-other-host", **KW)
    assert "does not match" in str(e.value)


def test_no_tty_without_confirm_target_aborts():
    # non-interactive and no --confirm-target -> must refuse
    with pytest.raises(SystemExit) as e:
        confirm_destructive_target(confirm_target=None, interactive=False, **KW)
    assert "without confirmation" in str(e.value)


def test_yes_cannot_bypass(monkeypatch):
    # interactive prompt: a wrong typed answer aborts even though no
    # --confirm-target/--yes is involved (the gate never consults --yes).
    monkeypatch.setattr("builtins.input", lambda _prompt="": "yes")
    with pytest.raises(SystemExit):
        confirm_destructive_target(confirm_target=None, interactive=True, **KW)


def test_interactive_correct_answer_proceeds(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt="": "prod-db-node")
    confirm_destructive_target(confirm_target=None, interactive=True, **KW)
