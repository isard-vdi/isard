# SPDX-License-Identifier: AGPL-3.0-or-later

"""Heavy admission follows the open schedule entry, on a real Redis."""

from __future__ import annotations

import json

from isardvdi_common.lib.governed_worker import (
    GOVERNOR_CONFIG_KEY,
    HEAVY_RUNNING_KEY,
    GovernedWorker,
)
from rq import Queue

WHOLE_DAY = [
    {"start": "00:00", "end": "12:00", "max_heavy": 3},
    {"start": "12:00", "end": "00:00", "max_heavy": 3},
]


def _admitted(scratch_redis, block):
    scratch_redis.set(GOVERNOR_CONFIG_KEY, json.dumps(block))
    worker = GovernedWorker(
        [Queue("storage.default.maintenance", connection=scratch_redis)],
        connection=scratch_redis,
    )
    worker._refresh_live_config()
    admitted = sum(worker._reserve_heavy(f"job-{n}") for n in range(6))
    assert scratch_redis.scard(HEAVY_RUNNING_KEY) == admitted
    return worker.gov_max_heavy, admitted


def test_open_profile_sets_the_heavy_cap(scratch_redis):
    assert _admitted(scratch_redis, {"max_heavy": 1, "schedule": WHOLE_DAY}) == (3, 3)


def test_without_schedule_the_flat_cap_applies(scratch_redis):
    assert _admitted(scratch_redis, {"max_heavy": 1}) == (1, 1)


def test_unknown_zone_keeps_the_flat_cap(scratch_redis):
    block = {"max_heavy": 1, "schedule": WHOLE_DAY, "schedule_tz": "Mars/Olympus"}
    assert _admitted(scratch_redis, block) == (1, 1)
