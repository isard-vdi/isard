#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The groups axis of ``build_shared_items_filter``.

Two code paths answer "may this user see this item": ``is_allowed`` in
Python, and this ReQL filter for the paginated listings. ``is_allowed``
matches the groups axis through ``check_secondary_groups``, which expands
the user's secondary groups and every ``linked_groups`` entry.

The filter used to match the primary group alone, which made it strictly
narrower than the Python path serving the very same data: an item shared
with a group the user belongs to as a SECONDARY member, or reachable
through a linked group, silently stopped being listed.
"""

import pytest
from isardvdi_common.helpers.alloweds import Alloweds

PRIMARY = "grp-primary"
SECOND = "grp-secondary"
LINKED = "grp-linked"
USER = "user-1"


@pytest.fixture
def expansion(monkeypatch):
    """Capture what the filter asks to expand, and what it gets back."""
    seen = {}

    def fake_get_user(cls, user_id):
        seen["user_id"] = user_id
        return {"id": user_id, "secondary_groups": [SECOND]}

    def fake_linked(cls, groups):
        seen["asked"] = list(groups)
        return list(groups) + [LINKED]

    monkeypatch.setattr(Alloweds, "get_user", classmethod(fake_get_user))
    monkeypatch.setattr(Alloweds, "get_all_linked_groups", classmethod(fake_linked))
    return seen


def _build(**kw):
    return Alloweds.build_shared_items_filter(
        user_role=kw.get("user_role", "advanced"),
        user_category=kw.get("user_category", "cat-a"),
        user_group=kw.get("user_group", PRIMARY),
        user_id=kw.get("user_id", USER),
        consider_user_role=kw.get("consider_user_role", True),
    )


def test_the_filter_expands_secondary_groups(expansion):
    _build()
    assert expansion["user_id"] == USER
    assert expansion["asked"] == [PRIMARY, SECOND]


def test_the_expanded_set_reaches_the_reql_term(expansion):
    """The linked group the expansion adds must end up in the query, not
    just be computed and dropped."""
    term = repr(_build().build())
    assert LINKED in term
    assert SECOND in term


def test_a_user_without_secondary_groups_still_matches_its_primary(
    expansion, monkeypatch
):
    monkeypatch.setattr(Alloweds, "get_user", classmethod(lambda cls, uid: {"id": uid}))
    _build()
    assert expansion["asked"] == [PRIMARY]


def test_a_vanished_user_degrades_to_the_primary_group(expansion, monkeypatch):
    """``get_user`` raises for a user deleted mid-listing. Losing the
    secondary groups is acceptable there; 500-ing the page is not."""

    def boom(cls, user_id):
        raise RuntimeError("no such user")

    monkeypatch.setattr(Alloweds, "get_user", classmethod(boom))
    _build()
    assert expansion["asked"] == [PRIMARY]


def test_an_empty_primary_group_is_not_looked_up(expansion, monkeypatch):
    """A blank primary would reach ``get_all`` as an empty id."""
    monkeypatch.setattr(
        Alloweds,
        "get_user",
        classmethod(lambda cls, uid: {"id": uid, "secondary_groups": [SECOND]}),
    )
    _build(user_group="")
    assert expansion["asked"] == [SECOND]


def test_an_admin_short_circuits_before_any_expansion(expansion):
    """Admins see everything; the filter must not pay for a lookup."""
    assert _build(user_role="admin") is True
    assert expansion == {}
