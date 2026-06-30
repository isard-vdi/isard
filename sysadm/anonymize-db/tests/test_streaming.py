"""Correctness of the bounded-memory JSON-array streamer vs json.loads."""

from __future__ import annotations

import io
import json

import pytest
from anonymize_db.streaming import JsonArrayWriter, iter_json_array

# tricky payload: brackets/braces/commas inside strings, escaped quotes &
# backslashes, unicode, nesting, reql-type wrappers, numbers, null/bool, empties
DOCS = [
    {"id": "a", "s": 'has ] } , [ { and "quotes" and \\ backslash'},
    {"id": "b", "nested": {"x": [1, 2, {"y": "z]}"}], "e": []}},
    {
        "id": "c",
        "u": "unicode: café ñ 日本語 😀",
        "n": 3.14,
        "neg": -7,
        "b": True,
        "nil": None,
    },
    {"$reql_type$": "BINARY", "data": "aGVsbG8="},
    {"$reql_type$": "TIME", "epoch_time": 1700000000.5, "timezone": "+00:00"},
    {"id": "empty_str", "v": ""},
    {},
    [1, "two", {"three": 3}],
]


def _roundtrip(docs, chunk):
    text = json.dumps(docs)  # default formatting (spaces after , and :)
    got = list(iter_json_array(io.StringIO(text), chunk_size=chunk))
    assert got == docs, f"chunk={chunk}"


@pytest.mark.parametrize("chunk", [1, 2, 3, 5, 7, 16, 64, 1 << 20])
def test_iter_matches_json_loads_all_chunk_sizes(chunk):
    _roundtrip(DOCS, chunk)


def test_compact_and_pretty_framing():
    for sep in [(",", ":"), (", ", ": ")]:
        text = json.dumps(DOCS, separators=sep)
        assert list(iter_json_array(io.StringIO(text), chunk_size=3)) == DOCS
    pretty = json.dumps(DOCS, indent=2)  # newlines/whitespace between elements
    assert list(iter_json_array(io.StringIO(pretty), chunk_size=4)) == DOCS


def test_empty_array():
    assert list(iter_json_array(io.StringIO("[]"))) == []
    assert list(iter_json_array(io.StringIO("  [ \n ] "))) == []


def test_single_doc_larger_than_chunk():
    big = [{"id": "x", "blob": "Q" * 100_000}]
    assert list(iter_json_array(io.StringIO(json.dumps(big)), chunk_size=8)) == big


def test_not_an_array_raises():
    with pytest.raises(ValueError):
        list(iter_json_array(io.StringIO('{"not":"array"}')))


def test_writer_roundtrip():
    out = io.StringIO()
    w = JsonArrayWriter(out)
    for d in DOCS:
        w.write(d)
    w.close()
    assert json.loads(out.getvalue()) == DOCS
    # and it streams back identically
    assert list(iter_json_array(io.StringIO(out.getvalue()), chunk_size=5)) == DOCS
