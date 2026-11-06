# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rule resolution with rules whose stored ``allowed`` lacks some keys."""

from isardvdi_common.helpers.rules import get_applied_rule_decorator

PAYLOAD = {
    "user_id": "juan",
    "group_id": "g",
    "category_id": "alumnos",
    "role_id": "user",
}
EMPTY = {"name": "empty", "allowed": {}}
DEFAULT = {
    "name": "default",
    "allowed": {"users": False, "groups": False, "categories": False, "roles": []},
}


def _resolve(rules):
    @get_applied_rule_decorator(rules)
    def applied(rule, payload):
        return rule

    return applied(PAYLOAD)


def test_rule_with_empty_allowed_matches_nobody():
    assert _resolve([EMPTY]) is False


def test_rule_with_empty_allowed_falls_through_to_the_next_rule():
    assert _resolve([EMPTY, DEFAULT]) is DEFAULT


def test_missing_keys_do_not_hide_the_ones_present():
    partial = {"name": "partial", "allowed": {"categories": ["alumnos"]}}
    assert _resolve([partial]) is partial
