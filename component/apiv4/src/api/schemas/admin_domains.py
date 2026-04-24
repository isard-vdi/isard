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

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# ── List Domains ─────────────────────────────────────────────────────────


class AdminListDomainsData(BaseModel):
    """Request body for listing domains (desktops or templates)."""

    kind: Literal["desktop", "template"] = "desktop"
    categories: Optional[str] = None
    domain_ids: Optional[List[str]] = None


# ── Multiple Actions ─────────────────────────────────────────────────────


class AdminMultipleActionsData(BaseModel):
    """Request body for performing actions on multiple domains."""

    action: str
    ids: List[str]


# ── Domain XML Update ────────────────────────────────────────────────────


class AdminDomainXmlData(BaseModel):
    """Request body for updating domain XML."""

    xml: Optional[dict] = None


# ── Domain Storage Path ──────────────────────────────────────────────────


class AdminDomainStoragePathData(BaseModel):
    """Request body for updating domain storage path."""

    old_path: str
    new_path: str


# ── Logs Config ──────────────────────────────────────────────────────────


class AdminLogsQueryData(BaseModel):
    """Request body for logs queries (desktops/users)."""

    # Accepts arbitrary form data for datatables-style queries
    pass
