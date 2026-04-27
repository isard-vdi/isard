# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/user_networks.py``."""

import pytest
from api.schemas.user_networks import (
    CreateUserNetworkRequest,
    UpdateUserNetworkRequest,
    UserNetworkAllowed,
    UserNetworkListResponse,
    UserNetworkResponse,
)
from pydantic import ValidationError


class TestUserNetworkAllowed:
    """The default access shape: roles=False (owner only), categories=False
    (none), groups=False (none), users=[] (none). Pin so the most-restrictive
    default doesn't accidentally widen."""

    def test_default_owner_only(self):
        a = UserNetworkAllowed()
        assert a.roles is False
        assert a.categories is False
        assert a.groups is False
        assert a.users == []

    def test_users_default_factory(self):
        """default_factory=list — each instance gets its own list."""
        a = UserNetworkAllowed()
        b = UserNetworkAllowed()
        assert a.users is not b.users

    def test_open_access_via_empty_list(self):
        """Empty list (vs False) is "everyone" semantically — pin the
        Any type accepts both."""
        a = UserNetworkAllowed(roles=[], categories=[], groups=[])
        assert a.roles == []
        assert a.categories == []
        assert a.groups == []


class TestCreateUserNetworkRequest:
    def test_name_required(self):
        with pytest.raises(ValidationError):
            CreateUserNetworkRequest()

    def test_defaults(self):
        r = CreateUserNetworkRequest(name="my-net")
        assert r.description == ""
        assert r.model == "virtio"
        assert r.qos_id == "unlimited"
        assert r.allowed is None

    def test_name_min_length(self):
        """min_length=1 — empty string rejected."""
        with pytest.raises(ValidationError):
            CreateUserNetworkRequest(name="")

    def test_name_max_length(self):
        """max_length=100 — pin the upper bound."""
        with pytest.raises(ValidationError):
            CreateUserNetworkRequest(name="x" * 101)
        # 100 chars accepted
        r = CreateUserNetworkRequest(name="x" * 100)
        assert len(r.name) == 100


class TestUpdateUserNetworkRequest:
    def test_accepts_empty(self):
        """All fields optional — partial update."""
        r = UpdateUserNetworkRequest()
        assert r.name is None

    def test_name_length_constraints_apply(self):
        """min_length=1 and max_length=100 apply on Update too — pin so
        partial-update path doesn't accidentally accept invalid name
        when the full Create path rejects it."""
        with pytest.raises(ValidationError):
            UpdateUserNetworkRequest(name="")
        with pytest.raises(ValidationError):
            UpdateUserNetworkRequest(name="x" * 101)


class TestUserNetworkResponse:
    def test_required_id_and_name(self):
        with pytest.raises(ValidationError):
            UserNetworkResponse()
        with pytest.raises(ValidationError):
            UserNetworkResponse(id="n-1")

    def test_defaults(self):
        r = UserNetworkResponse(id="n-1", name="my-net")
        assert r.description == ""
        assert r.kind == "user_network"
        assert r.model == "virtio"
        assert r.qos_id == "unlimited"
        assert r.metadata_id == 0


class TestUserNetworkListResponse:
    def test_networks_required(self):
        with pytest.raises(ValidationError):
            UserNetworkListResponse()

    def test_accepts_empty(self):
        assert UserNetworkListResponse(networks=[]).networks == []
