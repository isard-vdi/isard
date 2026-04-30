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

from pydantic import BaseModel, ConfigDict


class DownloadsOverviewResponse(BaseModel):
    """Response shape for ``GET /admin/downloads``.

    The service returns ``{}`` after the registration check passes;
    keeping a typed empty model documents the contract explicitly so
    callers don't expect a payload.
    """

    pass


class DownloadItem(BaseModel):
    """One row of ``GET /admin/downloads/{kind}``.

    The shape varies per kind (domains/media merge in registry rows,
    virt_install/videos/viewers come straight from the upstream
    updates server). Permissive (``ConfigDict(extra="allow")``) so all
    five kinds round-trip without schema fragmentation; the webapp
    admin renders fields per-kind.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
