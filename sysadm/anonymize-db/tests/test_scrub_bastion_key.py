# SPDX-License-Identifier: AGPL-3.0-or-later
"""The profile bastion SSH key is a credential and must not survive a dump.

The bastion resolves this key live when a connection arrives, so whoever holds
the matching private key gets a shell on every desktop its owner can reach. A
dump that keeps it is a dump that hands out that access.
"""

from anonymize_db.scrub import Scrubber

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIrealkey person@laptop"


def _scrub(rows):
    return Scrubber(seed=0).users(rows)


class TestTheBastionKeyIsBlanked:
    def test_a_stored_key_does_not_survive(self):
        (row,) = _scrub([{"id": "u-0123456789ab", "bastion_ssh_key": KEY}])
        assert row["bastion_ssh_key"] == ""

    def test_a_user_without_the_field_is_untouched(self):
        (row,) = _scrub([{"id": "u-0123456789ab"}])
        assert "bastion_ssh_key" not in row

    def test_a_non_string_value_is_left_alone(self):
        (row,) = _scrub([{"id": "u-0123456789ab", "bastion_ssh_key": None}])
        assert row["bastion_ssh_key"] is None
