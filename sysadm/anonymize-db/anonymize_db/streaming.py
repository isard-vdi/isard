"""Bounded-memory streaming of rethinkdb-dump table files.

Each `<table>.json` is a single top-level JSON array of documents. Loading it
whole (`json.load`) costs O(table size) in RAM — many GB for logs/usage/
recycle_bin on a large install. These helpers parse and re-emit the array one
document at a time, so peak memory is ~one document + a read buffer, regardless
of the table's total size.

The per-document object is parsed with the C `json` decoder (fast); only the
incremental framing is done here.
"""

from __future__ import annotations

import json
from typing import Any, Iterator, TextIO

_CHUNK = 1 << 20  # 1 MiB read granularity


def iter_json_array(fileobj: TextIO, chunk_size: int = _CHUNK) -> Iterator[Any]:
    """Yield each element of a top-level JSON array, reading incrementally.

    Memory stays bounded to roughly `chunk_size` + the largest single element,
    independent of the array length. Raises ValueError if the top level is not
    an array, or json.JSONDecodeError on malformed input.
    """
    dec = json.JSONDecoder()
    buf = ""
    i = 0
    eof = False

    def refill() -> bool:
        nonlocal buf, eof
        if eof:
            return False
        more = fileobj.read(chunk_size)
        if not more:
            eof = True
            return False
        buf += more
        return True

    # locate the opening '['
    while True:
        while i < len(buf) and buf[i].isspace():
            i += 1
        if i < len(buf):
            if buf[i] != "[":
                raise ValueError("expected a JSON array at the top level")
            i += 1
            break
        if not refill():
            return  # empty file

    while True:
        # skip whitespace and element separators
        while True:
            while i < len(buf) and (buf[i].isspace() or buf[i] == ","):
                i += 1
            if i < len(buf):
                break
            if not refill():
                return
        if buf[i] == "]":
            return
        # decode one element at i, refilling while it is still truncated
        while True:
            try:
                obj, end = dec.raw_decode(buf, i)
                break
            except json.JSONDecodeError:
                if not refill():
                    raise
        yield obj
        i = end
        # drop the consumed prefix so the buffer stays bounded
        if i >= chunk_size:
            buf = buf[i:]
            i = 0


class JsonArrayWriter:
    """Write a JSON array incrementally, one element at a time, matching the
    compact encoding rethinkdb-restore expects."""

    def __init__(self, fileobj: TextIO):
        self._f = fileobj
        self._first = True
        self._f.write("[")

    def write(self, obj: Any) -> None:
        if not self._first:
            self._f.write(",")
        json.dump(obj, self._f, ensure_ascii=False, separators=(",", ":"))
        self._first = False

    def close(self) -> None:
        self._f.write("]")
