# SPDX-License-Identifier: AGPL-3.0-or-later

"""Behaviour + config tests for the scheduler misfire-grace fix.

Booking-end date jobs (gpu_desktops_destroy / gpu_profile_set /
domain_reservable_set) used to inherit APScheduler's default 1-second
``misfire_grace_time``, so when the single gevent scheduler fell minutes
behind during a booking-transition burst the jobs were silently DROPPED.
The fix sets a large ``misfire_grace_time`` (plus ``coalesce`` /
``max_instances``) via ``job_defaults`` and uses ``GeventScheduler``.

The first test pins the behaviour (a past-due job fires with a generous
grace and is dropped with the 1-second default); the executor/scheduler
class is irrelevant to that contract, so it uses ``BackgroundScheduler`` to
avoid spinning a gevent loop in the rig. The second test pins that the
production scheduler is actually configured that way.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

_SCHEDULER_PY = (
    Path(__file__).resolve().parents[1] / "src" / "scheduler" / "lib" / "scheduler.py"
)


def _run_past_due_date_job(misfire_grace_time):
    """Schedule a one-shot date job 10s in the past and report whether it
    fired within a short window, under the given grace."""
    fired = []
    sched = BackgroundScheduler(
        timezone=pytz.timezone("UTC"),
        job_defaults={"misfire_grace_time": misfire_grace_time, "coalesce": True},
    )
    sched.start()
    try:
        sched.add_job(
            lambda: fired.append(True),
            "date",
            run_date=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        # Give the scheduler a beat to evaluate the (already-past) run time.
        deadline = time.time() + 3
        while time.time() < deadline and not fired:
            time.sleep(0.05)
    finally:
        sched.shutdown(wait=False)
    return bool(fired)


def test_large_grace_runs_past_due_job_while_default_drops_it():
    # The fix: a generous grace makes a late job run instead of being dropped.
    assert _run_past_due_date_job(3600) is True
    # The bug: the APScheduler default (1s) drops a job 10s late.
    assert _run_past_due_date_job(1) is False


def test_production_scheduler_uses_gevent_and_large_grace():
    src = _SCHEDULER_PY.read_text()
    # gevent-idiomatic scheduler (no fixed 10-worker ThreadPoolExecutor cap)
    assert "GeventScheduler(" in src
    assert "BackgroundScheduler(" not in src
    # job_defaults with a large misfire grace + coalesce + single instance
    assert re.search(r"misfire_grace_time\"\s*:\s*(\d+)", src)
    grace = int(re.search(r"misfire_grace_time\"\s*:\s*(\d+)", src).group(1))
    assert grace >= 300
    assert '"coalesce": True' in src
    assert '"max_instances": 1' in src
