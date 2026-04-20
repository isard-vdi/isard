# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/migrations.py``."""

import pytest
from api.schemas.migrations import (
    AdminMigrationEntry,
    AdminMigrationsResponse,
    ImportUserRequest,
    MigrationConfigResponse,
    MigrationConfigUpdateRequest,
    MigrationExportResponse,
    MigrationListDeployment,
    MigrationListDesktop,
    MigrationListItemsResponse,
    MigrationListMedia,
    MigrationListTemplate,
    MigrationProviderEnabledResponse,
)
from pydantic import ValidationError


class TestMigrationExportResponse:
    def test_token_required(self):
        with pytest.raises(ValidationError):
            MigrationExportResponse()

    def test_accepts_token(self):
        assert MigrationExportResponse(token="jwt").token == "jwt"


class TestImportUserRequest:
    def test_token_required(self):
        with pytest.raises(ValidationError):
            ImportUserRequest()


class TestMigrationProviderEnabledResponse:
    def test_enabled_required(self):
        with pytest.raises(ValidationError):
            MigrationProviderEnabledResponse()


class TestMigrationListDesktop:
    """kind is a Literal[DomainKindEnum.desktop.value] — pin so a typo
    in the kind value (e.g. "desktops" plural) is rejected."""

    _required = {
        "id": "d-1",
        "name": "Desktop",
        "kind": "desktop",
        "user": "u-1",
        "username": "u",
        "user_name": "User",
        "persistent": True,
    }

    def test_accepts_required(self):
        d = MigrationListDesktop(**self._required)
        assert d.kind == "desktop"

    def test_wrong_kind_rejected(self):
        with pytest.raises(ValidationError):
            MigrationListDesktop(**{**self._required, "kind": "template"})

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            MigrationListDesktop(**payload)


class TestMigrationListTemplate:
    _required = {
        "id": "t-1",
        "name": "Tmpl",
        "kind": "template",
        "user": "u-1",
        "category": "default",
        "group": "default-default",
        "username": "u",
        "user_name": "User",
    }

    def test_kind_template(self):
        t = MigrationListTemplate(**self._required)
        assert t.kind == "template"
        assert t.duplicate_parent_template is None

    def test_wrong_kind_rejected(self):
        with pytest.raises(ValidationError):
            MigrationListTemplate(**{**self._required, "kind": "desktop"})


class TestMigrationListMedia:
    @pytest.mark.parametrize("missing", ["id", "name", "user", "username", "user_name"])
    def test_required(self, missing):
        payload = {
            "id": "m-1",
            "name": "M",
            "user": "u-1",
            "username": "u",
            "user_name": "User",
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            MigrationListMedia(**payload)


class TestMigrationListDeployment:
    @pytest.mark.parametrize("missing", ["id", "name", "user", "username", "user_name"])
    def test_required(self, missing):
        payload = {
            "id": "dep-1",
            "name": "Dep",
            "user": "u-1",
            "username": "u",
            "user_name": "User",
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            MigrationListDeployment(**payload)


class TestMigrationListItemsResponse:
    _required = {
        "desktops": [],
        "templates": [],
        "media": [],
        "deployments": [],
        "users": [],
        "action_after_migrate": "none",
    }

    def test_accepts_empty_lists(self):
        r = MigrationListItemsResponse(**self._required)
        assert r.desktops == []
        assert r.action_after_migrate == "none"

    def test_action_literal(self):
        """action_after_migrate is Literal['none', 'disable', 'delete']."""
        for action in ["none", "disable", "delete"]:
            r = MigrationListItemsResponse(
                **{**self._required, "action_after_migrate": action}
            )
            assert r.action_after_migrate == action

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            MigrationListItemsResponse(
                **{**self._required, "action_after_migrate": "purge"}
            )

    @pytest.mark.parametrize("missing", list(_required))
    def test_every_field_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            MigrationListItemsResponse(**payload)


class TestMigrationConfigResponse:
    def test_default_check_quotas_false(self):
        r = MigrationConfigResponse()
        assert r.check_quotas is False


class TestMigrationConfigUpdateRequest:
    def test_check_quotas_optional(self):
        r = MigrationConfigUpdateRequest()
        assert r.check_quotas is None


class TestAdminMigrationEntry:
    _required = {
        "id": "m-1",
        "origin_user": "u-1",
        "status": "pending",
        "token": "jwt",
    }

    def test_accepts_required(self):
        e = AdminMigrationEntry(**self._required)
        assert e.target_user is None

    @pytest.mark.parametrize("missing", list(_required))
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminMigrationEntry(**payload)


class TestAdminMigrationsResponse:
    def test_migrations_required(self):
        with pytest.raises(ValidationError):
            AdminMigrationsResponse()
