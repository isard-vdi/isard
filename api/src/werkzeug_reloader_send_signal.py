#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2014-2023 Pallets
#   Copyright (C) 2023 Simó Albert i Beltran
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

# https://github.com/pallets/werkzeug/pull/2633

import builtins
import os
import signal
import subprocess
import types
import typing as t

from werkzeug._reloader import (
    StatReloaderLoop,
    _get_args_for_reloading,
    _log,
    reloader_loops,
)


class StatReloaderLoopSendSignal(StatReloaderLoop):
    """
    Stat Reloader Loop sending signal to child process
    """

    def restart_with_reloader(self) -> int:
        """Spawn a new Python interpreter with the same arguments as the
        current one, but running the reloader thread and send SIGTERM.
        """
        old_sigterm_handler = signal.getsignal(signal.SIGTERM)
        while True:
            _log("info", f" * Restarting with {self.name}")
            args = _get_args_for_reloading()
            new_environ = os.environ.copy()
            new_environ["WERKZEUG_RUN_MAIN"] = "true"
            process = subprocess.Popen(args, env=new_environ, close_fds=False)

            def new_sigterm_handler(
                signal_number: int,
                frame: t.Optional[types.FrameType],
                process: subprocess.Popen[builtins.bytes] = process,
            ) -> None:
                process.send_signal(signal.SIGTERM)
                if callable(old_sigterm_handler):
                    old_sigterm_handler(signal_number, frame)

            signal.signal(signal.SIGTERM, new_sigterm_handler)
            exit_code = process.wait()
            signal.signal(signal.SIGTERM, old_sigterm_handler)

            if exit_code != 3:
                return exit_code


reloader_loops["sendsignal"] = StatReloaderLoopSendSignal
reloader_options = {"reloader_type": "sendsignal"}
