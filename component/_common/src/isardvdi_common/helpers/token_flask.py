#
#   Copyright © 2023 Josep Maria Viñolas Auquer
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


import logging
import threading

from flask import request
from isardvdi_common.helpers.api_exceptions_flask import Error
from isardvdi_common.helpers.api_logs_users import LogsUsers
from isardvdi_common.helpers.token import Token

log = logging.getLogger(__name__)


class TokenFlask(Token):

    @staticmethod
    def get_token_header(header):
        """Obtains the Access Token from the a Header"""
        auth = request.headers.get(header, None)
        if not auth:
            raise Error(
                "unauthorized",
                header + " header is expected",
            )

        parts = auth.split()
        if parts[0].lower() != "bearer":
            raise Error(
                "unauthorized",
                header + " header must start with Bearer",
            )
        elif len(parts) == 1:
            raise Error("bad_request", "Token not found")
        elif len(parts) > 2:
            raise Error(
                "unauthorized",
                header + " header must be Bearer token",
            )

        return parts[1]  # Token

    @classmethod
    def log_user(cls, payload):
        """Fire-and-forget write of an authenticated-request audit row.

        Was ``gevent.spawn(LogsUsers, payload)`` — appended a callback
        to the gevent libev Hub. That only fires when the running
        greenlet yields, which requires ``gevent.monkey.patch_all()``
        to have made stdlib I/O cooperative. Of the three Flask
        services that import this class:

          - ``scheduler``: calls ``monkey.patch_all()`` in
            ``scheduler/src/start.py:23`` — Hub runs, greenlet fires.
          - ``webapp``: runs on waitress (stdlib threads + select),
            no monkey-patch — Hub never runs, greenlet enqueued
            forever, ``logs_users`` row never written. Silent data
            loss across every authenticated request.
          - ``notifier``: same as webapp.

        Replaced with a daemon ``threading.Thread`` — runs on a real
        OS thread under all three runtimes, doesn't block process
        exit, and matches ``isardvdi_common.helpers.user_storage._spawn_daemon``
        which migrated the same anti-pattern in the user-storage path.

        ``LogsUsers`` opens its own RethinkDB connection inside
        ``__init__`` and writes one row, so a fresh thread per call
        is fine. If this becomes a bottleneck, promote to a
        bounded module-level ``ThreadPoolExecutor`` rather than
        re-introducing gevent.

        Best-effort by design: target exceptions surface via the
        threading runtime's stderr handler. The outer try/except
        only catches failures of ``Thread.start()`` itself (e.g.
        thread-table exhaustion under DoS).
        """
        try:
            threading.Thread(target=LogsUsers, args=(payload,), daemon=True).start()
        except Exception:
            log.warning("Unable to schedule LogsUsers thread", exc_info=True)
