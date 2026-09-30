# SPDX-License-Identifier: AGPL-3.0-or-later

"""Migration ledger fixtures on a real RethinkDB, without the parent's admin login."""

from __future__ import annotations

from typing import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    """Shadow the parent's autouse fixture, which logs into apiv4."""
    yield
