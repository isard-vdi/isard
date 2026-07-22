# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the isard-changefeed AsyncAPI generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional, Union

import pytest
import yaml
from gen_changefeed_asyncapi import (
    TABLE_TO_CLASS,
    _camel,
    _change_schema,
    _envelope_schema,
    _nullable_row_schema,
    _permissive_row_schema,
    _row_schema_from_model,
    _try_load_model,
    _type_to_schema,
    build_spec,
    main,
)
from pydantic import BaseModel


class TestTypeToSchema:
    def test_str(self):
        assert _type_to_schema(str) == {"type": "string"}

    def test_int(self):
        assert _type_to_schema(int) == {"type": "integer"}

    def test_float(self):
        assert _type_to_schema(float) == {"type": "number"}

    def test_bool(self):
        assert _type_to_schema(bool) == {"type": "boolean"}

    def test_none_type(self):
        assert _type_to_schema(type(None)) == {"type": "null"}

    def test_any(self):
        assert _type_to_schema(Any) == {}

    def test_object(self):
        assert _type_to_schema(object) == {}

    def test_optional_str(self):
        assert _type_to_schema(Optional[str]) == {
            "oneOf": [{"type": "string"}, {"type": "null"}]
        }

    def test_optional_int(self):
        assert _type_to_schema(Optional[int]) == {
            "oneOf": [{"type": "integer"}, {"type": "null"}]
        }

    def test_union_str_int(self):
        assert _type_to_schema(Union[str, int]) == {
            "oneOf": [{"type": "string"}, {"type": "integer"}]
        }

    def test_union_str_int_none(self):
        assert _type_to_schema(Union[str, int, None]) == {
            "oneOf": [
                {"type": "string"},
                {"type": "integer"},
                {"type": "null"},
            ]
        }

    def test_pipe_union_str_none(self):
        # PEP 604 union syntax (Python 3.10+)
        assert _type_to_schema(str | None) == {
            "oneOf": [{"type": "string"}, {"type": "null"}]
        }

    def test_list_generic(self):
        assert _type_to_schema(list[str]) == {"type": "array"}

    def test_list_plain(self):
        # Plain `list` (no args) has no origin, so it falls through to the
        # permissive schema.
        assert _type_to_schema(list) == {}

    def test_tuple(self):
        assert _type_to_schema(tuple[int, str]) == {"type": "array"}

    def test_set(self):
        assert _type_to_schema(set[str]) == {"type": "array"}

    def test_dict_permissive(self):
        assert _type_to_schema(dict[str, Any]) == {
            "type": "object",
            "additionalProperties": True,
        }

    def test_nested_basemodel_degrades_to_permissive(self):
        class Nested(BaseModel):
            x: str

        assert _type_to_schema(Nested) == {
            "type": "object",
            "additionalProperties": True,
        }

    def test_literal_str(self):
        assert _type_to_schema(Literal["a", "b"]) == {"type": "string"}

    def test_literal_int(self):
        assert _type_to_schema(Literal[1, 2, 3]) == {"type": "integer"}

    def test_literal_bool(self):
        assert _type_to_schema(Literal[True, False]) == {"type": "boolean"}

    def test_unknown_type_degrades_to_empty(self):
        class Custom:
            pass

        assert _type_to_schema(Custom) == {}


class TestRowSchemaFromModel:
    def test_basic_fields(self):
        class FakeRow(BaseModel):
            id: str
            count: int
            rate: Optional[float] = None

        schema = _row_schema_from_model(FakeRow)

        assert schema["type"] == "object"
        assert schema["additionalProperties"] is True
        assert schema["properties"]["id"] == {"type": "string"}
        assert schema["properties"]["count"] == {"type": "integer"}
        assert schema["properties"]["rate"] == {
            "oneOf": [{"type": "number"}, {"type": "null"}]
        }

    def test_table_field_added_when_missing(self):
        class FakeRow(BaseModel):
            id: str

        schema = _row_schema_from_model(FakeRow)

        # The changefeed publisher merges {"table": ...} into every row
        # before publishing, so the schema must expose it regardless of
        # whether the source Pydantic model declares it.
        assert "table" in schema["properties"]
        assert schema["properties"]["table"] == {"type": "string"}

    def test_existing_table_field_kept_intact(self):
        # If the source model already declares ``table`` (e.g. with a
        # tighter type annotation) the generator must not clobber it via
        # ``setdefault``.
        class FakeRow(BaseModel):
            table: Literal["domains"] = "domains"

        schema = _row_schema_from_model(FakeRow)

        # Literal[str] collapses to {"type": "string"} in _type_to_schema;
        # the point is we didn't overwrite it with a fresh "string" dict.
        assert schema["properties"]["table"] == {"type": "string"}

    def test_no_required_fields_emitted(self):
        # Plucked rows drop fields, so every field must be optional on the
        # wire regardless of the Pydantic source declaration.
        class FakeRow(BaseModel):
            id: str  # Required in Pydantic

        schema = _row_schema_from_model(FakeRow)

        assert "required" not in schema


class TestPermissiveRowSchema:
    def test_structure(self):
        schema = _permissive_row_schema()

        assert schema["type"] == "object"
        assert schema["additionalProperties"] is True
        assert schema["properties"] == {"table": {"type": "string"}}


class TestNullableRowSchema:
    def test_oneOf_ref_and_null(self):
        # Naming the wrapper (rather than inlining oneOf inside _change_schema)
        # is the regression guard against modelina's "anonymous_schema_N
        # → AnyModel" warnings that wiped out new_val / old_val typing.
        schema = _nullable_row_schema("DomainsRow")

        variants = schema["oneOf"]
        assert {"$ref": "#/components/schemas/DomainsRow"} in variants
        assert {"type": "null"} in variants


class TestChangeSchema:
    def test_has_old_and_new_val(self):
        schema = _change_schema("NullableDomainsRow")

        assert schema["type"] == "object"
        assert "new_val" in schema["properties"]
        assert "old_val" in schema["properties"]

    def test_both_values_reference_nullable_row(self):
        schema = _change_schema("NullableDomainsRow")

        for key in ("new_val", "old_val"):
            assert schema["properties"][key] == {
                "$ref": "#/components/schemas/NullableDomainsRow"
            }


class TestEnvelopeSchema:
    def test_has_table_and_change_required(self):
        schema = _envelope_schema("domains", "DomainsChange")

        assert schema["type"] == "object"
        assert schema["required"] == ["change", "table"]
        assert "table" in schema["properties"]
        assert "change" in schema["properties"]

    def test_change_is_ref(self):
        schema = _envelope_schema("domains", "DomainsChange")

        assert schema["properties"]["change"] == {
            "$ref": "#/components/schemas/DomainsChange"
        }

    def test_no_const_on_table_field(self):
        # Regression guard: modelina (the asyncapi CLI's python model
        # generator) emits ``Field(default=''domains'')`` — invalid Python
        # — when the schema uses ``const``. We must use plain ``type:
        # string`` and let the helper dispatch by table name at runtime.
        schema = _envelope_schema("domains", "DomainsChange")

        assert "const" not in schema["properties"]["table"]

    def test_no_enum_on_table_field(self):
        # Regression guard: ``enum: [<name>]`` makes modelina spawn a
        # ``AnonymousSchemaXXX`` enum class per table, cluttering the
        # generated package.
        schema = _envelope_schema("domains", "DomainsChange")

        assert "enum" not in schema["properties"]["table"]

    def test_table_field_has_plain_string_type(self):
        schema = _envelope_schema("domains", "DomainsChange")

        assert schema["properties"]["table"]["type"] == "string"


class TestTryLoadModel:
    def test_nonexistent_module_raises(self):
        with pytest.raises(RuntimeError, match="Failed to load"):
            _try_load_model("__definitely_does_not_exist__", "Foo")

    def test_nonexistent_class_raises(self, monkeypatch):
        # Fake a loaded module without the requested attribute to exercise
        # the ``getattr`` branch of the try/except.
        fake = type("FakeModule", (), {})()

        def fake_import(name):
            if name == "isardvdi_common.models.fake_module":
                return fake
            raise ModuleNotFoundError(name)

        monkeypatch.setattr(
            "gen_changefeed_asyncapi.importlib.import_module", fake_import
        )

        with pytest.raises(RuntimeError, match="Failed to load"):
            _try_load_model("fake_module", "NotThere")

    def test_module_level_side_effect_raises(self, monkeypatch):
        # Simulate the ``isardvdi_common.models.domain:57`` case where
        # module import triggers ``isard_viewer = IsardViewer()``. The
        # generator must fail loud so the offending model gets fixed
        # rather than silently emitting a permissive schema.
        def failing_import(name):
            if name == "isardvdi_common.models.domain":
                raise RuntimeError("simulated IsardViewer init failure")
            raise ModuleNotFoundError(name)

        monkeypatch.setattr(
            "gen_changefeed_asyncapi.importlib.import_module", failing_import
        )

        with pytest.raises(RuntimeError, match="Failed to load"):
            _try_load_model("domain", "DomainModel")

    def test_successful_import_returns_class(self, monkeypatch):
        class GoodModel(BaseModel):
            id: str

        fake_module = type("FakeModule", (), {"GoodModel": GoodModel})()

        def fake_import(name):
            if name == "isardvdi_common.models.good_test_model":
                return fake_module
            raise ModuleNotFoundError(name)

        monkeypatch.setattr(
            "gen_changefeed_asyncapi.importlib.import_module", fake_import
        )

        cls = _try_load_model("good_test_model", "GoodModel")
        assert cls is GoodModel


class TestBuildSpec:
    """Integration tests for ``build_spec`` with synthetic tables.json."""

    def test_top_level_keys(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo"}])

        assert spec["asyncapi"] == "3.0.0"
        assert "info" in spec
        assert "servers" in spec
        assert "channels" in spec
        assert "operations" in spec
        assert "components" in spec
        assert "messages" in spec["components"]
        assert "schemas" in spec["components"]

    def test_pubsub_channel_per_table(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo"}, {"table": "bar"}])

        assert "foo" in spec["channels"]
        assert "bar" in spec["channels"]
        assert spec["channels"]["foo"]["address"] == "foo"
        assert spec["channels"]["bar"]["address"] == "bar"

    def test_stream_tables_get_extra_channel(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo", "stream": True}, {"table": "bar"}])

        assert "stream_foo" in spec["channels"]
        assert spec["channels"]["stream_foo"]["address"] == "stream:foo"
        assert "stream_bar" not in spec["channels"]

    def test_operation_per_pubsub_channel(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo"}])

        assert "publishFoo" in spec["operations"]
        op = spec["operations"]["publishFoo"]
        assert op["action"] == "send"
        assert op["channel"] == {"$ref": "#/channels/foo"}

    def test_operation_per_stream_channel(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo", "stream": True}])

        assert "publishFoo" in spec["operations"]
        assert "publishStreamFoo" in spec["operations"]
        stream_op = spec["operations"]["publishStreamFoo"]
        assert stream_op["channel"] == {"$ref": "#/channels/stream_foo"}

    def test_message_per_table(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo"}])

        assert "FooChangeEnvelope" in spec["components"]["messages"]
        msg = spec["components"]["messages"]["FooChangeEnvelope"]
        assert msg["payload"] == {"$ref": "#/components/schemas/FooChangeEnvelope"}

    def test_four_schemas_per_table(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "foo"}])

        schemas = spec["components"]["schemas"]
        assert "FooRow" in schemas
        assert "NullableFooRow" in schemas
        assert "FooChange" in schemas
        assert "FooChangeEnvelope" in schemas

    def test_permissive_row_for_unknown_table(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec([{"table": "unknown_table"}])

        row = spec["components"]["schemas"]["UnknownTableRow"]
        assert row["additionalProperties"] is True
        assert row["properties"] == {"table": {"type": "string"}}

    def test_model_import_failure_fails_loud(self, monkeypatch):
        # A table wired in TABLE_TO_CLASS but pointing to a non-existent
        # module must fail loud so the offending model gets fixed or
        # removed from TABLE_TO_CLASS — silent fallback to a permissive
        # schema would hide real bugs in the model imports.
        monkeypatch.setattr(
            "gen_changefeed_asyncapi.TABLE_TO_CLASS",
            {"broken": ("__missing_module__", "DoesNotExist")},
        )

        with pytest.raises(RuntimeError, match="Failed to load"):
            build_spec([{"table": "broken"}])

    def test_typed_model_produces_typed_row_schema(self, monkeypatch):
        class FakeRowModel(BaseModel):
            id: str
            count: int
            name: Optional[str] = None

        monkeypatch.setattr(
            "gen_changefeed_asyncapi.TABLE_TO_CLASS",
            {"typed": ("test_fake", "FakeRowModel")},
        )
        monkeypatch.setattr(
            "gen_changefeed_asyncapi._try_load_model",
            lambda module_name, class_name: (
                FakeRowModel if module_name == "test_fake" else None
            ),
        )

        spec = build_spec([{"table": "typed"}])

        row = spec["components"]["schemas"]["TypedRow"]
        assert row["properties"]["id"] == {"type": "string"}
        assert row["properties"]["count"] == {"type": "integer"}
        assert row["properties"]["name"] == {
            "oneOf": [{"type": "string"}, {"type": "null"}]
        }
        # The publisher-injected ``table`` field must always be present.
        assert "table" in row["properties"]


class TestIdempotency:
    """``build_spec`` must be deterministic for a given input."""

    def test_two_calls_produce_identical_dict(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        tables = [
            {"table": "domains", "stream": True},
            {"table": "users"},
            {"table": "vgpus"},
        ]

        spec1 = build_spec(tables)
        spec2 = build_spec(tables)

        assert spec1 == spec2

    def test_yaml_dump_is_byte_identical(self, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        tables = [{"table": "foo", "stream": True}, {"table": "bar"}]
        spec = build_spec(tables)

        dump1 = yaml.safe_dump(spec, sort_keys=True, default_flow_style=False)
        dump2 = yaml.safe_dump(spec, sort_keys=True, default_flow_style=False)

        assert dump1 == dump2


class TestRealTablesJson:
    """Smoke test against the real ``tables.json`` shipped with changefeed."""

    @pytest.fixture
    def real_tables(self):
        tables_path = (
            Path(__file__).resolve().parents[3]
            / "component"
            / "changefeed"
            / "src"
            / "isardvdi_changefeed"
            / "tables.json"
        )
        with tables_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_real_tables_json_relationships(self, real_tables):
        # Every entry has a string `table` field
        assert all(
            isinstance(t, dict) and isinstance(t.get("table"), str) for t in real_tables
        )

        # Table names are unique
        names = [t["table"] for t in real_tables]
        assert len(names) == len(set(names))

    def test_stream_tables_are_subset(self, real_tables):
        # Stream tables declare `stream: true` explicitly
        streams = [t for t in real_tables if t.get("stream")]
        assert all(isinstance(t["stream"], bool) for t in real_tables if "stream" in t)
        # Every stream table must also appear in the real table set
        stream_names = {t["table"] for t in streams}
        assert stream_names <= {t["table"] for t in real_tables}

    def test_build_spec_counts(self, monkeypatch, real_tables):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})
        spec = build_spec(real_tables)

        table_count = len(real_tables)
        stream_count = sum(1 for t in real_tables if t.get("stream"))

        # One message per table
        assert len(spec["components"]["messages"]) == table_count
        # One channel per table + one per stream table
        assert len(spec["channels"]) == table_count + stream_count
        # One operation per channel
        assert len(spec["operations"]) == table_count + stream_count
        # Four schemas per table (Row + NullableRow + Change + Envelope)
        assert len(spec["components"]["schemas"]) == 4 * table_count

    def test_every_table_has_its_four_schemas(self, monkeypatch, real_tables):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        spec = build_spec(real_tables)
        schemas = spec["components"]["schemas"]

        for entry in real_tables:
            camel = _camel(entry["table"])
            assert f"{camel}Row" in schemas
            assert f"Nullable{camel}Row" in schemas
            assert f"{camel}Change" in schemas
            assert f"{camel}ChangeEnvelope" in schemas


class TestMainCli:
    """Test the ``main()`` CLI entry point end-to-end."""

    def test_writes_valid_yaml_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        tables_file = tmp_path / "tables.json"
        tables_file.write_text(
            json.dumps([{"table": "foo"}, {"table": "bar", "stream": True}])
        )
        output_file = tmp_path / "out" / "changefeed.yaml"

        monkeypatch.setattr(
            "sys.argv",
            [
                "gen_changefeed_asyncapi.py",
                "--tables",
                str(tables_file),
                "--output",
                str(output_file),
            ],
        )
        rc = main()

        assert rc == 0
        assert output_file.is_file()

        # The file must round-trip through yaml.safe_load.
        with output_file.open("r") as fh:
            spec = yaml.safe_load(fh)

        assert spec["asyncapi"] == "3.0.0"
        assert "foo" in spec["channels"]
        assert "stream_bar" in spec["channels"]

    def test_output_parent_dir_is_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        tables_file = tmp_path / "tables.json"
        tables_file.write_text(json.dumps([{"table": "foo"}]))
        output_file = tmp_path / "nested" / "deeply" / "changefeed.yaml"

        monkeypatch.setattr(
            "sys.argv",
            [
                "gen_changefeed_asyncapi.py",
                "--tables",
                str(tables_file),
                "--output",
                str(output_file),
            ],
        )
        main()

        assert output_file.is_file()

    def test_main_idempotent_on_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gen_changefeed_asyncapi.TABLE_TO_CLASS", {})

        tables_file = tmp_path / "tables.json"
        tables_file.write_text(
            json.dumps([{"table": "a", "stream": True}, {"table": "b"}])
        )
        out1 = tmp_path / "run1.yaml"
        out2 = tmp_path / "run2.yaml"

        for out in (out1, out2):
            monkeypatch.setattr(
                "sys.argv",
                [
                    "gen_changefeed_asyncapi.py",
                    "--tables",
                    str(tables_file),
                    "--output",
                    str(out),
                ],
            )
            main()

        assert out1.read_bytes() == out2.read_bytes()


class TestTableToClassRegistry:
    """Guardrails on the ``TABLE_TO_CLASS`` mapping constant."""

    def test_registry_is_non_empty(self):
        assert len(TABLE_TO_CLASS) > 0

    def test_every_value_is_module_class_tuple(self):
        for table, value in TABLE_TO_CLASS.items():
            assert isinstance(value, tuple), f"{table} value is not a tuple"
            assert len(value) == 2
            module_name, class_name = value
            assert isinstance(module_name, str) and module_name
            assert isinstance(class_name, str) and class_name
