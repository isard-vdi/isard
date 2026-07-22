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

"""Thin re-exports for the usage helpers now living in
``isardvdi_common.lib.usage.common``.

The consolidator submodules (`consolidate.py`, `desktop.py`, `user.py`,
`storage.py`, `media.py`) keep importing from here so their relative
``from .common import …`` imports stay stable. The data-access lives
in ``_common``.
"""

import logging

from isardvdi_common.lib.usage.common import (  # noqa: F401  (re-exported)
    UsageProcessed,
    get_owner_info,
    securize_eval,
)

log = logging.getLogger("apiv4")


# Backwards-compatible function names — the consolidators import these
# by their old free-function spellings; UsageProcessed classmethods do
# the actual rdb work.
def get_group_name(group_id: str) -> str:
    return UsageProcessed.get_group_name(group_id)


def get_category_name(category_id: str) -> str:
    return UsageProcessed.get_category_name(category_id)


def get_owners_info() -> dict:
    return UsageProcessed.get_owners_info()


def get_abs_consumptions(item_type, date) -> dict:
    return UsageProcessed.get_abs_consumptions(item_type, date)


def get_params() -> dict:
    return UsageProcessed.get_params()


def get_default_consumption(parameters_ids: list[str] | None = None) -> dict:
    return UsageProcessed.get_default_consumption(parameters_ids)


def get_params_item_type_custom(item_type: str, custom: bool) -> list[dict]:
    return UsageProcessed.get_params_item_type_custom(item_type, custom)


def clear_usage_caches() -> None:
    """Clear every usage helper cache at once.

    Usage parameters are admin-edited via the usage admin endpoints;
    a single sweep helper keeps writers from having to know each
    cache name.
    """
    UsageProcessed.clear_all_caches()
