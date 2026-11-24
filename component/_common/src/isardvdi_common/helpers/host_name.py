#
#   Copyright © 2026 IsardVDI
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

import idna


def normalize_host_name(name: object) -> str:
    """Return the ASCII form idna gives the name, or raise ValueError."""
    if not isinstance(name, str):
        raise ValueError("Host name must be a string")
    try:
        return idna.encode(name, uts46=True, std3_rules=True).decode("ascii")
    except idna.IDNAError as e:
        raise ValueError(f"{name!r} is not a valid host name: {e}") from e
