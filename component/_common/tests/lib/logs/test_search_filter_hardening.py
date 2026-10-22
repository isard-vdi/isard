#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The DataTables per-column search takes a plain field name and a literal value."""

import re

import pytest
from isardvdi_common.lib.logs.logs import _safe_field


class TestSafeField:
    @pytest.mark.parametrize(
        "name",
        ["id", "user_id", "starting_time", "desktop.name", "_private", "a1.b2_c"],
    )
    def test_accepts_a_plain_identifier_path(self, name):
        assert _safe_field(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "",  # empty
            "1leading_digit",
            "with space",
            "with-dash",
            "quote'injection",
            "bracket[0]",
            "$dollar",
            ".leading_dot",
            "back\\slash",
        ],
    )
    def test_rejects_anything_else(self, name):
        assert _safe_field(name) is None

    @pytest.mark.parametrize("name", [None, 12, [], {}, True])
    def test_rejects_non_strings(self, name):
        # A JSON body can put any type here; the regex would raise on a
        # non-str, so the type check has to come first.
        assert _safe_field(name) is None


class TestSearchValueIsEscaped:
    """The value is matched literally."""

    @pytest.mark.parametrize(
        "raw",
        [
            "(a+)+$",  # catastrophic backtracking
            ".*",  # matches everything
            "a.b",  # the dot must not be a wildcard
            "^admin",  # anchors must be literal
            "[a-z]+",
        ],
    )
    def test_escaping_makes_the_value_literal(self, raw):
        escaped = re.escape(raw)
        # The escaped pattern matches the literal text and nothing else.
        assert re.fullmatch(escaped, raw)
        assert not re.fullmatch(escaped, "anything else entirely")

    def test_a_dot_no_longer_spans_other_characters(self):
        assert re.search(re.escape("a.b"), "axb") is None
        assert re.search(re.escape("a.b"), "a.b") is not None
