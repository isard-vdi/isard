#
#   Copyright © 2026 Josep Maria Viñolas Auquer
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

"""A scheduler whose main loop cannot be killed by one job-store error."""

import logging as log
import time

from apscheduler.schedulers.gevent import GeventScheduler


class ResilientLoopMixin:
    """APScheduler guards only get_due_jobs; the rest end the greenlet silently."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._next_tick_due = None
        self._tick_failing = False

    @property
    def stalled_seconds(self):
        # Deadline comes from the wait APScheduler computed, so a scheduler
        # idling until tomorrow is not mistaken for a stopped one.
        due = self._next_tick_due
        if due is None:
            return 0.0
        return max(0.0, time.monotonic() - due)

    def _process_jobs(self):
        try:
            wait_seconds = super()._process_jobs()
        except Exception:
            if not self._tick_failing:
                self._tick_failing = True
                log.exception(
                    "scheduler tick raised outside APScheduler's own guard; "
                    "keeping the loop alive and retrying"
                )
            wait_seconds = self.jobstore_retry_interval
        else:
            if self._tick_failing:
                self._tick_failing = False
                log.warning("scheduler tick recovered")

        self._next_tick_due = (
            None if wait_seconds is None else time.monotonic() + wait_seconds
        )
        return wait_seconds


class ResilientGeventScheduler(ResilientLoopMixin, GeventScheduler):
    pass
