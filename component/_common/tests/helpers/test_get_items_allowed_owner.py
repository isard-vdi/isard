#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Ownership inside ``get_items_allowed``, under ``query_merge``.

``query_merge`` rewrites ``user`` into a ``{id, name, photo}`` object so
the client can render the owner. The selection loop right after it — and
``is_allowed`` through it — decides ownership by comparing that field to
a user id, which against the merged object is never equal.

The effect was silent and user-visible: every listing that merges
dropped the caller's OWN rows unless some other axis happened to grant
them. It is the list behind "create a desktop from a template" in the
old frontend and in the webapp, both of which call
``/items/templates/allowed/all``.
"""

import contextlib

import pytest
from isardvdi_common.helpers import alloweds as alloweds_module
from isardvdi_common.helpers.alloweds import Alloweds

OWNER = "user-owner"
OTHER = "user-other"


class _FakeQuery:
    """Swallows the whole ReQL chain and returns the rows given to it."""

    def __init__(self, rows):
        self._rows = rows

    def __getattr__(self, _name):
        return lambda *a, **k: self

    def run(self, _conn):
        return self._rows


@pytest.fixture
def rows_from(monkeypatch):
    def _install(rows):
        monkeypatch.setattr(
            alloweds_module,
            "r",
            type("_R", (), {"table": staticmethod(lambda _t: _FakeQuery(rows))})(),
        )
        # ``_rdb_connection`` stays as it is: the fake query ignores the
        # argument, and the attribute is a metaclass property that
        # monkeypatch cannot restore.
        monkeypatch.setattr(
            Alloweds, "_rdb_context", classmethod(lambda cls: contextlib.nullcontext())
        )

    return _install


def _payload(user_id=OWNER, role_id="advanced"):
    return {
        "user_id": user_id,
        "role_id": role_id,
        "category_id": "cat-a",
        "group_id": "grp-a",
    }


def _template(item_id, user, category="cat-a"):
    return {
        "id": item_id,
        "user": user,
        "category": category,
        "allowed": {
            "roles": False,
            "categories": False,
            "groups": False,
            "users": False,
        },
    }


def test_own_row_survives_the_merged_user_object(rows_from):
    """The regression: ``user`` merged into an object hid the row."""
    rows_from([_template("t-mine", {"id": OWNER, "name": "Owner", "photo": None})])
    got = Alloweds.get_items_allowed(_payload(), table="domains")
    assert [i["id"] for i in got] == ["t-mine"]
    assert got[0]["editable"] is True


def test_own_row_survives_an_unmerged_user_id(rows_from):
    """The un-merged shape must keep working identically."""
    rows_from([_template("t-mine", OWNER)])
    got = Alloweds.get_items_allowed(_payload(), table="domains")
    assert [i["id"] for i in got] == ["t-mine"]
    assert got[0]["editable"] is True


def test_someone_elses_row_is_still_excluded(rows_from):
    """Normalising the owner must not turn into granting everything."""
    rows_from([_template("t-theirs", {"id": OTHER, "name": "Other", "photo": None})])
    assert Alloweds.get_items_allowed(_payload(), table="domains") == []


def test_the_response_keeps_the_merged_owner_object(rows_from):
    """Clients render owner name and photo from it; the fix must not
    flatten the field back to an id."""
    merged = {"id": OWNER, "name": "Owner", "photo": None}
    rows_from([_template("t-mine", merged)])
    got = Alloweds.get_items_allowed(_payload(), table="domains")
    assert got[0]["user"] == merged


def test_a_deleted_owner_placeholder_does_not_match_anyone(rows_from):
    """``query_merge`` defaults a missing owner to a placeholder with no
    ``id``; it must not accidentally compare equal."""
    rows_from([_template("t-orphan", {"name": "DELETED", "photo": None})])
    assert Alloweds.get_items_allowed(_payload(), table="domains") == []
