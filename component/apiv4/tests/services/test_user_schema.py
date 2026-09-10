#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Pydantic schema tests for ``UserFromCSV``.

The username regex on this schema is shared in spirit with the HTML5 input
``pattern`` attribute on ``webapp/.../users_modals_management.html`` —
keeping these in sync matters because admins create users through both the
CSV import endpoint (server-side, this schema) and the webapp form
(client-side, the HTML pattern). The fix lands the same escaped-dash
character class in both places so both compile under JavaScript's ``/v``
flag (default in Firefox 148+ and Chromium 132+).
"""

import re

import pytest
from isardvdi_common.schemas.user import UserFromCSV
from pydantic import ValidationError

# Smallest valid CSV row used as a base; each test mutates only `username`.
_BASE = {
    "name": "User One",
    "email": "u1@example.com",
    "group": "g1",
    "category": "default",
    "role": "user",
}


@pytest.mark.parametrize(
    "username",
    [
        "alice",
        "Alice",
        "alice123",
        "alice.smith",
        "alice_smith",
        "alice-smith",
        "alice@example.com",
        "alice%external",
        "alice+admin",
        # Single-character edge cases — all chars in the allowlist are valid
        # on their own length-wise (max_length=40 is the only upper bound).
        "a",
        "-",
        "_",
        ".",
    ],
)
def test_userfromcsv_accepts_valid_usernames(username):
    model = UserFromCSV(**{**_BASE, "username": username})
    assert model.username == username


@pytest.mark.parametrize(
    "username",
    [
        "",  # empty
        "alice space",  # whitespace not allowed
        "alice/admin",  # slash not allowed
        "alice\\admin",  # backslash not allowed
        "alice<admin",  # angle bracket not allowed
        "alice;drop",  # semicolon not allowed
        "alice'inject",  # single quote not allowed
        "alice|admin",  # pipe not allowed
        "x" * 41,  # over max_length (40)
    ],
)
def test_userfromcsv_rejects_invalid_usernames(username):
    with pytest.raises(ValidationError):
        UserFromCSV(**{**_BASE, "username": username})


def test_userfromcsv_pattern_escapes_dash_for_v_flag_compat():
    """Lock the literal ``\\-`` escape into the regex.

    Browsers compiling the same string under HTML5 input pattern with the
    /v flag (default in Firefox 148+ and Chromium 132+) reject ``-`` inside
    a character class unless it's escaped or sits at start/end. The fix
    was to switch the regex from ``[A-Za-z0-9._@%+-]+`` to
    ``[\\-A-Za-z0-9._@%+]+``. Keep the escape pinned so a future
    "tidy-up" doesn't silently put ``-`` at the end (which would compile
    under /u but trip /v).
    """
    # Pydantic stores Field constraints across multiple metadata entries
    # (MaxLen, StringConstraints, …). The pattern lives on whichever entry
    # exposes a `.pattern` attribute.
    metadata = UserFromCSV.model_fields["username"].metadata
    pattern = next((m.pattern for m in metadata if getattr(m, "pattern", None)), None)
    assert pattern is not None, "expected a pattern constraint on UserFromCSV.username"
    assert (
        "\\-" in pattern
    ), f"expected literal backslash-dash in pattern, got {pattern!r}"
    # Sanity — Python's re engine compiles the pattern and accepts a single `-`.
    compiled = re.compile(pattern)
    assert compiled.match("-")
    assert compiled.match("alice-smith")
