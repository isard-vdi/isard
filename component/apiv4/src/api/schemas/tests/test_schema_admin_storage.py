# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/admin_storage.py``."""

from api.schemas.admin_storage import AdminStorageFilterRequest


class TestAdminStorageFilterRequest:
    """Single-field filter — empty body is the "no filter" case."""

    def test_accepts_empty(self):
        r = AdminStorageFilterRequest()
        assert r.categories is None

    def test_accepts_categories_list(self):
        r = AdminStorageFilterRequest(categories=["cat-a", "cat-b"])
        assert r.categories == ["cat-a", "cat-b"]

    def test_accepts_empty_list(self):
        """Empty list is meaningful: "filter to nothing" — distinct from
        None which means "no filter". Pin both."""
        r = AdminStorageFilterRequest(categories=[])
        assert r.categories == []

    def test_round_trip(self):
        r = AdminStorageFilterRequest(categories=["x"])
        assert AdminStorageFilterRequest(**r.model_dump()) == r
