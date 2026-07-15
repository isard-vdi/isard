#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

import os

reload_enabled = os.environ.get("USAGE", "production") == "devel"
debug_enabled = os.environ.get("LOG_LEVEL", "INFO") == "DEBUG"
_is_reloader_supervisor = (
    reload_enabled and os.environ.get("WERKZEUG_RUN_MAIN") != "true"
)

# In devel the Werkzeug reloader spawns the real server as a subprocess
# (WERKZEUG_RUN_MAIN=true). Skip gevent monkey-patching and scheduler init
# in the supervisor: APScheduler would otherwise run in both processes and
# double-fire every cron, and on Python 3.13 the supervisor's subprocess
# fork trips gevent's after_fork_in_child assertion.
if _is_reloader_supervisor and __name__ == "__main__":
    from werkzeug._reloader import run_with_reloader

    run_with_reloader(lambda: None)
    raise SystemExit(0)

from gevent import monkey  # noqa: E402

monkey.patch_all()

from scheduler import app, socketio  # noqa: E402


def _serve():
    # use_reloader=False on purpose: gevent monkey-patching is already done by
    # monkey.patch_all() above. flask_socketio's gevent+reloader branch would
    # otherwise call monkey.patch_thread() a SECOND time, which on
    # gevent 25.5.1 + Python 3.13 crashes while re-patching already-patched
    # locks (ReferenceError: weakly-referenced object no longer exists) — it
    # walks existing lock weakrefs and trips on one already GC'd. This is
    # unfixed upstream in both gevent and flask_socketio, so we must not enter
    # that branch. Prod (use_reloader=False) already took the safe path.
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=debug_enabled,
        log_output=debug_enabled,
        use_reloader=False,
    )


if __name__ == "__main__":
    if reload_enabled:
        # We are the Werkzeug reloader worker (WERKZEUG_RUN_MAIN=true); the
        # supervisor half already ran run_with_reloader() above. Own the reload
        # watcher here so devel hot-reload still works WITHOUT re-entering
        # flask_socketio's crashing gevent reloader branch: run_with_reloader
        # runs _serve in a (green) thread and the file-watch loop in the main
        # thread, exiting 3 on a source change so the supervisor respawns us.
        from werkzeug._reloader import run_with_reloader

        run_with_reloader(_serve)
    else:
        _serve()
