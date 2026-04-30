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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

# --- Policy schemas ---


class PolicyCreateRequest(BaseModel):
    """Request to create an authentication policy"""

    category: str
    role: str
    type: str
    disclaimer: Optional[bool] = None
    email_verification: Optional[bool] = False
    password: Optional[Dict[str, Any]] = None


class PolicyEditRequest(BaseModel):
    """Request to edit an authentication policy"""

    category: Optional[str] = None
    role: Optional[str] = None
    type: Optional[str] = None
    disclaimer: Optional[Any] = None
    email_verification: Optional[bool] = None
    password: Optional[Dict[str, Any]] = None


# --- Provider config schemas ---


class ProviderConfigUpdateRequest(BaseModel):
    """Request to update a provider configuration"""

    migration: Optional[Dict[str, Any]] = None


# --- Migration exception schemas ---


class MigrationExceptionCreateRequest(BaseModel):
    """Request to add a migration exception"""

    item_type: str
    item_ids: List[str]
