# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/domains/templates.py``.

Focuses on the contract-relevant request bodies (TemplateEditRequest,
TemplateToDesktopRequest, NewTemplateRequest, DuplicateTemplateRequest,
TemplateSetEnabledRequest) and the wire-shape sentinels (UserAllowedTemplateFlatItem
extras-allow). Pure response shapes (UserTemplate, UserSharedTemplate, etc.)
get a lighter touch — required-fields + defaults only.
"""

import pytest
from api.schemas.domains.templates import (
    DuplicateTemplateRequest,
    NewTemplateRequest,
    TemplateDetailsResponse,
    TemplateEditRequest,
    TemplateResponse,
    TemplateResponseList,
    TemplateSetEnabledRequest,
    TemplateToDesktopRequest,
    TemplateTreeDomains,
    TemplateTreeResponse,
    UserAllowedTemplateFlatItem,
    UserTemplate,
    UserTemplateFilterParams,
    UserTemplatesResponse,
)
from pydantic import ValidationError


class TestUserTemplateFilterParams:
    def test_defaults_none(self):
        p = UserTemplateFilterParams()
        assert p.enabled is None


class TestUserTemplate:
    _required = {"id": "t-1", "name": "Tmpl", "enabled": True}

    def test_accepts_required(self):
        t = UserTemplate(**self._required)
        assert t.id == "t-1"
        assert t.image is None
        assert t.status is None
        assert t.progress is None

    @pytest.mark.parametrize("missing", ["id", "name", "enabled"])
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            UserTemplate(**payload)


class TestUserTemplatesResponse:
    def test_templates_required(self):
        with pytest.raises(ValidationError):
            UserTemplatesResponse()


class TestTemplateResponse:
    """Optional/None for many fields — the row may come from a sparsely
    populated DB document. Only id and name are required."""

    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_id_and_name_required(self, missing):
        payload = {
            "id": "t-1",
            "image": None,
            "name": "Tmpl",
            "description": None,
            "category": None,
            "group": None,
            "user": None,
            "user_name": None,
            "allowed": None,
        }
        del payload[missing]
        with pytest.raises(ValidationError):
            TemplateResponse(**payload)


class TestTemplateResponseList:
    def test_templates_required(self):
        with pytest.raises(ValidationError):
            TemplateResponseList()


class TestTemplateSetEnabledRequest:
    def test_enabled_required(self):
        with pytest.raises(ValidationError):
            TemplateSetEnabledRequest()

    def test_accepts_bool(self):
        assert TemplateSetEnabledRequest(enabled=True).enabled is True


class TestUserAllowedTemplateFlatItem:
    _required = {"id": "t-1", "name": "Tmpl"}

    def test_default_kind_template(self):
        """kind defaults to "template" — the helper uses this to
        distinguish allowed template lists from desktop lists."""
        i = UserAllowedTemplateFlatItem(**self._required)
        assert i.kind == "template"

    def test_extra_keys_allowed(self):
        """class Config: extra = 'allow' — full DB row passes through.
        Pin so a refactor flipping to extra='ignore' is loud."""
        i = UserAllowedTemplateFlatItem(**self._required, extra_field="x")
        assert i.model_dump()["extra_field"] == "x"


class TestTemplateEditRequest:
    """All five fields except `image` are required — the edit endpoint
    is a full-replace, not a partial update."""

    _required = {
        "name": "MyTmpl",
        "description": "x",
        "guest_properties": {},
        "hardware": {},
        "reservables": {"vgpus": None},
    }

    def test_accepts_required(self):
        r = TemplateEditRequest(**self._required)
        assert r.name == "MyTmpl"
        assert r.image is None

    def test_name_min_length_4(self):
        with pytest.raises(ValidationError):
            TemplateEditRequest(**{**self._required, "name": "abc"})

    def test_name_max_length_50(self):
        with pytest.raises(ValidationError):
            TemplateEditRequest(**{**self._required, "name": "x" * 51})

    def test_description_max_length_255(self):
        with pytest.raises(ValidationError):
            TemplateEditRequest(**{**self._required, "description": "x" * 256})

    @pytest.mark.parametrize(
        "missing",
        ["name", "description", "guest_properties", "hardware", "reservables"],
    )
    def test_required_fields(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            TemplateEditRequest(**payload)


class TestTemplateToDesktopRequest:
    def test_name_optional(self):
        """When name is omitted, the route uses the template's name —
        pin so that contract stays tolerant (default=None)."""
        r = TemplateToDesktopRequest()
        assert r.name is None

    def test_name_length_constraints_apply(self):
        """When name IS provided, length bounds enforce."""
        with pytest.raises(ValidationError):
            TemplateToDesktopRequest(name="abc")
        with pytest.raises(ValidationError):
            TemplateToDesktopRequest(name="x" * 51)


class TestNewTemplateRequest:
    _required = {
        "desktop_id": "d-1",
        "name": "NewTmpl",
        "description": "x",
        "allowed": {},
    }

    def test_accepts_required(self):
        r = NewTemplateRequest(**self._required)
        assert r.enabled is True  # default

    @pytest.mark.parametrize(
        "missing", ["desktop_id", "name", "description", "allowed"]
    )
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            NewTemplateRequest(**payload)

    def test_name_length_bounds(self):
        with pytest.raises(ValidationError):
            NewTemplateRequest(**{**self._required, "name": "abc"})
        with pytest.raises(ValidationError):
            NewTemplateRequest(**{**self._required, "name": "x" * 51})


class TestDuplicateTemplateRequest:
    _required = {"name": "DupTmpl", "description": "x", "allowed": {}}

    def test_accepts_required(self):
        r = DuplicateTemplateRequest(**self._required)
        assert r.enabled is True

    def test_name_length_bounds(self):
        with pytest.raises(ValidationError):
            DuplicateTemplateRequest(**{**self._required, "name": "abc"})


class TestTemplateTreeDomains:
    @pytest.mark.parametrize("missing", ["id", "kind", "name", "user"])
    def test_required(self, missing):
        payload = {"id": "x", "kind": "desktop", "name": "X", "user": "u-1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            TemplateTreeDomains(**payload)


class TestTemplateTreeResponse:
    _required = {"domains": [], "pending": False, "is_duplicated": False}

    def test_accepts_required(self):
        r = TemplateTreeResponse(**self._required)
        assert r.cross_category is False  # default
        assert r.deployments == []  # default_factory

    def test_deployments_default_factory(self):
        a = TemplateTreeResponse(**self._required)
        b = TemplateTreeResponse(**self._required)
        assert a.deployments is not b.deployments


class TestTemplateDetailsResponse:
    _required = {
        "name": "Tmpl",
        "boot_order": [{"id": "disk", "name": "Disk"}],
        "disk_bus": "virtio",
        "interfaces": [{"id": "net-1", "name": "default"}],
        "disks": [{"id": "s-1", "size": 10.0}],
        "videos": [{"id": "vga", "name": "VGA"}],
        "credentials": {"username": "u", "password": "p"},
    }

    def test_accepts_required(self):
        r = TemplateDetailsResponse(**self._required)
        assert r.name == "Tmpl"
        # vcpu/memory have defaults of 0 even though described as
        # required — pin the default.
        assert r.vcpu == 0
        assert r.memory == 0
        assert r.viewers == []
        assert r.fullscreen is False
