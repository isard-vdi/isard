#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Naomi Hidalgo Piñar
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

"""Reading ``guest_properties.viewers``.

A viewer is available when its key holds a non-null value. Key presence alone
is not enough: legacy rows persist a deselected viewer as
``{"browser_rdp": None}`` instead of omitting the key.
"""


def available_viewers(guest_properties):
    """Underscored viewer ids available on a domain, from its raw row dict."""
    return list(strip_unavailable_viewers((guest_properties or {}).get("viewers")))


def strip_unavailable_viewers(viewers):
    """``viewers`` without its null-valued entries. Values pass through."""
    if not viewers:
        return {}
    return {key: value for key, value in viewers.items() if value is not None}
