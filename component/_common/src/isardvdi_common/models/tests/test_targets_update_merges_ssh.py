#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Targets.update_domain_target`` must merge the protocol sub-documents.

It used to assign ``target["ssh"] = data["ssh"]`` outright. Every caller that
sent an ``ssh`` block without ``authorized_keys`` — the desktop edit form does
exactly that on every save — therefore replaced the whole sub-document and
took the keys with it. The keys are what grants bastion SSH access, so this
was silent data loss on a save that was never about them.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def targets_mod(monkeypatch):
    from isardvdi_common.models import targets as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.Targets, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        mod.Bastion, "bastion_domain_verification_required", staticmethod(lambda: False)
    )
    return mod


@pytest.fixture
def stored_and_written(targets_mod, monkeypatch):
    """Serve one stored target and capture what gets written back."""
    written = {}

    stored = {
        "id": "t1",
        "desktop_id": "d1",
        "user_id": "u1",
        "domains": [],
        "http": {"enabled": True, "http_port": 8080, "https_port": 443},
        "ssh": {
            "enabled": True,
            "port": 22,
            "authorized_keys": ["ssh-ed25519 AAAAowner owner", "ssh-rsa AAAAother bob"],
        },
    }

    monkeypatch.setattr(
        targets_mod.Targets,
        "get_domain_target",
        classmethod(lambda cls, domain_id: dict(stored)),
    )

    handle = MagicMock(name="targets-table")

    def _update(payload):
        written.update(payload)
        return MagicMock(run=MagicMock(return_value=None))

    handle.get.return_value.update.side_effect = _update
    monkeypatch.setattr(
        targets_mod.r, "db", lambda name: MagicMock(table=lambda t: handle)
    )
    monkeypatch.setattr(targets_mod.r, "table", lambda name: handle)

    return stored, written


class TestSshMergeKeepsAuthorizedKeys:
    def test_disabling_ssh_without_sending_keys_keeps_them(
        self, targets_mod, stored_and_written
    ):
        stored, written = stored_and_written

        targets_mod.Targets.update_domain_target(
            "d1", {"ssh": {"enabled": False, "port": 22}}
        )

        assert written["ssh"]["enabled"] is False
        assert written["ssh"]["authorized_keys"] == stored["ssh"]["authorized_keys"]

    def test_changing_the_port_alone_keeps_the_keys(
        self, targets_mod, stored_and_written
    ):
        stored, written = stored_and_written

        targets_mod.Targets.update_domain_target("d1", {"ssh": {"port": 2222}})

        assert written["ssh"]["port"] == 2222
        assert written["ssh"]["authorized_keys"] == stored["ssh"]["authorized_keys"]

    def test_keys_are_still_replaceable_when_actually_sent(
        self, targets_mod, stored_and_written
    ):
        _, written = stored_and_written

        targets_mod.Targets.update_domain_target(
            "d1", {"ssh": {"enabled": True, "port": 22, "authorized_keys": []}}
        )

        assert written["ssh"]["authorized_keys"] == []

    def test_http_merges_the_same_way(self, targets_mod, stored_and_written):
        stored, written = stored_and_written

        targets_mod.Targets.update_domain_target("d1", {"http": {"enabled": False}})

        assert written["http"]["enabled"] is False
        assert written["http"]["http_port"] == stored["http"]["http_port"]
