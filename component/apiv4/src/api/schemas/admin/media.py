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

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class AdminMediaStatusCount(BaseModel):
    """One row of ``GET /media/status``.

    The service emits ``{status, count}`` pairs from
    ``MediaProcessed.admin_get_media_status_count``. Status values are
    DB-driven (``MediaStatusEnum`` plus historical strings), so the
    field stays loose ``str``.
    """

    status: str
    count: int


class AdminMediaItem(BaseModel):
    """One row of ``GET /admin/media`` and ``GET /admin/media/{status}``.

    The service returns the raw media doc merged with display-friendly
    joined fields (category_name, group_name, user_name, domains
    count). Permissive (``ConfigDict(extra="allow")``) because legacy
    rows may carry fields the merger doesn't know about — losing them
    silently was the apiv3 behaviour and the webapp admin tolerates it.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    category_name: Optional[str] = None
    group: Optional[str] = None
    group_name: Optional[str] = None
    user: Optional[str] = None
    user_name: Optional[str] = None
    username: Optional[str] = None
    progress: Optional[Any] = None
    url_isard: Optional[str] = None
    url_web: Optional[str] = None
    icon: Optional[str] = None
    domains: Optional[int] = None
    accessed: Optional[Any] = None
    file: Optional[str] = None
