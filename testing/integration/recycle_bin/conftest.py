# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for the suites that assert on the migration ledger against a real
RethinkDB. They create their own rows and no apiv4 objects, so the parent's
admin-login cleanup is shadowed here."""

from __future__ import annotations

from typing import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    """Shadow the parent's autouse fixture, which logs into apiv4."""
    yield
