# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/allowed.py``.

Critical: the AllowedBase / Allowed models carry a custom
``field_serializer`` that deduplicates list values. Pin so a refactor
that drops the dedup silently lets duplicate user/group/category IDs
into the DB.
"""

import pytest
from api.schemas.allowed import (
    Allowed,
    AllowedBase,
    AllowedResponse,
    AllowedUpdate,
    AvailableGroup,
    AvailableUser,
    ItemAllowed,
    SelectedAllowed,
)
from pydantic import ValidationError


class TestAllowedUpdate:
    """Both groups/users default to None — meaning "don't update".
    Pin so a future schema change to False (which means "no allowed")
    is intentional."""

    def test_defaults_none(self):
        u = AllowedUpdate()
        assert u.groups is None
        assert u.users is None

    def test_accepts_bool(self):
        u = AllowedUpdate(groups=False, users=False)
        assert u.groups is False
        assert u.users is False

    def test_accepts_list(self):
        u = AllowedUpdate(groups=["g-1"], users=["u-1", "u-2"])
        assert u.groups == ["g-1"]


class TestItemAllowed:
    @pytest.mark.parametrize("missing", ["all", "available"])
    def test_required(self, missing):
        payload = {"all": False, "available": [{"id": "x"}]}
        del payload[missing]
        with pytest.raises(ValidationError):
            ItemAllowed(**payload)


class TestSelectedAllowed:
    def test_accepts_bool_or_list(self):
        a = SelectedAllowed(groups=False, users=False)
        assert a.groups is False
        a = SelectedAllowed(groups=["g-1"], users=["u-1"])
        assert a.groups == ["g-1"]


class TestAvailableUser:
    def test_required_set(self):
        with pytest.raises(ValidationError):
            AvailableUser()

    def test_minimal(self):
        u = AvailableUser(id="u-1", name="User", username="u")
        assert u.id == "u-1"
        # photo defaults to "" not None — pin so the wire shape always
        # carries a string (the frontend renders "" as "no photo").
        assert u.photo == ""

    def test_photo_optional_with_default(self):
        u = AvailableUser(id="u-1", name="User", username="u", photo="https://x/y.png")
        assert u.photo == "https://x/y.png"


class TestAvailableGroup:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_required(self, missing):
        payload = {"id": "g-1", "name": "G"}
        del payload[missing]
        with pytest.raises(ValidationError):
            AvailableGroup(**payload)


class TestAllowedResponse:
    def test_full(self):
        r = AllowedResponse(
            selected={"groups": ["g-1"], "users": False},
            available_groups=[{"id": "g-1", "name": "G"}],
        )
        assert r.selected.groups == ["g-1"]
        assert r.available_groups[0].id == "g-1"

    def test_available_groups_bool(self):
        """available_groups can be False (no shareable groups) — pin so
        the union type stays."""
        r = AllowedResponse(
            selected={"groups": False, "users": False},
            available_groups=False,
        )
        assert r.available_groups is False


class TestAllowedBase:
    def test_defaults_false(self):
        """groups/users default False (NOT empty list) — False means
        "no allowed"."""
        a = AllowedBase()
        assert a.groups is False
        assert a.users is False

    def test_dedup_lists(self):
        """The field_serializer deduplicates list values. Pin so a
        refactor that drops the dedup is loud — duplicates would
        silently bloat the DB row."""
        a = AllowedBase(groups=["g-1", "g-1", "g-2"], users=["u-1", "u-1"])
        dump = a.model_dump()
        assert sorted(dump["groups"]) == ["g-1", "g-2"]
        assert dump["users"] == ["u-1"]

    def test_bool_passes_through_serializer(self):
        """Serializer only dedups when the value is a list — bool
        passes through unchanged."""
        a = AllowedBase(groups=False, users=False)
        dump = a.model_dump()
        assert dump["groups"] is False
        assert dump["users"] is False


class TestAllowed:
    """Adds categories + roles fields; same dedup contract."""

    def test_defaults_false(self):
        a = Allowed()
        assert a.groups is False
        assert a.users is False
        assert a.categories is False
        assert a.roles is False

    def test_dedup_categories_and_roles(self):
        a = Allowed(
            categories=["c-1", "c-1", "c-2"],
            roles=["admin", "admin", "user"],
        )
        dump = a.model_dump()
        assert sorted(dump["categories"]) == ["c-1", "c-2"]
        assert sorted(dump["roles"]) == ["admin", "user"]
