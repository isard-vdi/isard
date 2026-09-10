# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for shared changefeed codegen utilities."""

from __future__ import annotations

import pytest
from isardvdi_codegen.changefeed_utils import camel


@pytest.mark.parametrize(
    "snake,expected",
    [
        ("foo", "Foo"),
        ("foo_bar", "FooBar"),
        ("foo_bar_baz", "FooBarBaz"),
        ("", ""),
    ],
)
def test_camel(snake, expected):
    assert camel(snake) == expected
