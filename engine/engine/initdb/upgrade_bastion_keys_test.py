"""Unit tests for the v206 bastion authorized_keys cleanup.

The bastion used to copy profile keys into every target it could reach and
nothing ever took them out; it resolves them live now. A stored copy is
therefore an access that outlives the permission it came from, and the
migration exists to drop exactly those and nothing else.

The decision lives in ``upgrade_helpers.py`` so it can be loaded bare
(``upgrade.py`` itself cannot: humanfriendly, rethinkdb, config).
"""

import os
import runpy
import types

OWNER = "ssh-ed25519 AAAAowner owner@host"
FRIEND = "ssh-ed25519 AAAAfriend friend@host"
HAND_TYPED = "ssh-rsa AAAAtyped somebody"


def _load_helpers():
    ns = runpy.run_path(
        os.path.join(os.path.dirname(__file__), "upgrade_helpers.py"),
        run_name="_bastion_keys_under_test",
    )
    return types.SimpleNamespace(**ns)


m = _load_helpers()


class TestWhatTheCleanupDrops:
    def test_a_copy_of_a_profile_key_is_dropped(self):
        assert m.bastion_keys_to_keep([OWNER], {OWNER}) == []

    def test_a_hand_typed_key_is_the_only_record_of_itself_and_stays(self):
        assert m.bastion_keys_to_keep([HAND_TYPED], {OWNER}) == [HAND_TYPED]

    def test_a_mixed_list_keeps_only_what_nobody_can_resolve_live(self):
        stored = [OWNER, HAND_TYPED, FRIEND]
        assert m.bastion_keys_to_keep(stored, {OWNER, FRIEND}) == [HAND_TYPED]

    def test_surrounding_whitespace_does_not_save_a_copy(self):
        assert m.bastion_keys_to_keep([f"  {OWNER}  "], {OWNER}) == []

    def test_an_entry_that_is_not_a_string_is_left_alone(self):
        entry = {"key": OWNER, "user_id": "u1"}
        assert m.bastion_keys_to_keep([entry], {OWNER}) == [entry]


class TestWhatTheCleanupLeavesAlone:
    def test_no_profile_keys_means_nothing_is_touched(self):
        stored = [OWNER, HAND_TYPED]
        assert m.bastion_keys_to_keep(stored, set()) == stored

    def test_an_empty_or_missing_list_is_handled(self):
        assert m.bastion_keys_to_keep([], {OWNER}) == []
        assert m.bastion_keys_to_keep(None, {OWNER}) == []
