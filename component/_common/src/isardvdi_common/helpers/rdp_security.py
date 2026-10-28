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

"""RDP security levels a guest may serve (``config.rdp_security``), all by default."""

RDP_SECURITY_LEVELS = ("rdp", "tls", "nla")
RDP_OPEN_STATES = ("ready", "unverified")


def allowed_rdp_security(config):
    """The allowed protocols from a config row; every level when unset or empty."""
    allowed = ((config or {}).get("rdp_security") or {}).get("allowed_protocols")
    if not allowed:
        return RDP_SECURITY_LEVELS
    return tuple(level for level in RDP_SECURITY_LEVELS if level in allowed)


def current_allowed_rdp_security():
    """The allowed protocols from the config row (1 s cache); every level if it cannot be read."""
    from isardvdi_common.models.config import Config

    try:
        return allowed_rdp_security(Config.get_config())
    except Exception:
        # an unreadable policy must not block every RDP viewer
        return RDP_SECURITY_LEVELS


def rdp_effective(rdp, allowed=RDP_SECURITY_LEVELS):
    """The RDP state to act on and show, from the stored ``viewer.rdp``."""
    if not rdp:
        return rdp
    # stored by older vpn probes for a guest that only serves standard RDP security
    if rdp.get("state") == "refused" and rdp.get("reason") == "tls_not_allowed":
        rdp = {**rdp, "state": "unverified", "protocol": "rdp", "reason": None}
    protocol = rdp.get("protocol")
    if (
        rdp.get("state") in RDP_OPEN_STATES
        and protocol in RDP_SECURITY_LEVELS
        and protocol not in allowed
    ):
        rdp = {**rdp, "state": "refused", "reason": "security_not_allowed"}
    return rdp


# .rdp ``authentication level``: 0 connects without warning, 1 refuses, 2 warns
CERTIFICATE_CHECK_LEVELS = (0, 1, 2)
_AUTHENTICATION_LEVEL = "authentication level:i:"


def certificate_check(rdp_file_text):
    """The ``authentication level`` a .rdp template sets, or None if it does not."""
    for line in (rdp_file_text or "").splitlines():
        line = line.strip()
        if line.startswith(_AUTHENTICATION_LEVEL):
            value = line[len(_AUTHENTICATION_LEVEL) :]
            return int(value) if value.isdigit() else None
    return None


def with_certificate_check(rdp_file_text, level):
    """The .rdp template with its ``authentication level`` line set to ``level``."""
    if level not in CERTIFICATE_CHECK_LEVELS:
        raise ValueError(f"authentication level {level!r}")
    lines = (rdp_file_text or "").splitlines()
    wanted = f"{_AUTHENTICATION_LEVEL}{level}"
    replaced = False
    for index, line in enumerate(lines):
        if line.strip().startswith(_AUTHENTICATION_LEVEL):
            lines[index] = wanted
            replaced = True
    if not replaced:
        lines.append(wanted)
    return "\n".join(lines)
