#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Simó Albert i Beltran
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

"""
Helpers to convert provider config fields between API (list) and DB
(comma-separated string) representations.

The authentication Go component stores ``auto_register_roles`` as a
comma-separated string in RethinkDB (read via ``db.CommaSplitString``).
The API exposes it as a JSON list so the frontend can treat it like any
other multi-value field.
"""

_COMMA_SEPARATED_FIELDS = ("auto_register_roles",)


def provider_config_db_to_api(config):
    """Convert comma-separated string fields to lists in a provider config dict.

    :param config: A single provider config dict (e.g. ``saml_config``).
    :type config: dict
    """
    for field in _COMMA_SEPARATED_FIELDS:
        if field in config:
            value = config[field]
            if isinstance(value, str):
                config[field] = [v for v in value.split(",") if v] if value else []


def provider_config_api_to_db(config):
    """Convert list fields to comma-separated strings in a provider config dict.

    :param config: A single provider config dict (e.g. ``saml_config``).
    :type config: dict
    """
    for field in _COMMA_SEPARATED_FIELDS:
        if field in config:
            value = config[field]
            if isinstance(value, list):
                config[field] = ",".join(value)
