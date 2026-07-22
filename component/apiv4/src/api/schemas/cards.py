#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class CardResponse(BaseModel):
    """Single card response.

    Permissive (``ConfigDict(extra="allow")``) because card payloads
    carry varied per-source fields (stock vs user vs generated) and
    the mock fixtures historically used ``name`` where the production
    rows use ``url``.
    """

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None


class GenerateCardRequest(BaseModel):
    """Request to generate a default card"""

    desktop_id: str
    desktop_name: str
