#
#   Copyright © 2017-2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from rethinkdb import r


def add_private_code(code):
    # Open and close the connection inside the function so the
    # script's import side-effects are limited to module bindings.
    # Explicit ``.run(conn)`` replaces the legacy ``.repl()`` global
    # default — no other process relies on the implicit default and
    # the explicit form is what every other isardvdi service uses.
    conn = r.connect("isard-db", 28015)
    try:
        r.db("isard").table("config").get(1).update(
            {"resources": {"private_code": code}}
        ).run(conn)
        print("Private code updated")
    except Exception as e:
        print("Error updating.\n" + str(e))
    finally:
        conn.close(noreply_wait=False)


if __name__ == "__main__":
    code = input("Enter you private access code to IsardVDI Downloads Service: ")
    add_private_code(code)
