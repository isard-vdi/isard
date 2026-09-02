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

"""``RethinkDBJobStore`` that reopens its connection instead of wedging on it."""

import logging as log
import threading
import time

from apscheduler.jobstores.rethinkdb import RethinkDBJobStore
from apscheduler.util import maybe_ref
from rethinkdb.errors import ReqlAuthError, ReqlDriverError

# Constants, not env knobs: the scheduler compose part passes an explicit
# environment allowlist, so os.environ here would offer a dial nobody can turn.
_CONNECT_TIMEOUT_S = 5.0
_BACKOFF_START_S = 1.0
_BACKOFF_MAX_S = 60.0
UNHEALTHY_AFTER_S = 120.0


class ReconnectingRethinkDBJobStore(RethinkDBJobStore):
    """Runs each store operation again on a fresh connection after a driver error."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conn_lock = threading.RLock()
        self._backoff_s = _BACKOFF_START_S
        self._retry_not_before = 0.0
        self._lost_at = None

    @property
    def disconnected_seconds(self):
        """How long the store has been unable to reach rethinkdb, 0 when healthy."""
        lost_at = self._lost_at
        return 0.0 if lost_at is None else time.monotonic() - lost_at

    def lookup_job(self, job_id):
        return self._run(super().lookup_job, job_id)

    def get_due_jobs(self, now):
        return self._run(super().get_due_jobs, now)

    def get_next_run_time(self):
        return self._run(super().get_next_run_time)

    def get_all_jobs(self):
        return self._run(super().get_all_jobs)

    def add_job(self, job):
        return self._run(super().add_job, job)

    def update_job(self, job):
        return self._run(super().update_job, job)

    def remove_job(self, job_id):
        return self._run(super().remove_job, job_id)

    def remove_all_jobs(self):
        return self._run(super().remove_all_jobs)

    def shutdown(self):
        # noreply_wait=True talks on the socket first, so it raises on a dead one.
        conn, self.conn = self.conn, None
        if conn is not None:
            self._close(conn)

    def _run(self, operation, *args):
        with self._conn_lock:
            try:
                result = operation(*args)
            except ReqlAuthError:
                raise
            except ReqlDriverError as error:
                self._note_lost(error)
                if not self._reconnect():
                    raise
                result = operation(*args)
            self._note_healthy()
            return result

    def _reconnect(self):
        # self.conn is rebound only once the new connection has answered, so a
        # failed attempt keeps raising ReqlDriverError rather than NoneType errors.
        if time.monotonic() < self._retry_not_before:
            return False

        owned = self.client is None
        if owned and self.conn is not None:
            self._close(self.conn)

        conn = None
        try:
            if owned:
                connect_args = dict(self.connect_args)
                connect_args.setdefault("timeout", _CONNECT_TIMEOUT_S)
                conn = self.r.connect(db=self.database, **connect_args)
            else:
                conn = maybe_ref(self.client)
                conn.reconnect(noreply_wait=False, timeout=_CONNECT_TIMEOUT_S)
            self._probe(conn)
        except Exception as error:
            if owned and conn is not None:
                self._close(conn)
            self._retry_not_before = time.monotonic() + self._backoff_s
            log.warning(
                "rdb jobstore reconnect failed (%s); retrying in %.0fs",
                error,
                self._backoff_s,
            )
            self._backoff_s = min(self._backoff_s * 2, _BACKOFF_MAX_S)
            return False

        self.conn = conn
        return True

    def _probe(self, conn):
        # Not start()'s db/table/index bootstrap: that would create the isard
        # database against whatever answered, masking a misconfiguration.
        self.r.expr(True).run(conn)

    @staticmethod
    def _close(conn):
        try:
            conn.close(noreply_wait=False)
        except Exception:
            log.debug("closing the rdb jobstore connection failed", exc_info=True)

    def _note_lost(self, error):
        # Once per transition: the container log ring is 10 MB x 5, and a line
        # every 10 s rolls away the history saying when the outage began.
        if self._lost_at is None:
            self._lost_at = time.monotonic()
            log.error(
                "rdb jobstore connection lost (%s); scheduled jobs are paused "
                "until it is back",
                error,
            )

    def _note_healthy(self):
        if self._lost_at is not None:
            log.warning(
                "rdb jobstore reconnected after %.1fs",
                time.monotonic() - self._lost_at,
            )
            self._lost_at = None
        self._backoff_s = _BACKOFF_START_S
        self._retry_not_before = 0.0
