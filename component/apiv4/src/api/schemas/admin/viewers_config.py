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


class ViewerConfigItem(BaseModel):
    """Single viewer configuration row.

    Fields match the per-viewer dict stored under ``config.viewers`` in
    RethinkDB and consumed by the webapp DataTables admin view.
    """

    key: Optional[str] = None
    viewer: Optional[str] = None
    custom: Optional[str] = None
    default: Optional[str] = None
    fixed: Optional[str] = None
