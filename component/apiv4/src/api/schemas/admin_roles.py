#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RoleResponse(BaseModel):
    """Single role response"""

    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    sortorder: Optional[int] = None


class RoleListResponse(BaseModel):
    """List of roles"""

    roles: List[Dict[str, Any]]
