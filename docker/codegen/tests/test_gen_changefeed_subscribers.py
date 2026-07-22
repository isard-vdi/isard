# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for the changefeed subscriber generator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gen_changefeed_subscribers import (
    _camel,
    _header,
    _init_source,
    _subscriber_source,
    generate,
    main,
)

_FAKE_HASH = "aabbccddeeff"


class TestSubscriberSource:
    def test_contains_class_name(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        assert "class DomainsSubscriber:" in src

    def test_imports_correct_envelope(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        assert (
            "from changefeed_models.domains_change_envelope import DomainsChangeEnvelope"
            in src
        )

    def test_parse_return_type(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        assert "-> DomainsChangeEnvelope:" in src

    def test_stream_attribute_present(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        assert 'STREAM: str = "stream:domains"' in src

    def test_stream_attribute_absent(self):
        src = _subscriber_source("bookings", has_stream=False, tables_hash=_FAKE_HASH)
        assert "STREAM" not in src

    def test_table_attribute(self):
        src = _subscriber_source(
            "user_storage", has_stream=False, tables_hash=_FAKE_HASH
        )
        assert 'TABLE: str = "user_storage"' in src

    def test_channel_attribute(self):
        src = _subscriber_source("hypervisors", has_stream=True, tables_hash=_FAKE_HASH)
        assert 'CHANNEL: str = "hypervisors"' in src

    def test_serialize_uses_correct_table(self):
        src = _subscriber_source("media", has_stream=True, tables_hash=_FAKE_HASH)
        assert '"table": "media"' in src

    def test_snake_case_table(self):
        src = _subscriber_source("qos_disk", has_stream=False, tables_hash=_FAKE_HASH)
        assert "class QosDiskSubscriber:" in src
        assert (
            "from changefeed_models.qos_disk_change_envelope import QosDiskChangeEnvelope"
            in src
        )

    def test_is_valid_python(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        compile(src, "<test>", "exec")

    def test_no_stream_is_valid_python(self):
        src = _subscriber_source("bookings", has_stream=False, tables_hash=_FAKE_HASH)
        compile(src, "<test>", "exec")

    def test_header_contains_hash(self):
        src = _subscriber_source("domains", has_stream=True, tables_hash=_FAKE_HASH)
        assert f"# tables.json sha256: {_FAKE_HASH}" in src

    def test_generated_serialize_does_not_exclude_none(self):
        """Serialized delete events must keep ``new_val: null`` in the JSON.

        The template must not pass ``exclude_none=True`` to
        ``model_dump_json``; otherwise ``new_val = None`` gets stripped on
        delete events, producing output that is incompatible with the
        AsyncAPI schema (which declares ``new_val`` as nullable).
        """
        src = _subscriber_source(
            table="media", has_stream=False, tables_hash=_FAKE_HASH
        )
        assert (
            "exclude_none=True" not in src
        ), "Generated serialize() drops new_val=None on delete events"

    def test_serialize_roundtrip_delete_keeps_new_val_null(self, tmp_path):
        """Load the generated subscriber source dynamically and assert that
        ``serialize`` on a delete event preserves ``new_val: null`` in the
        emitted JSON.

        This test imports the **real** generated envelope tree at
        ``pkg/gen/asyncapi/changefeed/changefeed_models/`` (gitignored
        codegen output, but present locally after a codegen run). That
        envelope ships a ``@model_serializer(mode='wrap')`` custom
        serializer plus an ``additional_properties`` field, so the test
        exercises the real wrap-handler interaction rather than a plain
        pydantic stub. If the real tree is absent (e.g. fresh clone
        without codegen), the test is skipped — we deliberately avoid
        mirroring the wrap serializer in a stub to prevent it drifting
        out of sync with the generator's output.
        """
        import importlib.util
        import sys

        changefeed_models_dir = (
            Path(__file__).resolve().parents[3]
            / "pkg"
            / "gen"
            / "asyncapi"
            / "changefeed"
            / "changefeed_models"
        )
        if not (changefeed_models_dir / "media_change_envelope.py").is_file():
            pytest.skip("Real changefeed_models/ tree not present; run codegen first.")

        src = _subscriber_source(
            table="media", has_stream=False, tables_hash=_FAKE_HASH
        )

        module_path = tmp_path / "gen_media_subscriber.py"
        module_path.write_text(src)

        # Parent of ``changefeed_models/`` goes on sys.path so the
        # template's ``from changefeed_models.media_change_envelope
        # import MediaChangeEnvelope`` resolves to the real generated
        # module (with its @model_serializer(mode='wrap')).
        real_parent = str(changefeed_models_dir.parent)
        sys.path.insert(0, real_parent)
        sys.path.insert(0, str(tmp_path))
        try:
            spec = importlib.util.spec_from_file_location(
                "gen_media_subscriber", module_path
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            Subscriber = module.MediaSubscriber
            out = Subscriber.serialize({"new_val": None, "old_val": {"id": "m1"}})
        finally:
            sys.path.remove(str(tmp_path))
            sys.path.remove(real_parent)
            for mod_name in list(sys.modules):
                if mod_name == "gen_media_subscriber" or mod_name.startswith(
                    "changefeed_models"
                ):
                    sys.modules.pop(mod_name, None)

        data = json.loads(out)
        assert "change" in data
        assert (
            "new_val" in data["change"]
        ), "new_val must be present in serialized delete event JSON"
        assert data["change"]["new_val"] is None
        # The real envelope types old_val as MediaRow, so pydantic expands
        # it with every MediaRow field populated from defaults. We only
        # care that the id round-trips; the rest is MediaRow's concern.
        assert data["change"]["old_val"]["id"] == "m1"


class TestInitSource:
    def test_contains_all_imports(self):
        tables = [{"table": "foo"}, {"table": "bar"}]
        src = _init_source(tables, tables_hash=_FAKE_HASH)
        assert "from changefeed_subscribers.foo import FooSubscriber" in src
        assert "from changefeed_subscribers.bar import BarSubscriber" in src

    def test_contains_table_to_subscriber(self):
        tables = [{"table": "foo"}, {"table": "bar"}]
        src = _init_source(tables, tables_hash=_FAKE_HASH)
        assert "TABLE_TO_SUBSCRIBER" in src
        assert '"foo": FooSubscriber' in src
        assert '"bar": BarSubscriber' in src

    def test_sorted_alphabetically(self):
        tables = [{"table": "zzz"}, {"table": "aaa"}]
        src = _init_source(tables, tables_hash=_FAKE_HASH)
        aaa_pos = src.index("AaaSubscriber")
        zzz_pos = src.index("ZzzSubscriber")
        assert aaa_pos < zzz_pos

    def test_is_valid_python(self):
        tables = [{"table": "foo"}, {"table": "bar", "stream": True}]
        src = _init_source(tables, tables_hash=_FAKE_HASH)
        compile(src, "<test>", "exec")

    def test_header_contains_hash(self):
        tables = [{"table": "foo"}]
        src = _init_source(tables, tables_hash=_FAKE_HASH)
        assert f"# tables.json sha256: {_FAKE_HASH}" in src


class TestGenerate:
    def test_creates_files_per_table(self, tmp_path):
        tables = [
            {"table": "foo"},
            {"table": "bar", "stream": True},
        ]
        generate(tables, tmp_path, _FAKE_HASH)

        assert (tmp_path / "foo.py").is_file()
        assert (tmp_path / "bar.py").is_file()
        assert (tmp_path / "__init__.py").is_file()

    def test_file_count(self, tmp_path):
        tables = [{"table": f"t{i}"} for i in range(5)]
        generate(tables, tmp_path, _FAKE_HASH)

        py_files = list(tmp_path.glob("*.py"))
        assert len(py_files) == 6  # 5 tables + __init__.py

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "nested" / "deep"
        generate([{"table": "foo"}], out, _FAKE_HASH)
        assert out.is_dir()
        assert (out / "foo.py").is_file()

    def test_stream_attribute_only_for_stream_tables(self, tmp_path):
        tables = [
            {"table": "with_stream", "stream": True},
            {"table": "without_stream"},
        ]
        generate(tables, tmp_path, _FAKE_HASH)

        with_src = (tmp_path / "with_stream.py").read_text()
        without_src = (tmp_path / "without_stream.py").read_text()

        assert "STREAM" in with_src
        assert "STREAM" not in without_src

    def test_all_files_are_valid_python(self, tmp_path):
        tables = [
            {"table": "domains", "stream": True},
            {"table": "users", "stream": True},
            {"table": "bookings"},
            {"table": "qos_net"},
        ]
        generate(tables, tmp_path, _FAKE_HASH)

        for py_file in tmp_path.glob("*.py"):
            src = py_file.read_text()
            compile(src, str(py_file), "exec")

    def test_files_contain_hash(self, tmp_path):
        generate([{"table": "foo"}], tmp_path, _FAKE_HASH)
        for py_file in tmp_path.glob("*.py"):
            assert f"# tables.json sha256: {_FAKE_HASH}" in py_file.read_text()


class TestIdempotency:
    def test_two_runs_produce_identical_output(self, tmp_path):
        tables = [
            {"table": "domains", "stream": True},
            {"table": "users"},
            {"table": "vgpus"},
        ]
        dir1 = tmp_path / "run1"
        dir2 = tmp_path / "run2"

        generate(tables, dir1, _FAKE_HASH)
        generate(tables, dir2, _FAKE_HASH)

        for f in dir1.glob("*.py"):
            assert f.read_text() == (dir2 / f.name).read_text()


class TestRealTablesJson:
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

    def test_generates_one_subscriber_file_per_table(self, real_tables, tmp_path):
        generate(real_tables, tmp_path, _FAKE_HASH)

        subscriber_files = [f for f in tmp_path.glob("*.py") if f.name != "__init__.py"]
        assert len(subscriber_files) == len(real_tables)

    def test_stream_subscribers_match_stream_tables(self, real_tables, tmp_path):
        generate(real_tables, tmp_path, _FAKE_HASH)

        stream_tables = []
        for entry in real_tables:
            if entry.get("stream"):
                src = (tmp_path / f"{entry['table']}.py").read_text()
                if "STREAM" in src:
                    stream_tables.append(entry["table"])

        expected = sum(1 for entry in real_tables if entry.get("stream"))
        assert len(stream_tables) == expected

    def test_all_generated_files_compile(self, real_tables, tmp_path):
        generate(real_tables, tmp_path, _FAKE_HASH)

        for py_file in tmp_path.glob("*.py"):
            src = py_file.read_text()
            compile(src, str(py_file), "exec")


class TestMainCli:
    def test_writes_files(self, tmp_path, monkeypatch):
        tables_file = tmp_path / "tables.json"
        tables_file.write_text(
            json.dumps([{"table": "foo"}, {"table": "bar", "stream": True}])
        )
        output_dir = tmp_path / "out"

        monkeypatch.setattr(
            "sys.argv",
            [
                "gen_changefeed_subscribers.py",
                "--tables",
                str(tables_file),
                "--output-dir",
                str(output_dir),
            ],
        )
        rc = main()

        assert rc == 0
        assert (output_dir / "foo.py").is_file()
        assert (output_dir / "bar.py").is_file()
        assert (output_dir / "__init__.py").is_file()
