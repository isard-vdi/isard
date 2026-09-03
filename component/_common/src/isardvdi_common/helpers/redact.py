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

import json
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
    "ssh_key",
    "authorized_keys",
    "jwt",
)
# Opaque blobs masked whole: secrets are embedded in the value, not in subkeys.
# `code` is exact-match so description_code/msg_code stay readable.
_SECRET_KEYS = frozenset({"xml", "code"})

BODY_LIMIT = 8192


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


def loggable_body(raw):
    """Redacted, size-capped JSON body, or None if it cannot safely be logged."""
    if not raw:
        return None
    if isinstance(raw, (bytes, bytearray)):
        if len(raw) > BODY_LIMIT:
            return {"truncated": True, "size": len(raw)}
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return None
    elif isinstance(raw, str) and len(raw) > BODY_LIMIT:
        return {"truncated": True, "size": len(raw)}
    try:
        parsed = json.loads(raw)
    except TypeError, ValueError:
        return None
    return redact_secrets(parsed)
