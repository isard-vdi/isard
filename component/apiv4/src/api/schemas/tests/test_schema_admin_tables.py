# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_tables.py``.

Covers TableListRequest, AllowedTermRequest, AllowedUpdateRequest, and
AllowedGetRequest — request bodies for the generic admin-table CRUD and
allowed-list management endpoints.
"""

import pytest
from api.schemas.admin_tables import (
    AllowedGetRequest,
    AllowedTermRequest,
    AllowedUpdateRequest,
    TableListRequest,
)
from pydantic import ValidationError


class TestTableListRequest:
    """Every field optional — used for filter-and-list. The route's
    `model_dump(exclude_none=True)` relies on unset fields being dropped
    so the service's `if "id" in options:` checks behave correctly."""

    def test_accepts_empty(self):
        r = TableListRequest()
        assert r.id is None
        assert r.pluck is None
        assert r.without is None

    def test_pluck_accepts_list(self):
        r = TableListRequest(pluck=["id", "name"])
        assert r.pluck == ["id", "name"]

    def test_pluck_accepts_dict(self):
        """pluck: Optional[Union[list, dict]] — RethinkDB pluck supports
        nested dict shape `{"sub": {"field": True}}`. Pin both shapes."""
        r = TableListRequest(pluck={"users": {"id": True}})
        assert r.pluck == {"users": {"id": True}}

    def test_without_accepts_list_or_string(self):
        assert TableListRequest(without=["secret"]).without == ["secret"]
        assert TableListRequest(without="password").without == "password"

    def test_full(self):
        r = TableListRequest(
            id="u-1",
            index="user_id",
            order_by="name",
            pluck=["id"],
            without="password",
        )
        dump = r.model_dump(exclude_none=True)
        # All set fields present, no extras.
        assert set(dump.keys()) == {"id", "index", "order_by", "pluck", "without"}


class TestAllowedTermRequest:
    def test_term_required(self):
        with pytest.raises(ValidationError):
            AllowedTermRequest()

    def test_accepts_term(self):
        r = AllowedTermRequest(term="ad")
        assert r.term == "ad"
        assert r.category is None
        assert r.exclude_role is None
        assert r.kind is None

    def test_accepts_filters(self):
        r = AllowedTermRequest(
            term="ad",
            category="default",
            exclude_role="admin",
            kind="isos",
        )
        assert r.kind == "isos"

    def test_round_trip(self):
        r = AllowedTermRequest(term="ad", category="default")
        assert AllowedTermRequest(**r.model_dump()) == r


class TestAllowedUpdateRequest:
    _required = {
        "id": "m-1",
        "allowed": {"roles": [], "categories": [], "groups": [], "users": []},
    }

    def test_accepts_required(self):
        r = AllowedUpdateRequest(**self._required)
        assert r.id == "m-1"
        assert r.allowed["roles"] == []

    @pytest.mark.parametrize("missing", ["id", "allowed"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AllowedUpdateRequest(**payload)

    def test_allowed_accepts_arbitrary_dict(self):
        """allowed: dict — no sub-schema enforced. The service builds the
        full allowed shape; the schema just passes through. Pin so a
        future move to typed `Allowed` is noticed (and route mocks
        update accordingly)."""
        r = AllowedUpdateRequest(id="m-1", allowed={"any": "shape"})
        assert r.allowed == {"any": "shape"}


class TestAllowedGetRequest:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            AllowedGetRequest()

    def test_accepts_id(self):
        r = AllowedGetRequest(id="m-1")
        assert r.id == "m-1"
