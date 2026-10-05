# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-RethinkDB suites that need no apiv4 login."""

from typing import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    yield
