#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from waitress import serve

from webapp import app

if __name__ == "__main__":
    reload_enabled = os.environ.get("USAGE", "production") == "devel"
    debug_enabled = os.environ.get("LOG_LEVEL", "INFO") == "DEBUG"

    if reload_enabled or debug_enabled:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=debug_enabled,
            use_debugger=debug_enabled,
            use_reloader=reload_enabled,
        )
    else:
        serve(app, listen="0.0.0.0:5000")
