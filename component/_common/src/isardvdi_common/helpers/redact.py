#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Miriam Melina Gamboa Valdez
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

"""Mask only secret-bearing fields in changefeed rows before logging.

Used by the change-handler and the engine so guest credentials, viewer
passwords and TLS material never reach stdout/Loki, while every other
field (status, timestamps, ids…) stays visible for debugging.
"""

from collections.abc import Mapping

REDACTED = "***"

# A dict key is masked when its lowercased name contains one of these tokens.
_SECRET_TOKENS = (
    "password",
    "passwd",
    "secret",
    "token",
    "credential",
    "tls",
    "cert",
    "private_key",
)
# Opaque blobs masked whole: secrets are embedded in the value, not in subkeys.
_SECRET_KEYS = frozenset({"xml"})


def _is_secret_key(key) -> bool:
    name = str(key).lower()
    return name in _SECRET_KEYS or any(token in name for token in _SECRET_TOKENS)


def redact_secrets(value):
    """Return a copy of ``value`` with secret-bearing fields replaced by ``***``.

    Recurses through mappings and lists; Pydantic rows are dumped to plain
    dicts first. Scalars and unknown objects pass through unchanged.
    """
    if hasattr(value, "model_dump"):
        try:
            value = value.model_dump()
        except Exception:
            return value
    if isinstance(value, Mapping):
        return {
            key: REDACTED if _is_secret_key(key) else redact_secrets(val)
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_secrets(item) for item in value]
    return value
