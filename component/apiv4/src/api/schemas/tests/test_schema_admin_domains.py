# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_domains.py``."""

import pytest
from api.schemas.admin_domains import (
    AdminDomainStoragePathData,
    AdminDomainXmlData,
    AdminListDomainsData,
    AdminLogsQueryData,
    AdminMultipleActionsData,
)
from pydantic import ValidationError


class TestAdminListDomainsData:
    def test_kind_default_desktop(self):
        d = AdminListDomainsData()
        assert d.kind == "desktop"
        assert d.categories is None
        assert d.domain_ids is None

    def test_kind_template(self):
        assert AdminListDomainsData(kind="template").kind == "template"

    def test_kind_literal_constraint(self):
        """kind is Literal['desktop', 'template'] — anything else fails."""
        with pytest.raises(ValidationError):
            AdminListDomainsData(kind="virtual_machine")

    def test_full(self):
        d = AdminListDomainsData(
            kind="template", categories="cat-a", domain_ids=["d-1", "d-2"]
        )
        assert d.domain_ids == ["d-1", "d-2"]


class TestAdminMultipleActionsData:
    _required = {"action": "stop", "ids": ["d-1", "d-2"]}

    def test_accepts_required(self):
        d = AdminMultipleActionsData(**self._required)
        assert d.action == "stop"
        assert d.ids == ["d-1", "d-2"]

    @pytest.mark.parametrize("missing", ["action", "ids"])
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminMultipleActionsData(**payload)


class TestAdminDomainXmlData:
    def test_xml_optional(self):
        """xml: Optional[dict] — None is "no update". Pin so a route
        that gates on `if data.xml is not None:` still works."""
        assert AdminDomainXmlData().xml is None
        assert AdminDomainXmlData(xml=None).xml is None

    def test_accepts_dict(self):
        assert AdminDomainXmlData(xml={"name": "test"}).xml == {"name": "test"}


class TestAdminDomainStoragePathData:
    _required = {"old_path": "/old", "new_path": "/new"}

    @pytest.mark.parametrize("missing", ["old_path", "new_path"])
    def test_both_paths_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            AdminDomainStoragePathData(**payload)

    def test_round_trip(self):
        d = AdminDomainStoragePathData(**self._required)
        assert AdminDomainStoragePathData(**d.model_dump()) == d


class TestAdminLogsQueryData:
    """Empty placeholder schema — accepts any body for datatables-style
    queries. Pin so a future tightening to a specific shape is
    intentional and updates the routes that rely on this tolerance."""

    def test_accepts_empty(self):
        d = AdminLogsQueryData()
        assert d.model_dump() == {}

    def test_extra_fields_dropped(self):
        d = AdminLogsQueryData(draw=1, start=0, length=10)
        assert d.model_dump() == {}
