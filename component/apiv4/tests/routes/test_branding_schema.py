#
#   Copyright © 2026 IsardVDI
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

from api.schemas.admin.categories import BrandingResponse, BrandingUpdateData


def test_branding_update_accepts_logo_collapsed():
    m = BrandingUpdateData(
        logo_collapsed={"enabled": True, "data": "data:image/svg+xml;base64,AAAA"}
    )
    assert m.logo_collapsed.enabled is True
    assert m.logo_collapsed.data == "data:image/svg+xml;base64,AAAA"


def test_branding_response_keeps_logo_collapsed():
    # A field absent from the response model is stripped on the wire; assert
    # logo_collapsed survives the response model so GET branding returns it.
    m = BrandingResponse(logo_collapsed={"enabled": True, "data": "x"})
    dumped = m.model_dump(exclude_none=True)
    assert dumped["logo_collapsed"]["enabled"] is True
