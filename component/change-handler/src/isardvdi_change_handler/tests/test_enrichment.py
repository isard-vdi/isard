# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the model_copy + additional_properties enrichment pattern."""

import json

from isardvdi_change_handler.handlers.base import json_dumps
from isardvdi_change_handler.tests.conftest import FakeRow


class TestEnrichmentPattern:
    def test_model_copy_adds_to_additional_properties(self):
        original = FakeRow(id="r1", name="test")
        enriched = original.model_copy()
        enriched.additional_properties = {"role_name": "admin"}

        dumped = enriched.model_dump(exclude_none=True)
        assert dumped["id"] == "r1"
        assert dumped["role_name"] == "admin"

    def test_enrichment_preserves_existing_additional_properties(self):
        original = FakeRow(
            id="r1",
            additional_properties={"existing": "value"},
        )
        enriched = original.model_copy()
        enriched.additional_properties = {
            **(original.additional_properties or {}),
            "new_field": "added",
        }

        dumped = enriched.model_dump(exclude_none=True)
        assert dumped["existing"] == "value"
        assert dumped["new_field"] == "added"

    def test_enrichment_does_not_mutate_original(self):
        original = FakeRow(id="r1")
        enriched = original.model_copy()
        enriched.additional_properties = {"extra": True}

        assert original.additional_properties is None
        assert enriched.additional_properties == {"extra": True}

    def test_json_dumps_includes_enriched_fields(self):
        row = FakeRow(id="r1", status="active")
        enriched = row.model_copy()
        enriched.additional_properties = {"editable": True, "score": 42}

        result = json.loads(json_dumps(enriched))
        assert result["id"] == "r1"
        assert result["status"] == "active"
        assert result["editable"] is True
        assert result["score"] == 42

    def test_json_dumps_nested_in_dict(self):
        row = FakeRow(id="r1")
        enriched = row.model_copy()
        enriched.additional_properties = {"extra": "yes"}

        result = json.loads(json_dumps({"table": "test", "data": enriched}))
        assert result["table"] == "test"
        assert result["data"]["id"] == "r1"
        assert result["data"]["extra"] == "yes"

    def test_model_copy_update_overrides_field(self):
        row = FakeRow(id="r1", status="active", name="original")
        updated = row.model_copy(update={"status": None})

        assert updated.status is None
        assert updated.name == "original"
        assert updated.id == "r1"

    def test_enrichment_does_not_overwrite_model_fields(self):
        row = FakeRow(id="r1", name="model_name")
        enriched = row.model_copy()
        enriched.additional_properties = {"name": "should_not_override"}

        dumped = enriched.model_dump(exclude_none=True)
        assert dumped["name"] == "model_name"

    def test_unknown_fields_captured_via_validator(self):
        row = FakeRow.model_validate({"id": "r1", "unknown_field": "captured"})
        assert row.id == "r1"
        assert row.additional_properties == {"unknown_field": "captured"}

        dumped = row.model_dump(exclude_none=True)
        assert dumped["unknown_field"] == "captured"
