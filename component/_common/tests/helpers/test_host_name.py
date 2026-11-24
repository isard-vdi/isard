#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import re

import pytest
from isardvdi_common.helpers.host_name import normalize_host_name


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("bad name.example.com", id="space"),
        pytest.param("example.com/../x", id="path-traversal"),
        pytest.param("example.com\nother", id="inner-newline"),
        pytest.param("example.com\n", id="trailing-newline"),
        pytest.param("*.example.com", id="wildcard"),
        pytest.param("example.com:443", id="port"),
        pytest.param("a_b.example.com", id="underscore"),
        pytest.param("-a.example.com", id="leading-hyphen"),
        pytest.param("a-.example.com", id="trailing-hyphen"),
        pytest.param("ab--cd.example.com", id="hyphens-in-third-and-fourth-place"),
        pytest.param("xn--abc.com", id="broken-punycode"),
        pytest.param("a..example.com", id="empty-label"),
        pytest.param("a" * 64 + ".example.com", id="label-over-63-characters"),
        pytest.param(("a" * 60 + ".") * 4 + "example.com", id="over-253-characters"),
        pytest.param("", id="empty"),
        pytest.param("\U0001f4a9.la", id="emoji"),
        pytest.param("xn--ls8h.la", id="emoji-in-punycode"),
    ],
)
def test_normalize_host_name_raises_when_name_is_not_a_host_name(name):
    with pytest.raises(ValueError, match=re.escape("is not a valid host name")):
        normalize_host_name(name)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        pytest.param("aula.example.com", "aula.example.com", id="lower-case"),
        pytest.param("Aula.Example.COM", "aula.example.com", id="mixed-case"),
        pytest.param("a-b.c0.example.com", "a-b.c0.example.com", id="hyphen-digit"),
        pytest.param("xn--exmple-cua.com", "xn--exmple-cua.com", id="punycode"),
        pytest.param("exämple.com", "xn--exmple-cua.com", id="unicode"),
        pytest.param("日本語.jp", "xn--wgv71a119e.jp", id="japanese"),
        pytest.param("localhost", "localhost", id="single-label"),
        pytest.param("example.com.", "example.com.", id="trailing-dot"),
    ],
)
def test_normalize_host_name_returns_the_ascii_name_idna_gives(name, expected):
    assert normalize_host_name(name) == expected


def test_normalize_host_name_raises_when_name_is_not_a_string():
    with pytest.raises(ValueError, match=re.escape("must be a string")):
        normalize_host_name(["aula.example.com"])
