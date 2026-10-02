#
#   Copyright © 2026 Miriam Melina Gamboa Valdez
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

from api import admin_router
from api.schemas.admin.version import AdminVersionResponse

tag = "admin-version"

try:
    with open("/version", "r") as file:
        version = file.read()
except OSError:
    # /version is baked into the image at build time; absent when running tests
    version = ""


@admin_router.get(
    "/admin/item/version",
    tags=[tag],
    response_model=AdminVersionResponse,
    summary="Get IsardVDI version",
    description="Returns the IsardVDI version stamped into the running image.",
)
async def admin_version_get() -> AdminVersionResponse:
    return AdminVersionResponse(isardvdi_version=version)
