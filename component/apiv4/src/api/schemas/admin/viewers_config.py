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

from typing import Optional

from pydantic import BaseModel


class ViewerConfigUpdateRequest(BaseModel):
    """Request to update a viewer custom configuration"""

    custom: Optional[str] = None


class ViewersConfigResponse(BaseModel):
    """Response shape for ``GET /admin/viewers-config``.

    The service returns a dict keyed by viewer name (file_rdpgw,
    file_rdpvpn, file_spice) where each value is the persisted custom
    template plus the default. Permissive because the per-viewer
    fields differ.
    """

    model_config = {"extra": "allow"}
