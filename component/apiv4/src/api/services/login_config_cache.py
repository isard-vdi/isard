#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

"""Shared TTL caches for the login-config and logo public endpoints.

Lives in services/ so admin writers can invalidate them without
importing from a route module (the previous lazy
``from api.routes.open import clear_login_config_cache`` shim avoided
a routes→services→routes cycle that would otherwise reappear).
"""

from cachetools import TTLCache

login_config_cache: TTLCache = TTLCache(maxsize=10, ttl=20)
logo_cache: TTLCache = TTLCache(maxsize=10, ttl=60)


def clear_login_config_cache() -> None:
    """Invalidate the per-category login-config cache.

    Called from admin write paths that mutate login-notification or
    per-category login settings, so the next GET returns fresh data
    instead of the 20 s TTL'd response.
    """
    login_config_cache.clear()


def clear_logo_cache() -> None:
    """Invalidate the per-domain logo cache.

    Called after branding updates so the next /logo request returns
    the updated image instead of the 60 s TTL'd response. Keyed by
    host header, so we clear the whole cache (categories can share
    logos across domains).
    """
    logo_cache.clear()
