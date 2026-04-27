# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_authentication.py``.

Validates the request bodies that the
``component/apiv4/src/api/routes/admin/authentication.py`` endpoints
accept: policy create/edit, provider-config update, migration-exception
create. Each test pins the required-field set so a future schema-tightening
change (defaulting a field, removing a required marker) trips this file
before reaching staging.
"""

import pytest
from api.schemas.admin_authentication import (
    MigrationExceptionCreateRequest,
    PolicyCreateRequest,
    PolicyEditRequest,
    ProviderConfigUpdateRequest,
)
from pydantic import ValidationError

# ══════════════════════════════════════════════════════════════════════════
#  PolicyCreateRequest
# ══════════════════════════════════════════════════════════════════════════


class TestPolicyCreateRequest:
    _required = {"category": "default", "role": "admin", "type": "local"}

    def test_accepts_required_fields(self):
        p = PolicyCreateRequest(**self._required)
        assert p.category == "default"
        assert p.role == "admin"
        assert p.type == "local"
        # Optional fields default appropriately.
        assert p.disclaimer is None
        assert p.email_verification is False
        assert p.password is None

    def test_round_trip(self):
        p = PolicyCreateRequest(**self._required)
        assert PolicyCreateRequest(**p.model_dump()) == p

    @pytest.mark.parametrize("missing", ["category", "role", "type"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            PolicyCreateRequest(**payload)

    def test_email_verification_default_false_not_none(self):
        """Important nuance: ``email_verification: Optional[bool] = False``.
        With default=False the field appears in model_dump() with value
        False — not stripped by exclude_none. Pin the wire shape that the
        route relies on."""
        p = PolicyCreateRequest(**self._required)
        dump = p.model_dump(exclude_none=True)
        assert "email_verification" in dump
        assert dump["email_verification"] is False

    def test_disclaimer_dropped_by_exclude_none(self):
        """disclaimer defaults to None and exclude_none drops it. Pin so
        a route that relies on `if "disclaimer" in payload` still works."""
        p = PolicyCreateRequest(**self._required)
        dump = p.model_dump(exclude_none=True)
        assert "disclaimer" not in dump

    def test_password_accepts_dict(self):
        p = PolicyCreateRequest(
            **self._required,
            password={"min_length": 12, "require_special": True},
        )
        assert p.password == {"min_length": 12, "require_special": True}


# ══════════════════════════════════════════════════════════════════════════
#  PolicyEditRequest
# ══════════════════════════════════════════════════════════════════════════


class TestPolicyEditRequest:
    """All fields optional — used for partial updates."""

    def test_accepts_empty(self):
        p = PolicyEditRequest()
        assert p.category is None
        assert p.role is None
        assert p.type is None

    def test_accepts_partial_update(self):
        p = PolicyEditRequest(role="manager")
        dump = p.model_dump(exclude_none=True)
        assert dump == {"email_verification": None, "role": "manager"} or dump == {
            "role": "manager"
        }
        # email_verification defaults to None (not False), so it IS dropped.
        # If a future schema flip changes that to False, this test will fail.
        assert "category" not in dump

    def test_disclaimer_accepts_any(self):
        """``disclaimer: Optional[Any]`` — pin that arbitrary types pass."""
        assert PolicyEditRequest(disclaimer=True).disclaimer is True
        assert PolicyEditRequest(disclaimer="acknowledged").disclaimer == "acknowledged"
        assert PolicyEditRequest(disclaimer={"foo": "bar"}).disclaimer == {"foo": "bar"}


# ══════════════════════════════════════════════════════════════════════════
#  ProviderConfigUpdateRequest
# ══════════════════════════════════════════════════════════════════════════


class TestProviderConfigUpdateRequest:
    def test_accepts_empty(self):
        """All fields optional — empty body is valid."""
        p = ProviderConfigUpdateRequest()
        assert p.migration is None

    def test_accepts_migration_dict(self):
        p = ProviderConfigUpdateRequest(migration={"export": True, "import": False})
        assert p.migration == {"export": True, "import": False}

    def test_extra_fields_silently_dropped(self):
        """The schema only declares `migration`; other top-level keys are
        accepted and silently dropped (default Pydantic behavior). Pin
        this so a route assumption that "only declared fields land in
        model_dump" stays true."""
        p = ProviderConfigUpdateRequest(migration={}, ldap_url="x")
        dump = p.model_dump()
        assert "ldap_url" not in dump


# ══════════════════════════════════════════════════════════════════════════
#  MigrationExceptionCreateRequest
# ══════════════════════════════════════════════════════════════════════════


class TestMigrationExceptionCreateRequest:
    _required = {"item_type": "categories", "item_ids": ["c-1", "c-2"]}

    def test_accepts_required(self):
        m = MigrationExceptionCreateRequest(**self._required)
        assert m.item_type == "categories"
        assert m.item_ids == ["c-1", "c-2"]

    def test_round_trip(self):
        m = MigrationExceptionCreateRequest(**self._required)
        assert MigrationExceptionCreateRequest(**m.model_dump()) == m

    @pytest.mark.parametrize("missing", ["item_type", "item_ids"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            MigrationExceptionCreateRequest(**payload)

    def test_empty_item_ids_accepted(self):
        """An empty item_ids list is a no-op at the route level (the
        handler short-circuits the insert), but it must validate cleanly."""
        m = MigrationExceptionCreateRequest(item_type="users", item_ids=[])
        assert m.item_ids == []
