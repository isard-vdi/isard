# SPDX-License-Identifier: AGPL-3.0-or-later

"""Fixtures for the suites that assert on RethinkDB's own behaviour.

What lives here proves premises about the rethinkdb driver and its tooling —
what ``rethinkdb-dump`` really writes, what ``_export.run_clients`` really
forks — against a real server, because a mocked connection cannot report on
any of it. That is why these are integration tests and not unit tests.

They need RethinkDB and nothing else, so the session-wide stack fixtures of
the parent conftest do not apply and ``_cleanup_before_and_after`` is shadowed
below. The job runs pytest with ``--confcutdir`` on this directory so the
parent conftest is not even imported: these suites run in the environment of
the package under test, which does not carry the generated apiv4 clients that
conftest reaches for.
"""

from __future__ import annotations

from typing import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def _cleanup_before_and_after() -> Iterator[None]:
    """Shadow the parent's autouse fixture, which logs into apiv4.

    These suites create no apiv4 objects, so there is nothing for the
    namespace cleanup to collect, and requiring an admin login would make them
    need the whole stack to assert on a dump archive.
    """
    yield
