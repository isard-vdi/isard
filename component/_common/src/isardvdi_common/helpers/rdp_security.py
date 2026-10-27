#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
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

"""How the stored guest RDP state is read."""

RDP_OPEN_STATES = ("ready", "unverified")


def rdp_effective(rdp):
    """The RDP state to act on and show, from the stored ``viewer.rdp``."""
    if not rdp:
        return rdp
    # stored by older vpn probes for a guest that only serves standard RDP security
    if rdp.get("state") == "refused" and rdp.get("reason") == "tls_not_allowed":
        return {**rdp, "state": "unverified", "protocol": "rdp", "reason": None}
    return rdp
