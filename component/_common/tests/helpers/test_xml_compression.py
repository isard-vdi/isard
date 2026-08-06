#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``isardvdi_common.helpers.xml_compression``.

Exercises the round-trip, the legacy str passthrough, the threshold,
the magic-header guard, the bytes idempotency, and the atomic
``r.branch`` shape emitted by ``lazy_compress_in_place``.
"""

from unittest.mock import MagicMock

import pytest
import zstandard as zstd
from isardvdi_common.helpers import xml_compression as mod

_BIG_XML = "<domain>" + ("<disk dev='vda'/>" * 200) + "</domain>"
_SMALL_XML = "<domain/>"


class TestRoundTrip:
    def test_compress_then_decompress_recovers_original(self):
        wrapped = mod.compress_xml(_BIG_XML)
        # ``compress_xml`` returns ``r.binary(...)`` for compressed
        # payloads, which a real driver round-trips back as ``bytes`` on
        # the read side. Pull the underlying bytes via the ReQL term
        # data and feed it through ``decompress_xml`` to mirror what a
        # caller sees coming back from rdb.
        compressed_bytes = _unwrap_binary(wrapped)
        assert compressed_bytes[:4] == mod.ZSTD_MAGIC
        assert mod.decompress_xml(compressed_bytes) == _BIG_XML

    def test_decompress_str_passthrough(self):
        assert mod.decompress_xml("<domain/>") == "<domain/>"

    def test_decompress_none(self):
        assert mod.decompress_xml(None) is None

    def test_compress_none(self):
        assert mod.compress_xml(None) is None

    def test_compress_empty_string_passthrough(self):
        # Below threshold (0 bytes) → returned unchanged so callers
        # don't have to special-case the empty string.
        assert mod.compress_xml("") == ""


class TestThreshold:
    def test_compress_short_returns_str_unchanged(self):
        assert mod.compress_xml(_SMALL_XML) == _SMALL_XML

    def test_compress_above_threshold_returns_binary(self):
        wrapped = mod.compress_xml(_BIG_XML)
        # Anything that isn't a plain ``str``/``None`` is the binary
        # ReQL term. Verify it's not the original string back.
        assert not isinstance(wrapped, str)
        assert wrapped is not None


class TestIsCompressed:
    def test_zstd_magic_bytes_returns_true(self):
        compressed = zstd.ZstdCompressor(level=3).compress(_BIG_XML.encode())
        assert mod.is_compressed(compressed) is True

    def test_str_returns_false(self):
        assert mod.is_compressed(_BIG_XML) is False

    def test_none_returns_false(self):
        assert mod.is_compressed(None) is False

    def test_other_bytes_returns_false(self):
        assert mod.is_compressed(b"<not-zstd>") is False

    def test_short_bytes_returns_false(self):
        assert mod.is_compressed(b"\x28") is False


class TestDecompressGuards:
    def test_bytes_without_magic_returns_utf8_decoded(self, caplog):
        # Defensive path: a corrupted / hand-injected byte string is
        # logged but still decoded so the read doesn't blow up.
        with caplog.at_level("WARNING"):
            assert mod.decompress_xml(b"<domain/>") == "<domain/>"
        assert any("missing zstd magic" in rec.message for rec in caplog.records)

    def test_bytearray_round_trip(self):
        compressed = zstd.ZstdCompressor(level=3).compress(_BIG_XML.encode())
        assert mod.decompress_xml(bytearray(compressed)) == _BIG_XML

    def test_memoryview_round_trip(self):
        compressed = zstd.ZstdCompressor(level=3).compress(_BIG_XML.encode())
        assert mod.decompress_xml(memoryview(compressed)) == _BIG_XML

    def test_decompress_rejects_unsupported_type(self):
        with pytest.raises(TypeError):
            mod.decompress_xml(123)


class TestCompressGuards:
    def test_compress_bytes_idempotent(self):
        # Pre-compressed bytes (e.g. re-staging a value already read
        # from rdb) must pass through untouched — otherwise we'd
        # double-compress.
        raw = zstd.ZstdCompressor(level=3).compress(_BIG_XML.encode())
        assert mod.compress_xml(raw) is raw

    def test_compress_rejects_unsupported_type(self):
        with pytest.raises(TypeError):
            mod.compress_xml(42)


class TestLazyCompressInPlace:
    def test_short_xml_is_skipped(self, monkeypatch):
        # Below threshold: must not even import rethinkdb. We assert by
        # patching the lazy import target to raise if touched.
        called = MagicMock()
        from rethinkdb import r

        monkeypatch.setattr(r, "table", called)
        mod.lazy_compress_in_place("d-1", _SMALL_XML, conn=MagicMock())
        called.assert_not_called()

    def test_emits_atomic_branch_update(self, monkeypatch):
        from rethinkdb import r

        # Capture the lambda passed to ``.update()`` so we can assert
        # it produces the expected ``r.branch`` shape.
        mock_table = MagicMock(name="r.table")
        monkeypatch.setattr(r, "table", mock_table)

        update_chain = mock_table.return_value.get.return_value.update
        update_chain.return_value.run.return_value = {"replaced": 1}

        conn = MagicMock(name="conn")
        mod.lazy_compress_in_place("d-1", _BIG_XML, conn=conn)

        mock_table.assert_called_with("domains")
        mock_table.return_value.get.assert_called_with("d-1")
        # ``update`` got called once with a callable (the r.branch lambda).
        assert update_chain.call_count == 1
        update_arg = update_chain.call_args.args[0]
        assert callable(update_arg)
        update_chain.return_value.run.assert_called_with(conn)

    def test_swallows_exceptions(self, monkeypatch, caplog):
        from rethinkdb import r

        mock_table = MagicMock(name="r.table")
        mock_table.side_effect = RuntimeError("rdb went away")
        monkeypatch.setattr(r, "table", mock_table)

        with caplog.at_level("WARNING"):
            mod.lazy_compress_in_place("d-1", _BIG_XML, conn=MagicMock())
        assert any(
            "lazy_compress_in_place failed for d-1" in rec.message
            for rec in caplog.records
        )

    def test_skips_when_id_missing(self, monkeypatch):
        called = MagicMock()
        from rethinkdb import r

        monkeypatch.setattr(r, "table", called)
        mod.lazy_compress_in_place("", _BIG_XML, conn=MagicMock())
        mod.lazy_compress_in_place(None, _BIG_XML, conn=MagicMock())
        called.assert_not_called()


def _unwrap_binary(wrapped):
    """Pull the raw bytes out of an ``r.binary(...)`` ReQL term.

    The driver returns Python ``bytes`` for binary fields on read; on
    write we hand it back the ``r.binary()`` wrapper. To avoid round-
    tripping through a real database in unit tests we decode the
    term's ``base64_data`` directly.
    """
    import base64

    return base64.b64decode(wrapped.base64_data)
