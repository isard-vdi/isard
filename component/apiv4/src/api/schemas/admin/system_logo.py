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

from typing import Optional

from api.schemas.admin.categories import BrandingLogo
from pydantic import BaseModel


class SystemLogoUpdateData(BaseModel):
    """Request body for updating the system-wide default logo."""

    logo: Optional[BrandingLogo] = None
    logo_collapsed: Optional[BrandingLogo] = None


class SystemLogoResponse(BaseModel):
    """Response shape for ``GET /admin/item/logo``.

    ``data`` is always omitted here — the actual image is served
    directly by the public ``/logo`` and ``/logo-collapsed`` endpoints,
    this only reports whether a custom one is currently set.
    """

    logo: BrandingLogo = BrandingLogo()
    logo_collapsed: BrandingLogo = BrandingLogo()
