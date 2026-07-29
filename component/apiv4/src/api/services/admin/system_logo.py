#
#   Copyright © 2026 Naomi Hidalgo Piñar
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

from api.services.error import Error
from api.services.login_config_cache import clear_logo_cache
from isardvdi_common.helpers.system_logo import delete_logo, logo_status, save_logo

_VARIANTS = {"logo": "logo", "logo_collapsed": "logo-collapsed"}


class AdminSystemLogoService:
    """Service for the deployment-wide default logo and collapsed logo."""

    @staticmethod
    def get_status() -> dict:
        return {
            key: {"enabled": logo_status(variant)} for key, variant in _VARIANTS.items()
        }

    @staticmethod
    def update(data: dict) -> None:
        for key, variant in _VARIANTS.items():
            entry = data.get(key)
            if entry is None:
                continue
            if entry.get("enabled") and entry.get("data"):
                try:
                    save_logo(entry["data"], variant)
                except ValueError as e:
                    raise Error("bad_request", str(e), description_code="logo_invalid")
            elif not entry.get("enabled", True):
                delete_logo(variant)

        clear_logo_cache()
