#
#   Copyright © 2025 IsardVDI
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
from isardvdi_common.helpers.api_viewers_config import ViewersConfig


class AdminViewersConfigService:

    @staticmethod
    def get_viewers_config() -> list:
        return ViewersConfig.get_viewers_config()

    @staticmethod
    def update_viewers_config(viewer: str, custom: str) -> None:
        ViewersConfig.update_viewers_config(viewer, custom)

    @staticmethod
    def reset_viewers_config(viewer: str) -> None:
        # Route layer constrains ``viewer`` to
        # ``Literal["file_rdpgw", "file_rdpvpn", "file_spice"]``.
        ViewersConfig.reset_viewers_config(viewer)
