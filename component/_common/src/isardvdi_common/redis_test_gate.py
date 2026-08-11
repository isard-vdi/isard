#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# One convention for "a real-Redis suite found no server", shared by the
# handful of suites that need one. There were two opposite conventions in the
# tree: these suites SKIPPED (so they went green having asserted nothing wherever
# no one happened to have a Redis running), while apiv4's
# test_tasks_retry.py::TestRqDependentAdmission FAILS on the grounds that "a
# guard whose premise is only checked where someone happens to have a redis
# running is a guard nobody can vouch for ... it must not be skipped into
# silence". This unifies on the second: fail, not skip.

import os

import pytest

# Escape hatch for an environment that genuinely cannot run a Redis. Unset in
# CI and under `make ci-test-common` / `make ci-test-change-handler` (which
# raise a server), so there a miss stays loud.
ALLOW_NO_REDIS_ENV = "ISARD_TESTS_ALLOW_NO_REDIS"


def redis_required(reason):
    """Fail — not skip — when a real-Redis probe cannot reach a server.

    `make ci-test-common` / `make ci-test-change-handler` start the same Redis
    the CI service pins, so a miss here is a real regression rather than an
    unlucky environment. Set ``ISARD_TESTS_ALLOW_NO_REDIS=1`` to downgrade to a
    skip where a real Redis is genuinely impossible.
    """
    message = (
        f"this suite needs a reachable Redis and must not skip into silence: "
        f"{reason}. Run it through `make ci-test-common` / "
        f"`make ci-test-change-handler` (they start one), or set "
        f"{ALLOW_NO_REDIS_ENV}=1 where a real Redis is genuinely impossible."
    )
    if os.environ.get(ALLOW_NO_REDIS_ENV):
        pytest.skip(message)
    pytest.fail(message)
