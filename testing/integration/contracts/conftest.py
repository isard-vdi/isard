#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests: what a third-party dependency actually does.

These prove premises our own code rests on — an rq admission rule, a Lua
script's effect — against the real thing rather than against a fake. A fake
here would be a second implementation of the very behaviour under test, so a
divergence between it and the server would read as confidence instead of as a
failure. That is what keeps them out of the unit suites: a test that needs a
running server is not a unit test, whatever directory it sits in.

They need **only** the dependency they are about, never the IsardVDI stack, so
the parent suite's session fixture is shadowed here with a no-op. Without that,
collecting a contract test would try to authenticate against an apiv4 that is
not running.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    """Shadow the real-stack cleanup: nothing here talks to the stack."""
    yield
