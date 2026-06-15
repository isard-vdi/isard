"""Unit tests for the in-RAM live-XML cache.

Loaded directly from the file so it runs without the heavy ``engine`` package
import chain (the module itself only depends on the stdlib).
"""

import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "live_xml_cache", os.path.join(os.path.dirname(__file__), "live_xml_cache.py")
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def test_set_get_roundtrip():
    m.set("d1", "<domain>one</domain>")
    assert m.get("d1") == "<domain>one</domain>"


def test_get_missing_returns_none():
    assert m.get("does-not-exist") is None


def test_set_overwrites():
    m.set("d2", "first")
    m.set("d2", "second")
    assert m.get("d2") == "second"


def test_pop_removes_and_returns():
    m.set("d3", "<x/>")
    assert m.pop("d3") == "<x/>"
    assert m.get("d3") is None
    # popping a missing key is safe and returns None
    assert m.pop("d3") is None


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
